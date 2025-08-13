import os
import requests
import tempfile
from urllib.parse import urljoin, urlparse
from PIL import Image
import trafilatura
from bs4 import BeautifulSoup
import re
from werkzeug.utils import secure_filename
import io





def natural_sort_key(text):
    """
    Sort strings containing numbers in natural order
    """
    def convert(text):
        if text.isdigit():
            return int(text)
        else:
            return text.lower()
    
    return [convert(c) for c in re.split('([0-9]+)', text)]


def scrape_chapter_images(source_website, chapter_url):
    """
    Scrape chapter images from various manga websites
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        if source_website == 'mangadex':
            return scrape_mangadx(chapter_url)
        elif source_website == 'manganelo':
            return scrape_manganelo(chapter_url)
        elif source_website == 'mangakakalot':
            return scrape_mangakakalot(chapter_url)
        elif source_website == 'generic':
            # تحقق من نوع الموقع واستخدم الكاشط المناسب
            if 'olympustaff.com' in chapter_url:
                from olympustaff_scraper import scrape_olympustaff_enhanced
                return scrape_olympustaff_enhanced(chapter_url)
            else:
                # استخدام الكشط المحسن العام
                from enhanced_scraper import scrape_enhanced_generic_site
                return scrape_enhanced_generic_site(chapter_url)
        else:
            scraped_data['error'] = 'موقع غير مدعوم'
            
    except Exception as e:
        scraped_data['error'] = f'خطأ في الكشط: {str(e)}'
    
    return scraped_data


def scrape_mangadx(chapter_url):
    """
    Scrape from MangaDx - Generic approach since API might not be available
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        response = requests.get(chapter_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get chapter title
        title_element = soup.find('h1') or soup.find('h2') or soup.find('.chapter-title')
        if title_element:
            scraped_data['chapter_title'] = title_element.get_text().strip()
        
        # Find images - try common selectors
        images = []
        for selector in ['.page-img img', '.chapter-reader img', 'img[data-src]', 'img[src*="mangadx"]']:
            images.extend(soup.select(selector))
        
        if not images:
            images = soup.find_all('img')
        
        for img in images:
            src = img.get('data-src') or img.get('src')
            if src and is_manga_image(src):
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(chapter_url, src)
                scraped_data['images'].append(src)
        
        if scraped_data['images']:
            scraped_data['success'] = True
        else:
            scraped_data['error'] = 'لم يتم العثور على صور في الفصل'
            
    except requests.RequestException as e:
        scraped_data['error'] = f'خطأ في الوصول للموقع: {str(e)}'
    except Exception as e:
        scraped_data['error'] = f'خطأ في معالجة الصفحة: {str(e)}'
    
    return scraped_data


def scrape_manganelo(chapter_url):
    """
    Scrape from Manganelo
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://manganelo.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(chapter_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get chapter title
        title_element = soup.find('h1') or soup.find('h2') or soup.find('.panel-chapter-info-top h1')
        if title_element:
            scraped_data['chapter_title'] = title_element.get_text().strip()
        
        # Find image container
        image_container = soup.find('div', class_='container-chapter-reader')
        if image_container:
            images = image_container.find_all('img')
            for img in images:
                src = img.get('src') or img.get('data-src')
                if src and is_manga_image(src):
                    # Make absolute URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(chapter_url, src)
                    scraped_data['images'].append(src)
            
            if scraped_data['images']:
                scraped_data['success'] = True
            else:
                scraped_data['error'] = 'لم يتم العثور على صور'
        else:
            scraped_data['error'] = 'تخطيط الموقع غير مدعوم'
            
    except requests.RequestException as e:
        scraped_data['error'] = f'خطأ في الوصول للموقع: {str(e)}'
    except Exception as e:
        scraped_data['error'] = f'خطأ في معالجة الصفحة: {str(e)}'
    
    return scraped_data


def scrape_mangakakalot(chapter_url):
    """
    Scrape from Mangakakalot
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://mangakakalot.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(chapter_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get chapter title
        title_element = soup.find('h1') or soup.find('h2') or soup.find('.panel-chapter-info-top h1')
        if title_element:
            scraped_data['chapter_title'] = title_element.get_text().strip()
        
        # Find images
        images = soup.find_all('img', class_='img-loading')
        if not images:
            # Try alternative selectors
            images = soup.find_all('img', src=re.compile(r'\.(jpg|jpeg|png|gif)'))
        
        for img in images:
            src = img.get('data-src') or img.get('src')
            if src and is_manga_image(src):
                # Make absolute URL
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(chapter_url, src)
                scraped_data['images'].append(src)
        
        if scraped_data['images']:
            scraped_data['success'] = True
        else:
            scraped_data['error'] = 'لم يتم العثور على صور في الفصل'
            
    except requests.RequestException as e:
        scraped_data['error'] = f'خطأ في الوصول للموقع: {str(e)}'
    except Exception as e:
        scraped_data['error'] = f'خطأ في معالجة الصفحة: {str(e)}'
    
    return scraped_data


def scrape_generic_site(chapter_url):
    """
    محسن: كشط عام للمواقع غير المعروفة مع ترتيب أفضل للصور
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(chapter_url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # جلب عنوان الفصل
        title_selectors = [
            'h1.chapter-title', 'h1.title', '.chapter-title h1', '.title h1',
            'h1', 'h2.chapter-title', 'h2.title', 
            '.panel-chapter-info-top h1', '.chapter-header h1',
            '[class*="chapter"][class*="title"] h1', '[class*="title"] h1'
        ]
        
        for selector in title_selectors:
            title_element = soup.select_one(selector)
            if title_element and title_element.get_text().strip():
                scraped_data['chapter_title'] = title_element.get_text().strip()
                break
        
        # البحث عن حاوي الصور الرئيسي
        main_content_selectors = [
            '.chapter-content', '.reading-content', '.page-break',
            '.chapter-images', '.manga-images', '.pages',
            '.reader-content', '.chapter-body', '.content',
            '#chapter-content', '#reading-content', '#pages',
            '[class*="chapter"][class*="content"]', '[class*="reading"][class*="content"]',
            '[class*="page"][class*="container"]'
        ]
        
        main_container = None
        for selector in main_content_selectors:
            container = soup.select_one(selector)
            if container:
                # تحقق من وجود صور داخل الحاوي
                images_in_container = container.find_all('img')
                if len(images_in_container) > 0:
                    main_container = container
                    break
        
        # إذا لم نجد حاوي محدد، استخدم الصفحة كاملة
        if not main_container:
            main_container = soup
        
        # جمع الصور مع معلومات إضافية للترتيب
        image_candidates = []
        
        # البحث في الصور المرئية والمخفية
        images = main_container.find_all('img')
        
        for img in images:
            # جلب جميع مصادر الصور المحتملة
            sources = [
                img.get('src'),
                img.get('data-src'),
                img.get('data-original'),
                img.get('data-lazy-src'),
                img.get('data-srcset'),
                img.get('data-echo'),
                img.get('data-url')
            ]
            
            for src in sources:
                if src and is_manga_page_image(src, img):
                    # تحويل الرابط إلى مطلق
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(chapter_url, src)
                    elif not src.startswith('http'):
                        src = urljoin(chapter_url, src)
                    
                    # جلب معلومات إضافية للترتيب
                    img_info = extract_image_order_info(img, src)
                    image_candidates.append({
                        'url': src,
                        'order': img_info['order'],
                        'element': img,
                        'dom_position': len(image_candidates)
                    })
                    break
        
        # ترتيب الصور حسب الترتيب المستخرج ثم الموضع في الصفحة
        image_candidates.sort(key=lambda x: (x['order'], x['dom_position']))
        
        # إزالة الصور المكررة والمشبوهة
        seen_urls = set()
        for img_data in image_candidates:
            url = img_data['url']
            if url not in seen_urls and is_valid_manga_image_url(url):
                scraped_data['images'].append(url)
                seen_urls.add(url)
        
        # إذا لم نجد صور كافية، جرب البحث في JavaScript أو البيانات المخفية
        if len(scraped_data['images']) < 3:
            js_images = extract_images_from_scripts(soup, chapter_url)
            for img_url in js_images:
                if img_url not in seen_urls:
                    scraped_data['images'].append(img_url)
                    seen_urls.add(img_url)
        
        if scraped_data['images']:
            scraped_data['success'] = True
            print(f"تم العثور على {len(scraped_data['images'])} صورة من {chapter_url}")
        else:
            scraped_data['error'] = 'لم يتم العثور على صور في الصفحة'
            
    except requests.RequestException as e:
        scraped_data['error'] = f'خطأ في الوصول للموقع: {str(e)}'
    except Exception as e:
        scraped_data['error'] = f'خطأ في معالجة الصفحة: {str(e)}'
        import traceback
        print(f"خطأ مفصل: {traceback.format_exc()}")
    
    return scraped_data


def is_manga_image(src):
    """
    Check if an image URL is likely a manga page
    """
    if not src:
        return False
    
    # Check file extension
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    if not any(ext in src.lower() for ext in image_extensions):
        return False
    
    # Skip common non-manga images
    skip_patterns = ['logo', 'banner', 'ad', 'avatar', 'icon', 'button', 'bg', 'background', 'thumb']
    if any(pattern in src.lower() for pattern in skip_patterns):
        return False
    
    return True


def download_scraped_images(image_urls, temp_dir, referer_url=None):
    """
    تحميل الصور من الروابط مع تحسين محسن
    """
    # تحقق من نوع الموقع واستخدم دالة التحميل المناسبة
    if image_urls and 'olympustaff.com' in image_urls[0]:
        from olympustaff_scraper import download_olympustaff_images
        return download_olympustaff_images(image_urls, temp_dir, referer_url)
    else:
        # استخدام دالة التحميل العامة
        from enhanced_scraper import download_images_with_retry
        return download_images_with_retry(image_urls, temp_dir, referer_url)


def test_scraping(source_website, chapter_url):
    """
    Test scraping functionality without downloading images
    """
    try:
        result = scrape_chapter_images(source_website, chapter_url)
        
        if result['success']:
            return {
                'success': True,
                'message': f'تم العثور على {len(result["images"])} صورة',
                'images_count': len(result['images']),
                'chapter_title': result.get('chapter_title', 'غير محدد')
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'خطأ غير معروف')
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'خطأ في الاختبار: {str(e)}'
        }


def is_manga_image(src):
    """
    Check if an image URL is likely a manga page
    """
    if not src:
        return False
    
    # Check file extension
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    if not any(ext in src.lower() for ext in image_extensions):
        return False
    
    # Skip common non-manga images
    skip_patterns = ['logo', 'banner', 'ad', 'avatar', 'icon', 'button', 'bg', 'background', 'thumb']
    if any(pattern in src.lower() for pattern in skip_patterns):
        return False
    
    return True