import os
import time
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import threading
import schedule
from flask import current_app
from app import app, db
from models import (AutoScrapingSource, ScrapingLog, ScrapingQueue, ScrapingSettings, 
                    Manga, Chapter, PageImage, Notification)
from scraper_utils import scrape_chapter_images, download_scraped_images
from utils import optimize_image
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import re


class AutoScrapingManager:
    """Manager for automatic chapter scraping"""
    
    def __init__(self):
        self.is_running = False
        self.thread = None
        
    def start_scheduler(self):
        """Start the automatic scraping scheduler"""
        if self.is_running:
            return
            
        self.is_running = True
        
        # Schedule tasks
        schedule.every(10).minutes.do(self.check_for_new_chapters)
        schedule.every(5).minutes.do(self.process_scraping_queue)
        schedule.every(1).hours.do(self.cleanup_old_logs)
        
        # Start scheduler thread
        self.thread = threading.Thread(target=self._run_scheduler)
        self.thread.daemon = True
        self.thread.start()
        
        print("Auto-scraping scheduler started")
    
    def stop_scheduler(self):
        """Stop the automatic scraping scheduler"""
        self.is_running = False
        schedule.clear()
        if self.thread:
            self.thread.join()
        print("Auto-scraping scheduler stopped")
    
    def _run_scheduler(self):
        """Run the scheduler in a separate thread"""
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def check_for_new_chapters(self):
        """Check all active sources for new chapters"""
        with app.app_context():
            try:
                sources = AutoScrapingSource.query.filter_by(is_active=True).all()
                
                for source in sources:
                    # Check if it's time to check this source
                    if source.last_check:
                        time_since_check = datetime.utcnow() - source.last_check
                        if time_since_check.total_seconds() < source.check_interval:
                            continue
                    
                    self.check_source_for_new_chapters(source)
                    
            except Exception as e:
                print(f"Error in check_for_new_chapters: {e}")
    
    def check_source_for_new_chapters(self, source: AutoScrapingSource):
        """Check a specific source for new chapters"""
        start_time = time.time()
        log_entry = ScrapingLog(
            source_id=source.id,
            check_time=datetime.utcnow()
        )
        
        try:
            # Get available chapters from source
            chapters = self.get_available_chapters(source)
            
            if not chapters:
                log_entry.status = 'no_new_chapters'
                log_entry.execution_time = time.time() - start_time
                db.session.add(log_entry)
                source.last_check = datetime.utcnow()
                db.session.commit()
                return
            
            # Filter new chapters
            new_chapters = [
                ch for ch in chapters 
                if ch['number'] > source.last_chapter_scraped
            ]
            
            if not new_chapters:
                log_entry.status = 'no_new_chapters'
                log_entry.execution_time = time.time() - start_time
                db.session.add(log_entry)
                source.last_check = datetime.utcnow()
                db.session.commit()
                return
            
            # Add new chapters to queue
            chapters_added = 0
            for chapter_data in new_chapters:
                # Check if already in queue
                existing = ScrapingQueue.query.filter_by(
                    source_id=source.id,
                    chapter_number=chapter_data['number']
                ).first()
                
                if not existing:
                    queue_item = ScrapingQueue(
                        source_id=source.id,
                        chapter_number=chapter_data['number'],
                        chapter_url=chapter_data['url'],
                        chapter_title=chapter_data.get('title'),
                        priority=1 if source.auto_publish else 0
                    )
                    db.session.add(queue_item)
                    chapters_added += 1
            
            log_entry.status = 'success'
            log_entry.chapters_found = len(new_chapters)
            log_entry.execution_time = time.time() - start_time
            db.session.add(log_entry)
            
            source.last_check = datetime.utcnow()
            db.session.commit()
            
            # Send notification if enabled
            if source.notification_enabled and chapters_added > 0:
                self.send_new_chapters_notification(source, chapters_added)
            
            print(f"Found {chapters_added} new chapters for {source.manga.title}")
            
        except Exception as e:
            log_entry.status = 'failed'
            log_entry.error_message = str(e)
            log_entry.execution_time = time.time() - start_time
            db.session.add(log_entry)
            
            source.last_check = datetime.utcnow()
            db.session.commit()
            
            print(f"Error checking source {source.id}: {e}")
    
    def get_available_chapters(self, source: AutoScrapingSource) -> List[Dict]:
        """Get list of available chapters from source website"""
        chapters = []
        
        try:
            if source.website_type == 'mangadx':
                chapters = self.get_mangadx_chapters(source.source_url)
            elif source.website_type == 'manganelo':
                chapters = self.get_manganelo_chapters(source.source_url)
            elif source.website_type == 'mangakakalot':
                chapters = self.get_mangakakalot_chapters(source.source_url)
            elif source.website_type == 'generic':
                chapters = self.get_generic_chapters(source.source_url)
        
        except Exception as e:
            print(f"Error getting chapters for source {source.id}: {e}")
        
        return chapters
    
    def get_mangadx_chapters(self, manga_url: str) -> List[Dict]:
        """Get chapters from MangaDex"""
        chapters = []
        
        try:
            # Extract manga ID from URL
            manga_id = self.extract_mangadx_manga_id(manga_url)
            if not manga_id:
                return chapters
            
            # Get chapters from API
            api_url = f"https://api.mangadx.org/manga/{manga_id}/chapters"
            params = {
                'limit': 500,
                'translatedLanguage[]': ['en'],
                'order[chapter]': 'asc'
            }
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(api_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            for chapter_data in data.get('data', []):
                attrs = chapter_data['attributes']
                chapter_num = attrs.get('chapter')
                
                if chapter_num:
                    try:
                        chapter_number = float(chapter_num)
                        chapters.append({
                            'number': chapter_number,
                            'title': attrs.get('title', f'Chapter {chapter_num}'),
                            'url': f"https://mangadx.org/chapter/{chapter_data['id']}"
                        })
                    except ValueError:
                        continue
        
        except Exception as e:
            print(f"Error getting MangaDex chapters: {e}")
        
        return chapters
    
    def get_manganelo_chapters(self, manga_url: str) -> List[Dict]:
        """Get chapters from Manganelo"""
        chapters = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://manganelo.com/'
            }
            
            response = requests.get(manga_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find chapter list
            chapter_elements = soup.find_all('a', href=re.compile(r'/chapter/'))
            
            for element in chapter_elements:
                href = element.get('href')
                text = element.get_text().strip()
                
                # Extract chapter number from text
                chapter_match = re.search(r'chapter[\s\-_]*(\d+(?:\.\d+)?)', text.lower())
                if chapter_match:
                    try:
                        chapter_number = float(chapter_match.group(1))
                        full_url = urljoin(manga_url, href) if href.startswith('/') else href
                        
                        chapters.append({
                            'number': chapter_number,
                            'title': text,
                            'url': full_url
                        })
                    except ValueError:
                        continue
        
        except Exception as e:
            print(f"Error getting Manganelo chapters: {e}")
        
        return chapters
    
    def get_mangakakalot_chapters(self, manga_url: str) -> List[Dict]:
        """Get chapters from Mangakakalot"""
        chapters = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://mangakakalot.com/'
            }
            
            response = requests.get(manga_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find chapter list
            chapter_elements = soup.find_all('a', href=re.compile(r'/chapter/'))
            
            for element in chapter_elements:
                href = element.get('href')
                text = element.get_text().strip()
                
                # Extract chapter number
                chapter_match = re.search(r'chapter[\s\-_]*(\d+(?:\.\d+)?)', text.lower())
                if chapter_match:
                    try:
                        chapter_number = float(chapter_match.group(1))
                        
                        chapters.append({
                            'number': chapter_number,
                            'title': text,
                            'url': href
                        })
                    except ValueError:
                        continue
        
        except Exception as e:
            print(f"Error getting Mangakakalot chapters: {e}")
        
        return chapters
    
    def get_generic_chapters(self, manga_url: str) -> List[Dict]:
        """Get chapters from generic manga site"""
        chapters = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(manga_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for chapter links
            chapter_elements = soup.find_all('a', href=True)
            
            for element in chapter_elements:
                href = element.get('href')
                text = element.get_text().strip()
                
                # Check if this looks like a chapter link
                if any(keyword in text.lower() for keyword in ['chapter', 'ch.', 'cap']):
                    chapter_match = re.search(r'(\d+(?:\.\d+)?)', text)
                    if chapter_match:
                        try:
                            chapter_number = float(chapter_match.group(1))
                            full_url = urljoin(manga_url, href) if href.startswith('/') else href
                            
                            chapters.append({
                                'number': chapter_number,
                                'title': text,
                                'url': full_url
                            })
                        except ValueError:
                            continue
        
        except Exception as e:
            print(f"Error getting generic chapters: {e}")
        
        return chapters
    
    def process_scraping_queue(self):
        """Process pending items in scraping queue"""
        with app.app_context():
            try:
                # Get pending items ordered by priority
                queue_items = ScrapingQueue.query.filter_by(
                    status='pending'
                ).order_by(ScrapingQueue.priority.desc()).limit(5).all()
                
                for item in queue_items:
                    self.process_queue_item(item)
                    
            except Exception as e:
                print(f"Error in process_scraping_queue: {e}")
    
    def process_queue_item(self, queue_item: ScrapingQueue):
        """Process a single queue item"""
        queue_item.status = 'processing'
        queue_item.attempts += 1
        db.session.commit()
        
        try:
            source = queue_item.source
            manga = source.manga
            
            # Check if chapter already exists
            existing_chapter = Chapter.query.filter_by(
                manga_id=manga.id,
                chapter_number=queue_item.chapter_number
            ).first()
            
            if existing_chapter:
                queue_item.status = 'completed'
                queue_item.processed_at = datetime.utcnow()
                db.session.commit()
                return
            
            # Scrape chapter images
            scrape_result = scrape_chapter_images(
                source.website_type, 
                queue_item.chapter_url
            )
            
            if not scrape_result['success']:
                raise Exception(scrape_result['error'])
            
            if not scrape_result['images']:
                raise Exception('No images found in chapter')
            
            # Create chapter
            chapter = Chapter(
                manga_id=manga.id,
                chapter_number=queue_item.chapter_number,
                title=queue_item.chapter_title or scrape_result.get('chapter_title') or f"Chapter {queue_item.chapter_number}",
                is_locked=not source.auto_publish
            )
            
            db.session.add(chapter)
            db.session.commit()
            
            # Download and save images
            temp_dir = tempfile.mkdtemp()
            try:
                downloaded_images = download_scraped_images(
                    scrape_result['images'],
                    temp_dir,
                    queue_item.chapter_url
                )
                
                if not downloaded_images:
                    raise Exception('Failed to download chapter images')
                
                # Create chapter directory
                chapter_dir = os.path.join('static/uploads/manga', str(manga.id), str(chapter.id))
                os.makedirs(chapter_dir, exist_ok=True)
                
                # Move images and create page records
                for i, temp_image_path in enumerate(downloaded_images, 1):
                    filename = f"page_{i:03d}.jpg"
                    final_path = os.path.join(chapter_dir, filename)
                    shutil.move(temp_image_path, final_path)
                    
                    # Create page record
                    page = PageImage(
                        chapter_id=chapter.id,
                        page_number=i,
                        image_path=f"uploads/manga/{manga.id}/{chapter.id}/{filename}"
                    )
                    db.session.add(page)
                
                # Update chapter pages count
                chapter.pages = len(downloaded_images)
                
                # Update source last scraped chapter
                source.last_chapter_scraped = max(source.last_chapter_scraped, queue_item.chapter_number)
                
                queue_item.status = 'completed'
                queue_item.processed_at = datetime.utcnow()
                
                db.session.commit()
                
                print(f"Successfully scraped chapter {queue_item.chapter_number} for {manga.title}")
                
            finally:
                # Clean up temp directory
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        except Exception as e:
            queue_item.error_message = str(e)
            
            if queue_item.attempts >= queue_item.max_attempts:
                queue_item.status = 'failed'
            else:
                queue_item.status = 'pending'
            
            queue_item.processed_at = datetime.utcnow()
            db.session.commit()
            
            print(f"Error processing queue item {queue_item.id}: {e}")
    
    def cleanup_old_logs(self):
        """Clean up old scraping logs"""
        with app.app_context():
            try:
                # Keep logs for 30 days
                cutoff_date = datetime.utcnow() - timedelta(days=30)
                
                old_logs = ScrapingLog.query.filter(
                    ScrapingLog.check_time < cutoff_date
                ).all()
                
                for log in old_logs:
                    db.session.delete(log)
                
                # Clean up completed queue items older than 7 days
                cutoff_date = datetime.utcnow() - timedelta(days=7)
                old_queue_items = ScrapingQueue.query.filter(
                    ScrapingQueue.status == 'completed',
                    ScrapingQueue.processed_at < cutoff_date
                ).all()
                
                for item in old_queue_items:
                    db.session.delete(item)
                
                db.session.commit()
                
            except Exception as e:
                print(f"Error in cleanup_old_logs: {e}")
    
    def send_new_chapters_notification(self, source: AutoScrapingSource, chapter_count: int):
        """Send notification about new chapters found"""
        try:
            manga = source.manga
            
            # Create admin notification
            notification = Notification(
                user_id=1,  # Assume admin user ID is 1
                type='auto_scraping',
                title=f'فصول جديدة متاحة للكشط',
                message=f'تم العثور على {chapter_count} فصل جديد للمانجا "{manga.title}" من {source.website_type}',
                link=f'/admin/auto-scraping/{source.id}'
            )
            
            db.session.add(notification)
            db.session.commit()
            
        except Exception as e:
            print(f"Error sending notification: {e}")
    
    def extract_mangadx_manga_id(self, url: str) -> Optional[str]:
        """Extract manga ID from MangaDx URL"""
        match = re.search(r'/manga/([a-f0-9\-]+)', url)
        return match.group(1) if match else None


# Global instance
auto_scraper = AutoScrapingManager()


def init_auto_scraping():
    """Initialize auto-scraping system"""
    with app.app_context():
        # Create default settings if they don't exist
        default_settings = [
            ('scraping_enabled', 'true', 'Enable automatic scraping'),
            ('max_concurrent_scrapes', '3', 'Maximum concurrent scraping operations'),
            ('scraping_delay', '5', 'Delay between scraping operations (seconds)'),
            ('quality_check_enabled', 'true', 'Enable quality checks on scraped content'),
        ]
        
        for key, value, description in default_settings:
            setting = ScrapingSettings.query.filter_by(key=key).first()
            if not setting:
                setting = ScrapingSettings(
                    key=key,
                    value=value,
                    description=description
                )
                db.session.add(setting)
        
        db.session.commit()
        
        # Start scheduler
        auto_scraper.start_scheduler()


def get_scraping_setting(key: str, default: str = '') -> str:
    """Get scraping setting value"""
    with app.app_context():
        setting = ScrapingSettings.query.filter_by(key=key).first()
        return setting.value if setting else default


def set_scraping_setting(key: str, value: str):
    """Set scraping setting value"""
    with app.app_context():
        setting = ScrapingSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = ScrapingSettings(key=key, value=value)
            db.session.add(setting)
        
        db.session.commit()