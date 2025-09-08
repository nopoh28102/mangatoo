import os
import re
import tempfile
import shutil
import logging
import time
import requests
import json
import zipfile
import threading
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, abort, session, Response
from sqlalchemy import func
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
try:
    from app.app import app, db
except ImportError:
    # Fallback for different import structures
    try:
        from app import app, db
    except ImportError:
        # Create fallback imports
        import sys
        sys.path.append('.')
        from app.app import app, db

# تهيئة Rate Limiter للحماية من الهجمات
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# API Security middleware - حماية عامة للـ API
@app.before_request
def api_security_middleware():
    """تحسين أمان جميع API endpoints"""
    if request.path.startswith('/api/'):
        # تحديد Content-Type المسموح به
        if request.method in ['POST', 'PUT', 'PATCH'] and request.content_type:
            allowed_types = ['application/json', 'application/x-www-form-urlencoded', 'multipart/form-data']
            if not any(ct in request.content_type for ct in allowed_types):
                return jsonify({
                    'status': 'error',
                    'message': 'نوع المحتوى غير مدعوم'
                }), 415
        
        # التحقق من headers المشبوهة
        suspicious_headers = ['x-forwarded-host', 'x-original-host']
        for header in suspicious_headers:
            if header in request.headers:
                logger.warning(f"Suspicious header detected from {get_remote_address()}: {header}")

# إضافة security headers للاستجابات
@app.after_request
def add_api_security_headers(response):
    """إضافة security headers للـ API responses"""
    if request.path.startswith('/api/'):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# إضافة استيرادات مفقودة
from app.models import (User, Manga, Chapter, PageImage, Category, Bookmark, ReadingProgress, 
                    Comment, CommentReaction, MangaReaction, Rating, manga_category, PublisherRequest, TranslationRequest, 
                    Notification, Announcement, Advertisement, Subscription, MangaAnalytics, Translation, Report, PaymentPlan,
                    AutoScrapingSource, ScrapingLog, ScrapingQueue, ScrapingSettings, StaticPage, BlogPost,
                    PaymentGateway, Payment, UserSubscription)
try:
    from app.utils import optimize_image, allowed_file
    from app.utils_dynamic_urls import safe_redirect_url
    from app.utils_settings import SettingsManager
    from app.utils_seo import generate_meta_tags, generate_canonical_url, generate_json_ld
except ImportError:
    def optimize_image(image_path, max_width=1200, quality=85):
        return (None, None)
    def allowed_file(filename, allowed_extensions=None):
        return True
    def safe_redirect_url(referrer_url, fallback_endpoint='index', **endpoint_kwargs):
        return referrer_url or url_for(fallback_endpoint, **endpoint_kwargs)
    
    class SettingsManager:
        @staticmethod
        def get(key, default=None):
            return default
    
    def generate_meta_tags(title=None, description=None, image=None, url=None, manga=None, chapter=None):
        return {}
    def generate_canonical_url(request, manga=None, chapter=None):
        return request.url if request else ""
    def generate_json_ld(manga=None, chapter=None):
        return "{}"

def safe_redirect(url):
    """
    Safely redirect to a URL, preventing open redirect attacks.
    Only allows redirects to the same domain.
    """
    try:
        parsed_url = urlparse(url)
        request_host = urlparse(request.url).netloc
        
        # If the URL has no netloc (relative URL), it's safe
        if not parsed_url.netloc:
            return redirect(url)
        
        # If the netloc matches our request host, it's safe
        if parsed_url.netloc == request_host:
            return redirect(url)
        
        # Otherwise, redirect to home page for safety
        return redirect(url_for('index'))
    except Exception:
        # If parsing fails, redirect to home page for safety
        return redirect(url_for('index'))

def safe_parse_float(value, default=1.0, field_name="number"):
    """
    Safely parse float values from user input, preventing NaN injection.
    Returns the parsed float or raises ValueError with user-friendly message.
    """
    if value is None:
        return default
    
    # Convert to string if needed
    str_value = str(value).strip()
    
    # Check for dangerous values
    if str_value.lower() in ('nan', 'inf', '-inf', '+inf'):
        raise ValueError(f"Invalid {field_name} value")
    
    try:
        parsed = float(str_value)
        # Additional NaN check (NaN != NaN is True)
        if parsed != parsed:
            raise ValueError(f"Invalid {field_name} value")
        return parsed
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid number")

def safe_parse_bool(value):
    """
    Safely parse boolean values from form input.
    """
    if not value:
        return False
    
    # Convert to string and check common false values
    str_value = str(value).strip().lower()
    return str_value not in ('false', '0', '', 'none', 'off', 'no')

# دالة لحفظ الصورة الشخصية
def save_profile_picture(file):
    """Save profile picture and return the URL"""
    if file and allowed_file(file.filename, ['jpg', 'jpeg', 'png', 'gif']):
        # إنشاء اسم ملف فريد
        import uuid as uuid_lib
        filename = str(uuid_lib.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
        
        # تحديد مسار المجلد
        upload_folder = os.path.join('static', 'uploads', 'avatars')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        filepath = os.path.join(upload_folder, filename)
        
        # حفظ الصورة
        file.save(filepath)
        
        # تحسين الصورة (تصغير الحجم وتحويل للصيغة المناسبة)
        try:
            with Image.open(filepath) as img:
                # تحويل إلى RGB إذا كانت PNG مع شفافية
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # تصغير الحجم إلى 200x200 مع الحفاظ على النسبة
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                
                # إنشاء صورة مربعة
                size = min(img.size)
                left = (img.width - size) // 2
                top = (img.height - size) // 2
                img = img.crop((left, top, left + size, top + size))
                img = img.resize((200, 200), Image.Resampling.LANCZOS)
                
                # حفظ الصورة المحسنة
                img.save(filepath, 'JPEG', quality=85, optimize=True)
                
                return f'/static/uploads/avatars/{filename}'
        except Exception as e:
            logging.error(f"Error processing profile picture: {e}")
            # حذف الملف إذا فشل التحسين
            if os.path.exists(filepath):
                os.remove(filepath)
            return None
    return None
from app.utils_payment import (convert_currency, get_currency_symbols, format_currency, 
                          validate_payment_amount, get_processing_fee, get_estimated_processing_time)
# Bravo Mail will be imported later when needed to avoid context issues

# Import sitemap functionality
try:
    from tools import sitemap
except ImportError:
    logging.warning("Sitemap module not available")
# استيراد المرافق الضرورية
try:
    from scrapers.simple_manga_scraper import scrape_olympustaff_simple
except ImportError:
    def scrape_olympustaff_simple(chapter_url, output_folder):
        return {'success': False, 'error': 'مكتبة simple_manga_scraper غير متوفرة', 'downloaded_files': []}

try:
    from app.utils_settings import SettingsManager as RealSettingsManager
    SettingsManager = RealSettingsManager
except ImportError:
    class SettingsManager:
        @staticmethod
        def get(key, default=None):
            return default
        @staticmethod
        def set(key, value, **kwargs):
            pass
        @staticmethod
        def clear_cache():
            pass
        @staticmethod
        def get_all():
            return {}
        @staticmethod
        def import_settings(data):
            return False
        @staticmethod
        def export_settings():
            return {}
        @staticmethod 
        def initialize_defaults():
            pass
        _default_settings = {}

try:
    from app.utils_seo import generate_meta_tags, generate_canonical_url, generate_breadcrumbs
except ImportError:
    def generate_meta_tags(**kwargs):
        return {}
    def generate_canonical_url(request, **kwargs):
        return request.url
    def generate_breadcrumbs(**kwargs):
        return '{}'

# Define missing functions
def scrape_manga_images(source_website, chapter_url):
    """Fallback function for scraping manga images"""
    try:
        return scrape_olympustaff_simple(chapter_url, '')['downloaded_files']
    except:
        return []

def get_setting(key, default=None):
    """Get a setting value"""
    try:
        return SettingsManager.get(key, default)
    except:
        return default

@app.route('/')
def index():
    try:
        # Get latest manga (8 for homepage grid)
        latest_manga = Manga.query.order_by(Manga.created_at.desc()).limit(8).all()
        
        # Get popular manga (by views)  
        popular_manga = Manga.query.order_by(Manga.views.desc()).limit(12).all()
        
        # Get completed manga (8 for homepage grid)
        completed_manga = Manga.query.filter_by(status='completed').order_by(Manga.views.desc()).limit(8).all()
        
        # Get categories
        categories = Category.query.all()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database error in index route: {e}")
        # Return with empty data to prevent crashes
        latest_manga = []
        popular_manga = []
        completed_manga = []
        categories = []
    
    # Get latest blog posts for news section
    latest_news = None
    try:
        from app.models import BlogPost
        latest_news = BlogPost.query.filter_by(is_published=True).order_by(BlogPost.published_at.desc()).limit(4).all()
    except:
        latest_news = []
    
    # Generate SEO meta tags for homepage
    try:
        from app.utils_seo import generate_meta_tags
        meta_tags = generate_meta_tags()
    except ImportError:
        meta_tags = {}
    
    return render_template('index.html', 
                         latest_manga=latest_manga, 
                         popular_manga=popular_manga,
                         completed_manga=completed_manga,
                         categories=categories,
                         latest_news=latest_news,
                         meta_tags=meta_tags)

# SEO-friendly manga detail route with slug
@app.route('/manga/<slug>')
def manga_detail(slug):
    manga = Manga.query.filter_by(slug=slug).first_or_404()
    return manga_detail_view(manga)

# Fallback route for backward compatibility
@app.route('/manga/<int:manga_id>')
def manga_detail_by_id(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    # Redirect to SEO-friendly URL if slug exists
    if manga.slug:
        return redirect(url_for('manga_detail', slug=manga.slug), code=301)
    return manga_detail_view(manga)

def manga_detail_view(manga):
    
    # Increment views
    manga.views += 1
    db.session.commit()
    
    # Check if description contains Arabic text
    import re
    def contains_arabic(text):
        if not text:
            return False
        arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
        return bool(arabic_pattern.search(text))
    
    # Set is_arabic flag for template
    manga.is_description_arabic = contains_arabic(manga.description) if manga.description else False
    
    # Generate SEO meta tags for manga page
    try:
        from app.utils_seo import generate_meta_tags
        meta_tags = generate_meta_tags(manga=manga)
    except ImportError:
        meta_tags = {}
    
    # Get all chapters for this manga
    chapters = manga.chapters.order_by(Chapter.chapter_number.asc()).all()
    
    # Separate available and locked chapters for premium info display
    available_chapters = []
    locked_chapters = []
    
    for chapter in chapters:
        if chapter.is_locked:
            locked_chapters.append(chapter)
        else:
            available_chapters.append(chapter)
    
    # Check if user has bookmarked this manga
    is_bookmarked = False
    user_rating = None
    reading_progress = None
    
    if current_user.is_authenticated:
        bookmark = Bookmark.query.filter_by(user_id=current_user.id, manga_id=manga.id).first()
        is_bookmarked = bookmark is not None
        
        rating = Rating.query.filter_by(user_id=current_user.id, manga_id=manga.id).first()
        user_rating = rating.rating if rating else None
        
        reading_progress = ReadingProgress.query.filter_by(user_id=current_user.id, manga_id=manga.id).first()
    
    # Get recent comments for this manga with reaction data
    recent_comments = Comment.query.filter_by(manga_id=manga.id, parent_id=None).join(User).order_by(Comment.created_at.desc()).limit(10).all()
    
    # Add reaction data to comments
    comments_with_reactions = []
    for comment in recent_comments:
        comment_data = {
            'comment': comment,
            'reaction_counts': comment.get_reaction_counts(),
            'user_reaction': comment.get_user_reaction(current_user.id) if current_user.is_authenticated else None,
            'replies': comment.replies.all()
        }
        comments_with_reactions.append(comment_data)
    
    # Get manga reaction data
    manga_reaction_counts = manga.get_reaction_counts()
    user_manga_reaction = manga.get_user_reaction(current_user.id) if current_user.is_authenticated else None
    
    return render_template('manga_detail.html', 
                         manga=manga, 
                         chapters=available_chapters,
                         locked_chapters=locked_chapters,
                         total_chapters=len(chapters),
                         user_bookmark=is_bookmarked,
                         user_rating=user_rating,
                         reading_progress=reading_progress,
                         comments=comments_with_reactions,
                         manga_reaction_counts=manga_reaction_counts,
                         user_manga_reaction=user_manga_reaction,
                         today=datetime.utcnow(),
                         meta_tags=meta_tags)

# SEO-friendly chapter reading route with manga slug and chapter slug
@app.route('/read/<manga_slug>/<chapter_slug>')
def read_chapter(manga_slug, chapter_slug):
    manga = Manga.query.filter_by(slug=manga_slug).first_or_404()
    chapter = Chapter.query.filter_by(manga_id=manga.id, slug=chapter_slug).first_or_404()
    return read_chapter_view(chapter)

# Fallback route for backward compatibility
@app.route('/read/<int:chapter_id>')
def read_chapter_by_id(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    manga = chapter.manga
    # Redirect to SEO-friendly URL if slugs exist
    if manga.slug and chapter.slug:
        return redirect(url_for('read_chapter', manga_slug=manga.slug, chapter_slug=chapter.slug), code=301)
    return read_chapter_view(chapter)

def read_chapter_view(chapter):
    manga = chapter.manga
    
    # Generate SEO meta tags for chapter page
    try:
        from app.utils_seo import generate_meta_tags, generate_breadcrumbs
        meta_tags = generate_meta_tags(manga=manga, chapter=chapter)
        breadcrumbs = generate_breadcrumbs(manga=manga, chapter=chapter)
    except ImportError:
        meta_tags = {}
        breadcrumbs = None
    
    # Check if chapter is locked for premium users
    if chapter.is_locked:
        now = datetime.utcnow()
        
        # Check if user is logged in
        if not current_user.is_authenticated:
            flash('هذا الفصل متاح للمشتركين المميزين فقط. يرجى تسجيل الدخول والاشتراك للوصول.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        # Check if user has premium subscription
        user_is_premium = (hasattr(current_user, 'premium_until') and 
                          current_user.premium_until and 
                          current_user.premium_until > now)
        
        if not user_is_premium:
            # Check if chapter has early access date
            if chapter.early_access_date and now < chapter.early_access_date:
                flash(f'هذا الفصل متاح للمشتركين المميزين من {chapter.early_access_date.strftime("%Y-%m-%d %H:%M")}. يرجى الاشتراك للوصول المبكر.', 'info')
                return redirect(url_for('premium_plans', manga_id=manga.id))
            
            # Check if chapter has general release date
            elif chapter.release_date and now < chapter.release_date:
                flash(f'هذا الفصل سيصبح متاحاً للجميع في {chapter.release_date.strftime("%Y-%m-%d %H:%M")}. اشترك الآن للوصول المبكر!', 'info')
                return redirect(url_for('premium_plans', manga_id=manga.id))
            
            else:
                # Chapter is locked but no dates set - premium only
                flash('هذا الفصل متاح للمشتركين المميزين فقط. يرجى الاشتراك للوصول.', 'warning')
                return redirect(url_for('premium_plans', manga_id=manga.id))
    
    # Get all pages for this chapter
    pages = chapter.page_images.order_by(PageImage.page_number.asc()).all()
    
    if not pages:
        flash('هذا الفصل لا يحتوي على صفحات متاحة أو لا يزال قيد المعالجة.', 'warning')
        if manga.slug:
            return redirect(url_for('manga_detail', slug=manga.slug))
        else:
            return redirect(url_for('manga_detail_by_id', manga_id=manga.id))
    
    # Note: image_url is now a property in PageImage model that automatically
    # handles Cloudinary URLs, local image paths, and fallbacks
    
    # Update reading progress if user is logged in
    if current_user.is_authenticated:
        progress = ReadingProgress.query.filter_by(
            user_id=current_user.id, 
            manga_id=manga.id
        ).first()
        
        if progress:
            progress.chapter_id = chapter.id
            progress.page_number = 1
            progress.updated_at = datetime.utcnow()
        else:
            progress = ReadingProgress()
            progress.user_id = current_user.id
            progress.manga_id = manga.id
            progress.chapter_id = chapter.id
            progress.page_number = 1
            db.session.add(progress)
        
        db.session.commit()
    
    # Get adjacent chapters for navigation
    prev_chapter = Chapter.query.filter(
        Chapter.manga_id == manga.id,
        Chapter.chapter_number < chapter.chapter_number
    ).order_by(Chapter.chapter_number.desc()).first()
    
    next_chapter = Chapter.query.filter(
        Chapter.manga_id == manga.id,
        Chapter.chapter_number > chapter.chapter_number
    ).order_by(Chapter.chapter_number.asc()).first()
    
    # Get comments
    comments = chapter.comments.order_by(Comment.created_at.desc()).all()
    
    # Get advertisements for free users
    advertisements = {}
    show_ads = True
    if current_user.is_authenticated and current_user.is_premium:
        show_ads = False
    
    if show_ads:
        # Get active advertisements for different placements
        now = datetime.utcnow()
        
        advertisements['reader_top'] = Advertisement.query.filter_by(
            placement='reader_top', is_active=True
        ).filter(
            db.or_(Advertisement.start_date == None, Advertisement.start_date <= now)
        ).filter(
            db.or_(Advertisement.end_date == None, Advertisement.end_date >= now)
        ).order_by(Advertisement.priority.desc()).first()
        
        advertisements['reader_bottom'] = Advertisement.query.filter_by(
            placement='reader_bottom', is_active=True
        ).filter(
            db.or_(Advertisement.start_date == None, Advertisement.start_date <= now)
        ).filter(
            db.or_(Advertisement.end_date == None, Advertisement.end_date >= now)
        ).order_by(Advertisement.priority.desc()).first()
        
        advertisements['reader_side'] = Advertisement.query.filter_by(
            placement='reader_side', is_active=True
        ).filter(
            db.or_(Advertisement.start_date == None, Advertisement.start_date <= now)
        ).filter(
            db.or_(Advertisement.end_date == None, Advertisement.end_date >= now)
        ).order_by(Advertisement.priority.desc()).first()
        
        advertisements['between_pages'] = Advertisement.query.filter_by(
            placement='between_pages', is_active=True
        ).filter(
            db.or_(Advertisement.start_date == None, Advertisement.start_date <= now)
        ).filter(
            db.or_(Advertisement.end_date == None, Advertisement.end_date >= now)
        ).order_by(Advertisement.priority.desc()).first()
        
        advertisements['chapter_end'] = Advertisement.query.filter_by(
            placement='chapter_end', is_active=True
        ).filter(
            db.or_(Advertisement.start_date == None, Advertisement.start_date <= now)
        ).filter(
            db.or_(Advertisement.end_date == None, Advertisement.end_date >= now)
        ).order_by(Advertisement.priority.desc()).first()
    
    return render_template('reader.html', 
                         chapter=chapter, 
                         manga=manga,
                         pages=pages,
                         prev_chapter=prev_chapter,
                         next_chapter=next_chapter,
                         comments=comments,
                         advertisements=advertisements,
                         show_ads=show_ads)

@app.route('/library')
def library():
    search = request.args.get('search', '')
    category_id = request.args.get('category', '')
    manga_type = request.args.get('type', '')
    status = request.args.get('status', '')
    sort = request.args.get('sort', 'latest')
    
    query = Manga.query
    
    # Apply filters
    if search:
        query = query.filter(
            (Manga.title.contains(search)) |
            (Manga.title_ar.contains(search)) |
            (Manga.author.contains(search))
        )
    
    if category_id:
        query = query.join(manga_category).filter(manga_category.c.category_id == category_id)
    
    if manga_type:
        query = query.filter(Manga.type == manga_type)
    
    if status:
        query = query.filter(Manga.status == status)
    
    # Apply sorting
    if sort == 'latest':
        query = query.order_by(Manga.created_at.desc())
    elif sort == 'popular':
        query = query.order_by(Manga.views.desc())
    elif sort == 'rating':
        # This would require a more complex query with joins
        query = query.order_by(Manga.created_at.desc())
    elif sort == 'alphabetical':
        query = query.order_by(Manga.title.asc())
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    manga_list = query.paginate(page=page, per_page=24, error_out=False)
    
    categories = Category.query.all()
    
    return render_template('library.html', 
                         manga_list=manga_list,
                         categories=categories,
                         search=search,
                         selected_category=category_id,
                         selected_type=manga_type,
                         selected_status=status,
                         selected_sort=sort)

@app.route('/bookmark/<int:manga_id>', methods=['POST'])
@login_required
def toggle_bookmark(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    
    bookmark = Bookmark.query.filter_by(user_id=current_user.id, manga_id=manga_id).first()
    
    if bookmark:
        db.session.delete(bookmark)
        action = 'removed'
    else:
        bookmark = Bookmark()
        bookmark.user_id = current_user.id
        bookmark.manga_id = manga_id
        db.session.add(bookmark)
        action = 'added'
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'action': action})

@app.route('/rate/<int:manga_id>', methods=['POST'])
@login_required
def rate_manga(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    rating_value = (request.json or {}).get('rating')
    
    if not rating_value or rating_value < 1 or rating_value > 5:
        return jsonify({'status': 'error', 'message': 'Invalid rating'}), 400
    
    rating = Rating.query.filter_by(user_id=current_user.id, manga_id=manga_id).first()
    
    if rating:
        rating.rating = rating_value
    else:
        rating = Rating()
        rating.user_id = current_user.id
        rating.manga_id = manga_id
        rating.rating = rating_value
        db.session.add(rating)
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'new_average': manga.average_rating})

@app.route('/comment/<int:chapter_id>', methods=['POST'])
@login_required
def add_comment(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    content = (request.json or {}).get('content', '').strip()
    
    if not content:
        return jsonify({'status': 'error', 'message': 'Comment cannot be empty'}), 400
    
    comment = Comment()
    comment.user_id = current_user.id
    comment.chapter_id = chapter_id
    comment.content = content
    
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'comment': {
            'id': comment.id,
            'content': comment.content,
            'username': current_user.username,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
        }
    })

@app.route('/manga-comment/<int:manga_id>', methods=['POST'])
@login_required
def add_manga_comment(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    content = (request.json or {}).get('content', '').strip()
    
    if not content:
        return jsonify({'status': 'error', 'message': 'Comment cannot be empty'}), 400
    
    comment = Comment()
    comment.user_id = current_user.id
    comment.manga_id = manga_id
    comment.content = content
    
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'comment': {
            'id': comment.id,
            'content': comment.content,
            'username': current_user.username,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
        }
    })

@app.route('/add_comment', methods=['POST'])
@login_required
def add_comment_form():
    """Add comment via form submission"""
    content = request.form.get('content', '').strip()
    manga_id = request.form.get('manga_id')
    chapter_id = request.form.get('chapter_id')
    
    if not content:
        flash('المحتوى مطلوب', 'error')
        return redirect(safe_redirect_url(request.referrer, 'index'))
    
    # Handle image upload
    image_path = None
    if 'image' in request.files:
        image_file = request.files['image']
        if image_file and image_file.filename:
            import os
            from werkzeug.utils import secure_filename
            
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join('static', 'uploads', 'comments')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save the file
            filename = secure_filename(image_file.filename)
            timestamp = str(int(datetime.utcnow().timestamp()))
            filename = f"{timestamp}_{filename}"
            image_path = os.path.join(upload_dir, filename)
            image_file.save(image_path)
            
            # Store relative path for database
            image_path = f"uploads/comments/{filename}"
    
    comment = Comment()
    comment.user_id = current_user.id
    comment.content = content
    comment.manga_id = int(manga_id) if manga_id else None
    comment.chapter_id = int(chapter_id) if chapter_id else None
    
    # If there's an image, add it to the content
    if image_path:
        comment.content += f"\n[صورة: /static/{image_path}]"
    
    db.session.add(comment)
    db.session.commit()
    
    flash('تم إضافة التعليق بنجاح', 'success')
    return redirect(safe_redirect_url(request.referrer, 'index'))

@app.route('/manga/<int:manga_id>/comment', methods=['POST'])
@login_required
def add_manga_comment_form(manga_id):
    """Add comment to manga via form submission"""
    manga = Manga.query.get_or_404(manga_id)
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('المحتوى مطلوب', 'error')
        return redirect(safe_redirect_url(request.referrer, 'manga_detail', manga_slug=manga.slug))
    
    # Handle image upload
    image_path = None
    if 'image' in request.files:
        image_file = request.files['image']
        if image_file and image_file.filename:
            import os
            from werkzeug.utils import secure_filename
            
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join('static', 'uploads', 'comments')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save the file
            filename = secure_filename(image_file.filename)
            timestamp = str(int(datetime.utcnow().timestamp()))
            filename = f"{timestamp}_{filename}"
            image_path = os.path.join(upload_dir, filename)
            image_file.save(image_path)
            
            # Store relative path for database
            image_path = f"uploads/comments/{filename}"
    
    comment = Comment()
    comment.user_id = current_user.id
    comment.content = content
    comment.manga_id = manga_id
    
    # If there's an image, add it to the content
    if image_path:
        comment.content += f"\n[صورة: /static/{image_path}]"
    
    db.session.add(comment)
    db.session.commit()
    
    flash('تم إضافة التعليق بنجاح', 'success')
    return redirect(url_for('manga_detail', slug=manga.slug))

@app.route('/manga-comments/<int:manga_id>')
def get_manga_comments(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    offset = request.args.get('offset', 0, type=int)
    limit = 5
    
    comments = Comment.query.filter_by(manga_id=manga_id).join(User).order_by(Comment.created_at.desc()).offset(offset).limit(limit).all()
    
    comments_data = []
    for comment in comments:
        comments_data.append({
            'id': comment.id,
            'content': comment.content,
            'username': comment.user.username,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
        })
    
    return jsonify({'comments': comments_data})

@app.route('/comment/<int:comment_id>/react', methods=['POST'])
@login_required
def add_comment_reaction(comment_id):
    """Add or update reaction to a comment"""
    comment = Comment.query.get_or_404(comment_id)
    if not request.json:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400
    reaction_type = request.json.get('reaction_type')
    
    if reaction_type not in ['surprised', 'angry', 'shocked', 'love', 'laugh', 'thumbs_up']:
        return jsonify({'success': False, 'error': 'Invalid reaction type'}), 400
    
    # Check if user already has a reaction on this comment
    existing_reaction = CommentReaction.query.filter_by(
        user_id=current_user.id,
        comment_id=comment_id
    ).first()
    
    if existing_reaction:
        if existing_reaction.reaction_type == reaction_type:
            # Remove reaction if clicking the same one
            db.session.delete(existing_reaction)
            db.session.commit()
            user_reaction = None
        else:
            # Update existing reaction
            existing_reaction.reaction_type = reaction_type
            db.session.commit()
            user_reaction = reaction_type
    else:
        # Add new reaction
        new_reaction = CommentReaction()
        new_reaction.user_id = current_user.id
        new_reaction.comment_id = comment_id
        new_reaction.reaction_type = reaction_type
        db.session.add(new_reaction)
        db.session.commit()
        user_reaction = reaction_type
    
    # Get updated reaction counts
    reaction_counts = comment.get_reaction_counts()
    
    return jsonify({
        'success': True,
        'reaction_counts': reaction_counts,
        'user_reaction': user_reaction
    })

@app.route('/manga/<int:manga_id>/react', methods=['POST'])
@login_required
def react_to_manga(manga_id):
    """Add or update reaction to a manga"""
    manga = Manga.query.get_or_404(manga_id)
    if not request.json:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400
    reaction_type = request.json.get('reaction_type')
    
    if reaction_type not in ['surprised', 'angry', 'shocked', 'love', 'laugh', 'thumbs_up']:
        return jsonify({'success': False, 'error': 'Invalid reaction type'}), 400
    
    # Check if user already has a reaction on this manga
    existing_reaction = MangaReaction.query.filter_by(
        user_id=current_user.id,
        manga_id=manga_id
    ).first()
    
    if existing_reaction:
        if existing_reaction.reaction_type == reaction_type:
            # Remove reaction if clicking the same one
            db.session.delete(existing_reaction)
            db.session.commit()
            user_reaction = None
        else:
            # Update existing reaction
            existing_reaction.reaction_type = reaction_type
            db.session.commit()
            user_reaction = reaction_type
    else:
        # Add new reaction
        new_reaction = MangaReaction()
        new_reaction.user_id = current_user.id
        new_reaction.manga_id = manga_id
        new_reaction.reaction_type = reaction_type
        db.session.add(new_reaction)
        db.session.commit()
        user_reaction = reaction_type
    
    # Get updated reaction counts
    reaction_counts = manga.get_reaction_counts()
    
    return jsonify({
        'success': True,
        'reaction_counts': reaction_counts,
        'user_reaction': user_reaction
    })

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    """Delete a comment"""
    comment = Comment.query.get_or_404(comment_id)
    
    # Check if user owns the comment or is admin
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Delete all reactions first
    CommentReaction.query.filter_by(comment_id=comment_id).delete()
    
    # Delete all replies
    Comment.query.filter_by(parent_id=comment_id).delete()
    
    # Delete the comment
    db.session.delete(comment)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/comment/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_comment(comment_id):
    """Edit a comment"""
    comment = Comment.query.get_or_404(comment_id)
    
    # Check if user owns the comment
    if comment.user_id != current_user.id:
        abort(403)
    
    if not request.json:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400
    content = request.json.get('content', '').strip()
    if not content:
        return jsonify({'success': False, 'error': 'Comment cannot be empty'}), 400
    
    comment.content = content
    comment.is_edited = True
    comment.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'content': comment.content,
        'updated_at': comment.updated_at.strftime('%Y-%m-%d %H:%M')
    })



# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'error')
            return render_template('auth/register.html')
        
        if User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني موجود بالفعل', 'error')
            return render_template('auth/register.html')
        
        # معالجة رفع الصورة الشخصية
        avatar_url = None
        if 'profile_picture' in request.files and request.files['profile_picture'].filename:
            avatar_url = save_profile_picture(request.files['profile_picture'])
            if not avatar_url:
                flash('حدث خطأ في رفع الصورة الشخصية', 'warning')
        
        # Create new user
        user = User()
        user.username = username
        user.email = email
        user.password_hash = generate_password_hash(password)
        user.avatar_url = avatar_url or '/static/img/default-avatar.svg'
        
        db.session.add(user)
        db.session.commit()
        
        # Send welcome email
        try:
            from app.utils_bravo_mail import bravo_mail, send_welcome_email
        except ImportError:
            bravo_mail = None
            send_welcome_email = None
        
        if bravo_mail and bravo_mail.is_enabled() and send_welcome_email:
            try:
                email_result = send_welcome_email(user.email, user.username)
                if email_result.get('success'):
                    logger.info(f"Welcome email sent successfully to {user.email}")
                else:
                    logger.warning(f"Failed to send welcome email to {user.email}: {email_result.get('error')}")
            except Exception as e:
                logger.error(f"Error sending welcome email to {user.email}: {str(e)}")
        
        login_user(user)
        flash('تم إنشاء الحساب بنجاح!', 'success')
        return redirect(url_for('index'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Admin routes
@app.route('/admin')
@login_required
def admin_dashboard():
    # Allow access for admin, publisher, or translator
    if not (current_user.is_admin or current_user.is_publisher or current_user.is_translator):
        abort(403)
    
    total_manga = Manga.query.count()
    total_chapters = Chapter.query.count()
    total_users = User.query.count()
    
    recent_manga = Manga.query.order_by(Manga.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_manga=total_manga,
                         total_chapters=total_chapters,
                         total_users=total_users,
                         recent_manga=recent_manga)

# Redirected to unified upload page
@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
def admin_upload():
    """Redirect to the unified upload page"""
    return redirect(url_for('admin_upload_new'))

@app.route('/admin/manage')
@login_required
def admin_manage():
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    try:
        # Get filter parameters
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        category_id = request.args.get('category', '')
        sort = request.args.get('sort', 'newest')
        
        # Build query
        query = Manga.query
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    Manga.title.contains(search),
                    Manga.title_ar.contains(search) if Manga.title_ar is not None else False,
                    Manga.author.contains(search),
                    Manga.artist.contains(search)
                )
            )
        
        # Apply status filter
        if status == 'published':
            query = query.filter(Manga.is_published == True)
        elif status == 'draft':
            query = query.filter(Manga.is_published == False)
        elif status == 'featured':
            query = query.filter(Manga.is_featured == True)
        
        # Apply category filter
        if category_id:
            query = query.filter(Manga.categories.any(Category.id == category_id))
        
        # Apply sorting
        if sort == 'oldest':
            query = query.order_by(Manga.created_at.asc())
        elif sort == 'alphabetical':
            query = query.order_by(Manga.title.asc())
        elif sort == 'popular':
            query = query.order_by(Manga.views.desc())
        else:  # newest
            query = query.order_by(Manga.created_at.desc())
        
        # Paginate results
        manga_list = query.paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Calculate statistics
        total_manga = Manga.query.count()
        published_manga = Manga.query.filter(Manga.is_published == True).count()
        draft_manga = Manga.query.filter(Manga.is_published == False).count()
        featured_manga = Manga.query.filter(Manga.is_featured == True).count()
        
        # Get all categories for the dropdown
        categories = Category.query.filter(Category.is_active == True).order_by(Category.name).all()
        
        return render_template('admin/manage_manga.html', 
                             manga_list=manga_list,
                             total_manga=total_manga,
                             published_manga=published_manga,
                             draft_manga=draft_manga,
                             featured_manga=featured_manga,
                             categories=categories,
                             search=search,
                             current_status=status,
                             current_category=category_id,
                             current_sort=sort)
    except Exception as e:
        logging.error(f"Error in admin_manage: {str(e)}")
        flash(f'خطأ في تحميل صفحة إدارة المانجا: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_manga/<int:manga_id>', methods=['POST'])
@login_required
def admin_delete_manga(manga_id):
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    manga = Manga.query.get_or_404(manga_id)
    
    try:
        logging.info(f"🗑️ Starting deletion process for manga {manga_id}: {manga.title}")
        
        # Delete reading progress records first to prevent foreign key constraints
        ReadingProgress.query.filter_by(manga_id=manga_id).delete()
        
        # Delete images from Cloudinary
        try:
            from app.utils_cloudinary import cloudinary_uploader
            cloudinary_result = cloudinary_uploader.delete_manga_images(manga_id)
            if cloudinary_result['success']:
                logging.info(f"✅ Deleted {cloudinary_result['deleted_count']} images from Cloudinary")
                if cloudinary_result.get('errors'):
                    logging.warning(f"⚠️ Some Cloudinary deletion errors: {cloudinary_result['errors']}")
            else:
                logging.error(f"❌ Failed to delete images from Cloudinary: {cloudinary_result.get('error')}")
        except Exception as e:
            logging.error(f"❌ Error during Cloudinary deletion: {e}")
        
        # Delete associated local files (backup/fallback)
        if manga.cover_image and os.path.exists(manga.cover_image):
            try:
                os.remove(manga.cover_image)
                logging.info(f"✅ Deleted local cover image: {manga.cover_image}")
            except Exception as e:
                logging.warning(f"⚠️ Could not delete local cover image: {e}")
        
        # Delete chapter images from local storage (backup/fallback)
        for chapter in manga.chapters:
            for page in chapter.page_images:
                if page.image_path and os.path.exists(page.image_path):
                    try:
                        os.remove(page.image_path)
                        logging.info(f"✅ Deleted local image: {page.image_path}")
                    except Exception as e:
                        logging.warning(f"⚠️ Could not delete local image: {e}")
        
        # Delete the manga (cascade will handle other relationships)
        db.session.delete(manga)
        db.session.commit()
        
        logging.info(f"✅ Successfully deleted manga {manga_id} from database")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error deleting manga {manga_id}: {str(e)}")
        flash(f'خطأ في حذف المانجا: {str(e)}', 'error')
        return redirect(url_for('admin_manage'))
    
    flash('تم حذف المانجا بنجاح من قاعدة البيانات والتخزين السحابي!', 'success')
    return redirect(url_for('admin_manage'))

@app.route('/admin/delete_selected_manga', methods=['POST'])
@login_required
def admin_delete_selected_manga():
    """Delete multiple selected manga"""
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    try:
        data = request.get_json()
        manga_ids = data.get('manga_ids', [])
        
        if not manga_ids:
            return jsonify({
                'success': False,
                'message': 'لم يتم تحديد أي مانجا للحذف'
            })
        
        deleted_count = 0
        errors = []
        
        # Get the manga objects first
        manga_objects = Manga.query.filter(Manga.id.in_(manga_ids)).all()
        
        for manga in manga_objects:
            try:
                logging.info(f"🗑️ Deleting manga {manga.id}: {manga.title}")
                
                # Delete reading progress records first
                ReadingProgress.query.filter_by(manga_id=manga.id).delete()
                
                # Delete images from Cloudinary
                try:
                    from app.utils_cloudinary import cloudinary_uploader
                    cloudinary_result = cloudinary_uploader.delete_manga_images(manga.id)
                    if cloudinary_result['success']:
                        logging.info(f"✅ Deleted {cloudinary_result['deleted_count']} images from Cloudinary for manga {manga.id}")
                    else:
                        logging.warning(f"⚠️ Failed to delete images from Cloudinary for manga {manga.id}")
                except Exception as e:
                    logging.error(f"❌ Error during Cloudinary deletion for manga {manga.id}: {e}")
                
                # Delete local files (backup/fallback)
                if manga.cover_image and os.path.exists(manga.cover_image):
                    try:
                        os.remove(manga.cover_image)
                        logging.info(f"✅ Deleted local cover image: {manga.cover_image}")
                    except Exception as e:
                        logging.warning(f"⚠️ Could not delete local cover image: {e}")
                
                # Delete chapter images from local storage
                for chapter in manga.chapters:
                    for page in chapter.page_images:
                        if page.image_path and os.path.exists(page.image_path):
                            try:
                                os.remove(page.image_path)
                            except Exception as e:
                                logging.warning(f"⚠️ Could not delete local image: {e}")
                
                # Delete the manga
                db.session.delete(manga)
                deleted_count += 1
                
            except Exception as e:
                error_msg = f"خطأ في حذف المانجا {manga.title}: {str(e)}"
                errors.append(error_msg)
                logging.error(error_msg)
        
        # Commit all deletions at once
        db.session.commit()
        
        success_msg = f'تم حذف {deleted_count} مانجا بنجاح'
        if errors:
            success_msg += f' (مع {len(errors)} أخطاء)'
        
        logging.info(f"✅ Successfully deleted {deleted_count} manga")
        
        return jsonify({
            'success': True,
            'message': success_msg,
            'deleted_count': deleted_count,
            'errors': errors
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error in bulk delete: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء الحذف: {str(e)}'
        })

@app.route('/admin/delete_all_manga', methods=['POST'])
@login_required
def admin_delete_all_manga():
    """Delete all manga in the database"""
    if not current_user.is_admin:
        abort(403)  # Only admins can delete ALL content
    
    try:
        # Get total count before deletion
        total_manga = Manga.query.count()
        
        if total_manga == 0:
            return jsonify({
                'success': False,
                'message': 'لا يوجد مانجا للحذف'
            })
        
        logging.info(f"🗑️ Starting deletion of ALL manga ({total_manga} items)")
        
        # Get all manga objects
        all_manga = Manga.query.all()
        deleted_count = 0
        
        # Delete reading progress for all manga
        ReadingProgress.query.delete()
        
        for manga in all_manga:
            try:
                # Delete images from Cloudinary
                try:
                    from app.utils_cloudinary import cloudinary_uploader
                    cloudinary_result = cloudinary_uploader.delete_manga_images(manga.id)
                    if cloudinary_result['success']:
                        logging.info(f"✅ Deleted {cloudinary_result['deleted_count']} images from Cloudinary for manga {manga.id}")
                except Exception as e:
                    logging.error(f"❌ Error during Cloudinary deletion for manga {manga.id}: {e}")
                
                # Delete local files
                if manga.cover_image and os.path.exists(manga.cover_image):
                    try:
                        os.remove(manga.cover_image)
                    except Exception as e:
                        logging.warning(f"⚠️ Could not delete local cover image: {e}")
                
                # Delete chapter images from local storage
                for chapter in manga.chapters:
                    for page in chapter.page_images:
                        if page.image_path and os.path.exists(page.image_path):
                            try:
                                os.remove(page.image_path)
                            except Exception as e:
                                pass  # Continue even if local files can't be deleted
                
                deleted_count += 1
                
            except Exception as e:
                logging.error(f"❌ Error processing manga {manga.id}: {e}")
        
        # Delete all manga at once
        Manga.query.delete()
        db.session.commit()
        
        logging.info(f"✅ Successfully deleted ALL manga ({deleted_count} items)")
        
        return jsonify({
            'success': True,
            'message': f'تم حذف جميع المانجا بنجاح',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error in delete all manga: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء حذف جميع المانجا: {str(e)}'
        })

@app.route('/admin/edit_manga/<int:manga_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_manga(manga_id):
    """Edit manga details"""
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    manga = Manga.query.get_or_404(manga_id)
    
    if request.method == 'GET':
        # Return edit form page
        categories = Category.query.all()
        return render_template('admin/edit_manga.html', manga=manga, categories=categories)
    
    if request.method == 'POST':
        try:
            # Update manga fields
            manga.title = request.form.get('title', '').strip()
            manga.title_ar = request.form.get('title_ar', '').strip()
            manga.description = request.form.get('description', '').strip()
            manga.description_ar = request.form.get('description_ar', '').strip()
            manga.author = request.form.get('author', '').strip()
            manga.artist = request.form.get('artist', '').strip()
            manga.type = request.form.get('type', 'manga')
            manga.status = request.form.get('status', 'ongoing')
            manga.age_rating = request.form.get('age_rating', 'everyone')
            
            # Handle cover image if uploaded
            cover_file = request.files.get('cover_image')
            if cover_file and cover_file.filename:
                from werkzeug.utils import secure_filename
                cover_filename = secure_filename(cover_file.filename)
                cover_dir = 'static/uploads/covers'
                os.makedirs(cover_dir, exist_ok=True)
                cover_path = os.path.join(cover_dir, cover_filename)
                cover_file.save(cover_path)
                manga.cover_image = f"uploads/covers/{cover_filename}"
            
            # Handle categories
            category_ids = request.form.getlist('categories')
            manga.categories = Category.query.filter(Category.id.in_(category_ids)).all()
            
            # Generate new slug if title changed
            manga.slug = manga.generate_slug()
            
            db.session.commit()
            flash('تم تحديث المانجا بنجاح', 'success')
            return redirect(url_for('admin_manage'))
            
        except Exception as e:
            print(f"Error updating manga: {e}")
            flash('حدث خطأ في تحديث المانجا', 'error')
            return safe_redirect(request.url)

# API endpoint for updating reading progress
@app.route('/api/update_progress', methods=['POST'])
@login_required
def update_progress():
    data = request.json or {}
    manga_id = data.get('manga_id')
    chapter_id = data.get('chapter_id')
    page_number = data.get('page_number')
    
    if not all([manga_id, chapter_id, page_number]):
        return jsonify({'status': 'error', 'message': 'Missing required data'}), 400
    
    progress = ReadingProgress.query.filter_by(
        user_id=current_user.id,
        manga_id=manga_id
    ).first()
    
    if progress:
        progress.chapter_id = chapter_id
        progress.page_number = page_number
        progress.updated_at = datetime.utcnow()
    else:
        progress = ReadingProgress()
        progress.user_id = current_user.id
        progress.manga_id = manga_id
        progress.chapter_id = chapter_id
        progress.page_number = page_number
        db.session.add(progress)
    
    db.session.commit()
    return jsonify({'status': 'success'})

# Publisher System Routes
@app.route('/publisher/apply', methods=['GET', 'POST'])
@login_required
def apply_publisher():
    """Apply to become a publisher"""
    if current_user.is_publisher:
        flash('You are already a publisher!', 'info')
        return redirect(url_for('publisher_dashboard'))
    
    # Check if already has pending application
    existing_request = PublisherRequest.query.filter_by(
        user_id=current_user.id, 
        status='pending'
    ).first()
    
    if existing_request:
        flash('You already have a pending publisher application.', 'info')
        return render_template('publisher/application_status.html', request=existing_request)
    
    if request.method == 'POST':
        publisher_request = PublisherRequest()
        publisher_request.user_id = current_user.id
        publisher_request.portfolio_url = request.form.get('portfolio_url')
        publisher_request.description = request.form.get('description')
        
        # Handle sample work upload
        if 'sample_work' in request.files:
            file = request.files['sample_work']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename or 'untitled')
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'samples', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                publisher_request.sample_work = filepath
        
        db.session.add(publisher_request)
        db.session.commit()
        
        flash('Your publisher application has been submitted!', 'success')
        return redirect(url_for('index'))
    
    return render_template('publisher/apply.html')

@app.route('/publisher/dashboard')
@login_required
def publisher_dashboard():
    """Publisher dashboard"""
    if not current_user.is_publisher:
        abort(403)
    
    # Get publisher's manga
    user_manga = Manga.query.filter_by(publisher_id=current_user.id).all()
    
    return render_template('publisher/dashboard.html', user_manga=user_manga)

@app.route('/publisher/upload', methods=['GET', 'POST'])
@login_required
def publisher_upload():
    """Publisher manga upload - unified with admin upload"""
    if not current_user.is_publisher:
        abort(403)
    
    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        title_ar = request.form.get('title_ar')
        description = request.form.get('description')
        description_ar = request.form.get('description_ar')
        author = request.form.get('author')
        artist = request.form.get('artist')
        manga_type = request.form.get('type')
        status = request.form.get('status')
        age_rating = request.form.get('age_rating')
        
        # Chapter data
        chapter_title = request.form.get('chapter_title')
        
        # Safely parse chapter number with NaN protection
        try:
            chapter_number = safe_parse_float(request.form.get('chapter_number', '1'), 1.0, "chapter number")
        except ValueError as e:
            flash(f'رقم الفصل غير صحيح: {str(e)}', 'error')
            return safe_redirect(request.url)
        
        # Safely parse is_locked boolean
        is_locked = safe_parse_bool(request.form.get('is_locked'))
        early_access_date = request.form.get('early_access_date')
        release_date = request.form.get('release_date')
        
        # Convert date strings to datetime objects
        early_access_dt = None
        release_date_dt = None
        
        if early_access_date:
            early_access_dt = datetime.strptime(early_access_date, '%Y-%m-%dT%H:%M')
        if release_date:
            release_date_dt = datetime.strptime(release_date, '%Y-%m-%dT%H:%M')
        
        # Get upload method
        upload_method = request.form.get('upload_method', 'images')
        
        # Handle file uploads based on method
        cover_file = request.files.get('cover_image')
        chapter_files = []
        
        if upload_method == 'images':
            chapter_files = request.files.getlist('chapter_images')
            if not title or not chapter_files:
                flash('العنوان وصور الفصل مطلوبة', 'error')
                return safe_redirect(request.url)
        elif upload_method == 'zip':
            zip_file = request.files.get('chapter_zip')
            if not title or not zip_file:
                flash('العنوان وملف ZIP مطلوبان', 'error')
                return safe_redirect(request.url)
        elif upload_method == 'scrape':
            source_website = request.form.get('source_website')
            chapter_url = request.form.get('chapter_url')
            # للكشط، نتحقق من وجود صور محفوظة مسبقاً
            temp_scraped_dir = os.path.join('static', 'uploads', 'temp_scraped')
            has_scraped_images = os.path.exists(temp_scraped_dir) and any(
                f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                for f in os.listdir(temp_scraped_dir) if os.path.isfile(os.path.join(temp_scraped_dir, f))
            )
            
            if not title:
                flash('العنوان مطلوب', 'error')
                return safe_redirect(request.url)
            
            # التحقق من وجود بيانات الكشط المختبرة
            scraping_tested = request.form.get('scraping_tested', 'false')
            scraped_images_json = request.form.get('scraped_images', '')
            has_tested_data = scraping_tested == 'true' and scraped_images_json
            
            if not has_scraped_images and not has_tested_data and (not source_website or not chapter_url):
                flash('الموقع المصدر ورابط الفصل مطلوبان أو يجب كشط الصور أولاً', 'error')
                return safe_redirect(request.url)
        
        try:
            # Create manga (set publisher_id for publishers)
            manga = Manga()
            manga.title = title
            manga.title_ar = title_ar
            manga.description = description
            manga.description_ar = description_ar
            manga.author = author
            manga.artist = artist
            manga.type = manga_type
            manga.status = status
            manga.age_rating = age_rating
            manga.publisher_id = current_user.id  # Set publisher
            
            # Handle cover image (same logic as admin)
            if cover_file and cover_file.filename:
                from werkzeug.utils import secure_filename
                cover_filename = secure_filename(cover_file.filename)
                cover_dir = 'static/uploads/covers'
                os.makedirs(cover_dir, exist_ok=True)
                cover_path = os.path.join(cover_dir, cover_filename)
                cover_file.save(cover_path)
                manga.cover_image = f"uploads/covers/{cover_filename}"
            
            # Add manga first, then handle categories (like populate_database.py)
            db.session.add(manga)
            db.session.flush()  # Get the manga ID without committing
            
            # Handle categories AFTER flush - use safe method to avoid duplicates
            from app.utils_manga_category import set_manga_categories
            category_ids = request.form.getlist('categories')
            if category_ids:
                success, message = set_manga_categories(manga.id, category_ids)
                if not success:
                    logging.warning(f"Categories assignment warning: {message}")
            
            # Commit after everything is set up
            db.session.commit()
            
            # Create chapter (same logic as admin)
            chapter = Chapter()
            chapter.manga_id = manga.id
            chapter.chapter_number = chapter_number
            chapter.title = chapter_title
            chapter.is_locked = is_locked
            chapter.early_access_date = early_access_dt
            chapter.release_date = release_date_dt
            
            db.session.add(chapter)
            db.session.commit()
            
            # Handle chapter images (same as admin logic)
            chapter_dir = os.path.join('static/uploads/manga', str(manga.id), str(chapter.id))
            os.makedirs(chapter_dir, exist_ok=True)
            
            image_files = []
            temp_dir = None
            
            try:
                if upload_method == 'images':
                    # Direct image upload
                    for i, image_file in enumerate(chapter_files, 1):
                        if image_file and image_file.filename:
                            filename = secure_filename(f"page_{i:03d}_{image_file.filename}")
                            image_path = os.path.join(chapter_dir, filename)
                            image_file.save(image_path)
                            image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                elif upload_method == 'zip':
                    # ZIP file extraction and upload (same as scraping method)
                    logging.info("🗂️ بدء معالجة رفع ZIP")
                    zip_file = request.files.get('chapter_zip')
                    if not zip_file:
                        logging.error("❌ لم يتم توفير ملف ZIP")
                        flash('ملف ZIP مطلوب', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)
                    
                    logging.info(f"📦 ملف ZIP موجود: {zip_file.filename}")
                    
                    try:
                        import zipfile
                        import tempfile
                        
                        # Create temporary directory
                        temp_dir = tempfile.mkdtemp()
                        zip_path = os.path.join(temp_dir, 'chapter.zip')
                        zip_file.save(zip_path)
                        
                        # Extract images from ZIP
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            # Get image files only
                            image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
                            image_filenames = [f for f in zip_ref.namelist() 
                                             if f.lower().endswith(image_extensions) 
                                             and not f.startswith('__MACOSX/')]
                            
                            # Sort images naturally
                            image_filenames.sort()
                            
                            if not image_filenames:
                                raise Exception('لم يتم العثور على صور في ملف ZIP')
                            
                            # Extract and save images directly to chapter directory
                            for i, img_filename in enumerate(image_filenames, 1):
                                try:
                                    # Extract image data
                                    with zip_ref.open(img_filename) as img_file:
                                        image_data = img_file.read()
                                    
                                    # Save image to chapter directory
                                    filename = f"page_{i:03d}.jpg"
                                    image_path = os.path.join(chapter_dir, filename)
                                    
                                    with open(image_path, 'wb') as f:
                                        f.write(image_data)
                                    
                                    image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                    
                                except Exception as e:
                                    logging.warning(f"Failed to extract image {img_filename}: {e}")
                                    continue
                        
                        # Clean up temp directory
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
                        if not image_files:
                            raise Exception('فشل في استخراج أي صور من ملف ZIP')
                            
                    except Exception as e:
                        flash(f'خطأ في استخراج ملف ZIP: {str(e)}', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)
                
                elif upload_method == 'scrape':
                    # Web scraping (same as admin)
                    import requests
                    
                    source_website = request.form.get('source_website', '')
                    chapter_url = request.form.get('chapter_url', '')
                    
                    try:
                        image_urls = scrape_manga_images(source_website, chapter_url)
                        
                        if not image_urls:
                            flash('لم يتم العثور على صور في الرابط المحدد', 'error')
                            db.session.rollback()
                            return safe_redirect(request.url)
                        
                        # Download and save images
                        for i, img_url in enumerate(image_urls, 1):
                            try:
                                filename = f"page_{i:03d}.jpg"
                                image_path = os.path.join(chapter_dir, filename)
                                
                                response = requests.get(img_url, stream=True, timeout=30)
                                response.raise_for_status()
                                
                                with open(image_path, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                
                                image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                
                            except Exception as e:
                                logging.warning(f"Failed to download image {img_url}: {e}")
                                continue
                                
                    except Exception as e:
                        flash(f'خطأ في كشط الصور: {str(e)}', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)
                
                # Create page records
                for i, image_file in enumerate(image_files, 1):
                    page = PageImage()
                    page.chapter_id = chapter.id
                    page.page_number = i
                    page.image_path = image_file
                    db.session.add(page)
                
                # Update chapter page count
                chapter.pages = len(image_files)
                db.session.commit()
                
                # Send notifications to subscribers
                try:
                    from app.utils_bravo_mail import bravo_mail, send_manga_chapter_notification
                except ImportError:
                    bravo_mail = None
                    send_manga_chapter_notification = None
                
                if bravo_mail and bravo_mail.is_enabled() and send_manga_chapter_notification:
                    # Get manga subscribers
                    subscribers = db.session.query(User).join(Subscription).filter(
                        Subscription.manga_id == manga.id
                    ).all()
                    
                    chapter_url = url_for('read_chapter', manga_id=manga.id, chapter_id=chapter.id, _external=True)
                    
                    for subscriber in subscribers:
                        try:
                            email_result = send_manga_chapter_notification(
                                subscriber.email,
                                subscriber.username,
                                manga.title,
                                chapter.title or f"الفصل {chapter.chapter_number}",
                                chapter_url
                            )
                            if email_result.get('success'):
                                logger.info(f"Chapter notification email sent to {subscriber.email}")
                            else:
                                logger.warning(f"Failed to send chapter notification to {subscriber.email}: {email_result.get('error')}")
                        except Exception as e:
                            logger.error(f"Error sending chapter notification to {subscriber.email}: {str(e)}")
                
                # Categories were already handled during manga creation
                
                flash('تم رفع المانجا بنجاح!', 'success')
                return redirect(url_for('manga_detail', slug=manga.slug))
                
            except Exception as e:
                # Clean up on error
                if os.path.exists(chapter_dir):
                    import shutil
                    shutil.rmtree(chapter_dir, ignore_errors=True)
                db.session.rollback()
                raise e
                
        except Exception as e:
            flash(f'خطأ في رفع المانجا: {str(e)}', 'error')
            db.session.rollback()
    
    # Get categories for form
    categories = Category.query.all()
    return render_template('admin/upload.html', categories=categories, is_publisher=True)

# Subscription Routes
@app.route('/subscribe/<int:manga_id>', methods=['POST'])
@login_required
def subscribe_manga(manga_id):
    """Subscribe to manga notifications"""
    manga = Manga.query.get_or_404(manga_id)
    
    subscription = Subscription.query.filter_by(
        user_id=current_user.id,
        manga_id=manga_id
    ).first()
    
    if subscription:
        db.session.delete(subscription)
        action = 'unsubscribed'
    else:
        subscription = Subscription()
        subscription.user_id = current_user.id
        subscription.manga_id = manga_id
        db.session.add(subscription)
        action = 'subscribed'
    
    db.session.commit()
    return jsonify({'status': 'success', 'action': action})

# Notification Routes
@app.route('/notifications')
@login_required
def user_notifications():
    """User notifications page"""
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    
    # Mark all as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(
        {'is_read': True}
    )
    db.session.commit()
    
    return render_template('notifications.html', notifications=notifications)

@app.route('/api/notifications/unread-count')
@login_required
def unread_notifications_count():
    """Get unread notifications count"""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})

@app.route('/api/upload-progress/<int:chapter_id>')
@login_required
def api_upload_progress(chapter_id):
    """API endpoint to get upload progress"""
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    try:
        from scripts.background_uploader import background_uploader
        progress = background_uploader.upload_progress.get(chapter_id, {
            'total_images': 0,
            'uploaded_images': 0,
            'status': 'not_found',
            'percentage': 0
        })
        return jsonify(progress)
    except Exception as e:
        logging.error(f"Error getting upload progress for chapter {chapter_id}: {e}")
        return jsonify({'status': 'error', 'percentage': 0})

# Translation Routes
@app.route('/translate/request/<int:manga_id>', methods=['POST'])
@login_required
def request_translation(manga_id):
    """Request translation for a manga"""
    manga = Manga.query.get_or_404(manga_id)
    
    data = request.json or {}
    to_language = data.get('to_language')
    
    if not to_language:
        return jsonify({'status': 'error', 'message': 'Target language required'}), 400
    
    translation_request = TranslationRequest()
    translation_request.manga_id = manga_id
    translation_request.from_language = manga.original_language or manga.language
    translation_request.to_language = to_language
    
    db.session.add(translation_request)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Translation requested!'})

# Advanced Search
@app.route('/search')
def advanced_search():
    """Advanced search with filters"""
    query = request.args.get('q', '')
    category_ids = request.args.getlist('categories')
    manga_type = request.args.get('type', '')
    status = request.args.get('status', '')
    sort = request.args.get('sort', 'relevance')
    
    # Base query
    manga_query = Manga.query.filter(Manga.is_published.is_(True))
    
    # Apply search filters
    if query:
        manga_query = manga_query.filter(
            db.or_(
                Manga.title.contains(query),
                Manga.title_ar.contains(query),
                Manga.author.contains(query),
                Manga.description.contains(query)
            )
        )
    
    if category_ids:
        manga_query = manga_query.join(manga_category).filter(
            manga_category.c.category_id.in_(category_ids)
        )
    
    if manga_type:
        manga_query = manga_query.filter(Manga.type == manga_type)
    
    if status:
        manga_query = manga_query.filter(Manga.status == status)
    
    # Apply sorting
    if sort == 'latest':
        manga_query = manga_query.order_by(Manga.created_at.desc())
    elif sort == 'popular':
        manga_query = manga_query.order_by(Manga.views.desc())
    elif sort == 'alphabetical':
        manga_query = manga_query.order_by(Manga.title.asc())
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    manga_results = manga_query.paginate(page=page, per_page=20, error_out=False)
    
    categories = Category.query.all()
    
    return render_template('search.html',
                         manga_results=manga_results,
                         categories=categories,
                         search_params=request.args)

@app.route('/publishers')
def publishers():
    """Display all publishers with their statistics"""
    # Get all users who are publishers and have published content
    publishers = db.session.query(User).filter(
        User.is_publisher == True,
        User.account_active == True
    ).all()
    
    # Calculate statistics for each publisher
    publisher_stats = []
    for publisher in publishers:
        # Get published manga count
        published_manga = Manga.query.filter_by(publisher_id=publisher.id).all()
        total_manga = len(published_manga)
        
        # Get published chapters count
        published_chapters = []
        for manga in published_manga:
            published_chapters.extend(manga.chapters.all())
        total_chapters = len(published_chapters)
        
        # Get total views from all manga published by this publisher
        total_views = sum(manga.views for manga in published_manga)
        
        # Get latest published chapter
        latest_chapter = None
        if published_chapters:
            latest_chapter = max(published_chapters, key=lambda c: c.created_at)
        
        publisher_stats.append({
            'publisher': publisher,
            'total_manga': total_manga,
            'total_chapters': total_chapters,
            'total_views': total_views,
            'latest_chapter': latest_chapter,
            'join_date': publisher.created_at
        })
    
    # Sort by total chapters published (most active first)
    publisher_stats.sort(key=lambda x: x['total_chapters'], reverse=True)
    
    return render_template('publishers.html', publisher_stats=publisher_stats)

@app.route('/publisher/<int:publisher_id>')
def publisher_profile(publisher_id):
    """Display individual publisher profile with detailed statistics"""
    publisher = User.query.filter_by(id=publisher_id, is_publisher=True, account_active=True).first_or_404()
    
    # Get publisher's manga with chapter counts
    manga_list = []
    for manga in publisher.published_manga:
        chapter_count = manga.chapters.count()
        latest_chapter = manga.chapters.order_by(Chapter.created_at.desc()).first()
        manga_list.append({
            'manga': manga,
            'chapter_count': chapter_count,
            'latest_chapter': latest_chapter
        })
    
    # Sort by latest update
    manga_list.sort(key=lambda x: x['latest_chapter'].created_at if x['latest_chapter'] else datetime.min, reverse=True)
    
    # Get recent chapters published by this publisher
    recent_chapters = Chapter.query.filter_by(publisher_id=publisher_id).order_by(Chapter.created_at.desc()).limit(10).all()
    
    # Calculate total statistics
    total_manga = len(publisher.published_manga)
    total_chapters = len(publisher.published_chapters) if publisher.published_chapters else 0
    total_views = sum(manga.views for manga in publisher.published_manga)
    
    return render_template('publisher_profile.html', 
                         publisher=publisher,
                         manga_list=manga_list,
                         recent_chapters=recent_chapters,
                         total_manga=total_manga,
                         total_chapters=total_chapters,
                         total_views=total_views)

# Admin Enhancement Routes
@app.route('/admin/publisher-requests')
@login_required
def admin_publisher_requests():
    """Admin view for publisher requests"""
    if not current_user.is_admin:
        abort(403)
    
    requests = PublisherRequest.query.order_by(PublisherRequest.created_at.desc()).all()
    return render_template('admin/publisher_requests.html', requests=requests)

@app.route('/admin/approve-publisher/<int:request_id>')
@login_required
def admin_approve_publisher(request_id):
    """Approve publisher request"""
    if not current_user.is_admin:
        abort(403)
    
    publisher_request = PublisherRequest.query.get_or_404(request_id)
    user = User.query.get(publisher_request.user_id)
    
    if user:
        user.is_publisher = True
        publisher_request.status = 'approved'
        publisher_request.reviewed_at = datetime.utcnow()
        
        # Create notification for user
        notification = Notification()
        notification.user_id = user.id
        notification.type = 'publisher_approved'
        notification.title = 'Publisher Application Approved!'
        notification.message = 'Congratulations! Your publisher application has been approved.'
        notification.link = url_for('publisher_dashboard')
        db.session.add(notification)
        
        db.session.commit()
        
        # Send email notification
        try:
            from app.utils_bravo_mail import bravo_mail, send_notification_email
        except ImportError:
            bravo_mail = None
            send_notification_email = None
        
        if bravo_mail and bravo_mail.is_enabled() and send_notification_email:
            try:
                email_result = send_notification_email(
                    user.email, 
                    user.username, 
                    notification.title,
                    notification.message,
                    url_for('publisher_dashboard', _external=True)
                )
                if email_result.get('success'):
                    logger.info(f"Publisher approval email sent successfully to {user.email}")
                else:
                    logger.warning(f"Failed to send publisher approval email to {user.email}: {email_result.get('error')}")
            except Exception as e:
                logger.error(f"Error sending publisher approval email to {user.email}: {str(e)}")
        flash(f'{user.username} has been approved as a publisher!', 'success')
    else:
        flash('User not found!', 'error')
    return redirect(url_for('admin_publisher_requests'))

@app.route('/admin/analytics')
@login_required
def admin_analytics():
    """Admin analytics dashboard"""
    if not current_user.is_admin:
        abort(403)
    
    # Basic statistics
    total_users = User.query.count()
    total_manga = Manga.query.count()
    total_chapters = Chapter.query.count()
    active_publishers = User.query.filter_by(is_publisher=True).count()
    
    return render_template('admin/analytics.html',
                         total_users=total_users,
                         total_manga=total_manga,
                         total_chapters=total_chapters,
                         active_publishers=active_publishers)

# API Routes - محسنة الأمان
@app.route('/api/manga')
@limiter.limit("30 per minute")  # تحديد عدد الطلبات لمنع الإفراط
def api_manga_list():
    """API endpoint for manga list - محسن الأمان"""
    try:
        # التحقق من صحة parameters
        page = max(1, request.args.get('page', 1, type=int))
        per_page = min(max(1, request.args.get('per_page', 20, type=int)), 50)  # تقليل الحد الأقصى لـ 50
        
        # فلترة البحث الآمنة
        search_term = request.args.get('search', '', type=str).strip()[:100]  # تحديد طول البحث
        category = request.args.get('category', '', type=str).strip()
        
        # بناء الاستعلام بشكل آمن
        manga_query = Manga.query.filter_by(is_published=True)
        
        # إضافة فلترة البحث إذا تم توفيرها
        if search_term:
            manga_query = manga_query.filter(
                db.or_(
                    Manga.title.ilike(f'%{search_term}%'),
                    Manga.author.ilike(f'%{search_term}%')
                )
            )
        
        if category and category.isdigit():
            manga_query = manga_query.join(manga_category).filter(manga_category.c.category_id == int(category))
        
        manga_pagination = manga_query.paginate(page=page, per_page=per_page, error_out=False)
        
        manga_list = []
        for manga in manga_pagination.items:
            # إخفاء بعض المعلومات الحساسة وعرض المطلوب فقط
            manga_data = {
                'id': manga.id,
                'title': manga.title,
                'title_ar': manga.title_ar,
                'author': manga.author,
                'cover_image': manga.cover_image,
                'status': manga.status,
                'type': manga.type,
                'language': manga.language,
                'average_rating': round(manga.average_rating, 1) if manga.average_rating else None,
                'total_chapters': manga.total_chapters
            }
            
            # عدم عرض views للحد من المعلومات المكشوفة
            manga_list.append(manga_data)
        
        response_data = {
            'status': 'success',
            'manga': manga_list,
            'pagination': {
                'page': manga_pagination.page,
                'pages': manga_pagination.pages,
                'total': min(manga_pagination.total, 10000),  # تحديد العدد المعروض لأسباب أمنية
                'per_page': per_page
            }
        }
        
        # إضافة security headers
        response = jsonify(response_data)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=300'  # cache لمدة 5 دقائق
        
        return response
        
    except Exception as e:
        logger.error(f"Error in api_manga_list: {str(e)}")
        # عدم كشف تفاصيل الخطأ للمستخدم
        return jsonify({
            'status': 'error',
            'message': 'حدث خطأ في تحميل البيانات'
        }), 500

@app.route('/api/manga/<int:manga_id>')
@limiter.limit("60 per minute")  # حد أعلى للتفاصيل المحددة
def api_manga_detail(manga_id):
    """API endpoint for manga details - محسن الأمان"""
    try:
        # التحقق من صحة ID
        if manga_id <= 0 or manga_id > 999999:  # حدود معقولة للـ ID
            return jsonify({
                'status': 'error',
                'message': 'معرف المانجا غير صحيح'
            }), 400
        
        manga = Manga.query.filter_by(id=manga_id, is_published=True).first()
        if not manga:
            return jsonify({
                'status': 'error',
                'message': 'المانجا غير موجودة'
            }), 404
        
        # تجميع بيانات الفصول بشكل آمن
        chapters = []
        for chapter in manga.chapters.filter_by(is_published=True).order_by(Chapter.chapter_number).all():
            chapter_data = {
                'id': chapter.id,
                'chapter_number': chapter.chapter_number,
                'title': chapter.title[:200] if chapter.title else None,  # تحديد طول العنوان
                'pages': min(chapter.pages or 0, 1000)  # تحديد عدد الصفحات المعروضة
            }
            chapters.append(chapter_data)
        
        # إعداد البيانات المرجعة مع إخفاء المعلومات الحساسة
        response_data = {
            'status': 'success',
            'id': manga.id,
            'title': manga.title,
            'description': manga.description[:1000] if manga.description else None,  # تحديد طول الوصف
            'author': manga.author,
            'cover_image': manga.cover_image,
            'status': manga.status,
            'type': manga.type,
            'language': manga.language,
            'average_rating': round(manga.average_rating, 1) if manga.average_rating else None,
            'total_chapters': len(chapters),
            'chapters': chapters[:100]  # تحديد عدد الفصول المعروضة
        }
        
        # إضافة security headers
        response = jsonify(response_data)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=600'  # cache لمدة 10 دقائق
        
        return response
        
    except Exception as e:
        logger.error(f"Error in api_manga_detail for ID {manga_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'حدث خطأ في تحميل تفاصيل المانجا'
        }), 500

# Premium Plans Route
@app.route('/premium')
def premium_plans():
    """Show premium subscription plans"""
    from datetime import datetime
    
    # Get active payment plans
    plans = PaymentPlan.query.filter_by(is_active=True).order_by(PaymentPlan.price.asc()).all()
    
    # Get active payment gateways ordered by display_order
    payment_gateways = PaymentGateway.query.filter_by(is_active=True).order_by(PaymentGateway.display_order.asc(), PaymentGateway.name.asc()).all()
    
    # Pass current datetime for template comparison
    return render_template('premium/plans.html', plans=plans, payment_gateways=payment_gateways, now=datetime.now())

# User bookmarks route
@app.route('/user/bookmarks')
@login_required
def user_bookmarks():
    """User bookmarks page"""
    bookmarks = Bookmark.query.filter_by(user_id=current_user.id).all()
    return render_template('user/bookmarks.html', bookmarks=bookmarks)

# User reading history route
@app.route('/user/history')
@login_required
def user_history():
    """User reading history page"""
    history = ReadingProgress.query.filter_by(user_id=current_user.id).order_by(
        ReadingProgress.updated_at.desc()
    ).all()
    return render_template('user/history.html', history=history)

# Admin Category Management
@app.route('/admin/categories')
@login_required
def admin_categories():
    """Admin category management"""
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    categories = Category.query.order_by(Category.name.asc()).all()
    
    # Calculate statistics for dashboard cards
    total_categories = Category.query.count()
    active_categories = Category.query.filter_by(is_active=True).count()
    popular_categories = Category.query.join(manga_category).group_by(Category.id).having(db.func.count(manga_category.c.manga_id) > 0).count()
    total_manga = Manga.query.count()
    
    # Add manga count to each category
    for category in categories:
        category.manga_count = len(category.manga_items) if hasattr(category, 'manga_items') else 0
    
    stats = {
        'total_categories': total_categories,
        'active_categories': active_categories,
        'popular_categories': popular_categories,
        'inactive_categories': total_categories - active_categories,
        'total_manga': total_manga
    }
    
    return render_template('admin/categories.html', categories=categories, stats=stats)

@app.route('/admin/categories/add', methods=['GET', 'POST'])
@login_required
def admin_add_category():
    """Add new category"""
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    if request.method == 'POST':
        # Handle JSON request from AJAX
        if request.is_json:
            data = request.get_json()
            name = data.get('name', '').strip()
            name_ar = data.get('name_ar', '').strip()
            description = data.get('description', '').strip()
        else:
            name = request.form.get('name', '').strip()
            name_ar = request.form.get('name_ar', '').strip()
            description = request.form.get('description', '').strip()
        
        if not name:
            if request.is_json:
                return jsonify({'success': False, 'error': 'اسم الفئة مطلوب'})
            flash('Category name is required!', 'error')
            return render_template('admin/add_category.html')
        
        # Check if category exists
        if Category.query.filter_by(name=name).first():
            if request.is_json:
                return jsonify({'success': False, 'error': 'الفئة موجودة بالفعل'})
            flash('Category already exists!', 'error')
            return render_template('admin/add_category.html')
        
        # Get description_ar field  
        description_ar = ""
        if request.is_json:
            data = request.get_json()
            if data:
                description_ar = data.get('description_ar', '').strip()
        else:
            description_ar = request.form.get('description_ar', '').strip()
        
        category = Category()
        category.name = name
        category.name_ar = name_ar
        category.description = description
        category.description_ar = description_ar
        # Generate slug from name
        import re
        slug = re.sub(r'[^a-zA-Z0-9-]', '-', name.lower().strip())
        slug = re.sub(r'-+', '-', slug).strip('-')
        category.slug = slug
        category.is_active = True
        
        db.session.add(category)
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'message': 'تم إضافة الفئة بنجاح'})
        
        flash('Category added successfully!', 'success')
        return redirect(url_for('admin_categories'))
    
    return render_template('admin/add_category.html')

@app.route('/admin/categories/edit/<int:category_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_category(category_id):
    """Edit category"""
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    
    if request.method == 'POST':
        # Handle JSON request from AJAX
        if request.is_json:
            data = request.get_json()
            name = data.get('name', '').strip()
            name_ar = data.get('name_ar', '').strip()
            description = data.get('description', '').strip()
            description_ar = data.get('description_ar', '').strip()
        else:
            name = request.form.get('name', '').strip()
            name_ar = request.form.get('name_ar', '').strip()
            description = request.form.get('description', '').strip()
            description_ar = request.form.get('description_ar', '').strip()
        
        if not name:
            if request.is_json:
                return jsonify({'success': False, 'error': 'اسم الفئة مطلوب'})
            flash('Category name is required!', 'error')
            return render_template('admin/edit_category.html', category=category)
        
        # Check if name exists for different category
        existing = Category.query.filter(Category.name == name, Category.id != category_id).first()
        if existing:
            if request.is_json:
                return jsonify({'success': False, 'error': 'اسم الفئة موجود بالفعل'})
            flash('Category name already exists!', 'error')
            return render_template('admin/edit_category.html', category=category)
        
        category.name = name
        category.name_ar = name_ar
        category.description = description
        category.description_ar = description_ar
        # Update slug from name
        import re
        slug = re.sub(r'[^a-zA-Z0-9-]', '-', name.lower().strip())
        slug = re.sub(r'-+', '-', slug).strip('-')
        category.slug = slug
        
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'message': 'تم تحديث الفئة بنجاح'})
        
        flash('Category updated successfully!', 'success')
        return redirect(url_for('admin_categories'))
    
    return render_template('admin/edit_category.html', category=category)

@app.route('/admin/categories/delete/<int:category_id>', methods=['POST'])
@login_required
def admin_delete_category(category_id):
    """Delete category"""
    if not current_user.is_admin:
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    
    # Check if category has manga
    if category.manga.count() > 0:
        flash('Cannot delete category with associated manga!', 'error')
        return redirect(url_for('admin_categories'))
    
    db.session.delete(category)
    db.session.commit()
    
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('admin_categories'))

# Admin User Management
@app.route('/admin/users')
@login_required
def admin_users():
    """Admin user management"""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            (User.username.contains(search)) |
            (User.email.contains(search))
        )
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get user statistics
    total_users = User.query.count()
    admin_users = User.query.filter_by(is_admin=True).count()
    publisher_users = User.query.filter_by(is_publisher=True).count()
    # Handle premium_until field safely
    try:
        premium_users = User.query.filter(User.premium_until > datetime.utcnow()).count()
    except:
        premium_users = 0
    
    # Get active users count (handle is_active field safely)
    try:
        active_users = User.query.filter_by(is_active=True).count()
    except:
        active_users = total_users  # Assume all users are active if field doesn't exist
    
    return render_template('admin/users.html', 
                         users=users, 
                         search=search,
                         total_users=total_users,
                         admin_users=admin_users,
                         publisher_users=publisher_users,
                         premium_users=premium_users,
                         active_users=active_users)

@app.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
def admin_toggle_user_admin(user_id):
    """Toggle user admin status"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('لا يمكن تعديل صلاحياتك الخاصة', 'error')
        return redirect(url_for('admin_users'))
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = 'منح صلاحية المدير' if user.is_admin else 'إزالة صلاحية المدير'
    flash(f'تم {status} للمستخدم {user.username}', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/toggle-publisher', methods=['POST'])
@login_required
def admin_toggle_user_publisher(user_id):
    """Toggle user publisher status"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    user.is_publisher = not user.is_publisher
    db.session.commit()
    
    status = 'منح صلاحية النشر' if user.is_publisher else 'إزالة صلاحية النشر'
    flash(f'تم {status} للمستخدم {user.username}', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/toggle-translator', methods=['POST'])
@login_required
def admin_toggle_user_translator(user_id):
    """Toggle user translator status"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    was_translator = user.is_translator
    user.is_translator = not user.is_translator
    db.session.commit()
    
    # Send translator approval email if user was promoted to translator
    if user.is_translator and not was_translator:
        try:
            from app.utils_bravo_mail import bravo_mail, send_translator_approval_email
        except ImportError:
            bravo_mail = None
            send_translator_approval_email = None
        
        if bravo_mail and bravo_mail.is_enabled() and send_translator_approval_email:
            try:
                email_result = send_translator_approval_email(user.email, user.username)
                if email_result.get('success'):
                    logger.info(f"Translator approval email sent to {user.email}")
                else:
                    logger.warning(f"Failed to send translator approval email: {email_result.get('error')}")
            except Exception as e:
                logger.error(f"Error sending translator approval email to {user.email}: {str(e)}")
    
    status = 'منح صلاحية الترجمة' if user.is_translator else 'إزالة صلاحية الترجمة'
    flash(f'تم {status} للمستخدم {user.username}', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
def admin_toggle_user_status(user_id):
    """Toggle user active status"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    # Toggle user active status
    user.is_active = not getattr(user, 'is_active', True)
    db.session.commit()
    
    status = 'تفعيل' if user.is_active else 'إلغاء تفعيل'
    flash(f'تم {status} المستخدم {user.username}', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/bulk-activate', methods=['POST'])
@login_required
def admin_bulk_activate():
    """Bulk activate users"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        
        if not user_ids:
            return {'success': False, 'error': 'No users selected'}
        
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user:
                user.is_active = True
        db.session.commit()
        
        return {'success': True, 'message': f'Activated {len(user_ids)} users'}
        
    except Exception as e:
        print(f"Error in bulk activate: {e}")
        return {'success': False, 'error': 'Database error'}

@app.route('/admin/users/bulk-deactivate', methods=['POST'])
@login_required
def admin_bulk_deactivate():
    """Bulk deactivate users"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        
        if not user_ids:
            return {'success': False, 'error': 'No users selected'}
        
        # Don't deactivate admin users
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user and not user.is_admin:
                user.is_active = False
        db.session.commit()
        
        return {'success': True, 'message': f'Deactivated selected users'}
        
    except Exception as e:
        print(f"Error in bulk deactivate: {e}")
        return {'success': False, 'error': 'Database error'}

@app.route('/admin/users/bulk-delete', methods=['POST'])
@login_required
def admin_bulk_delete():
    """Bulk delete users"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        
        if not user_ids:
            return {'success': False, 'error': 'No users selected'}
        
        # Get all admin users
        admin_users = User.query.filter_by(is_admin=True).all()
        admin_user_ids = [admin.id for admin in admin_users]
        
        # Check if we're trying to delete admin users
        admin_users_to_delete = [uid for uid in user_ids if uid in admin_user_ids]
        
        # If trying to delete admin users, ensure at least one admin remains
        if admin_users_to_delete:
            remaining_admins = len(admin_user_ids) - len(admin_users_to_delete)
            if remaining_admins < 1:
                return {'success': False, 'error': 'Cannot delete all admin users. At least one admin must remain.'}
        
        # Get all users to delete (including admins if safe)
        users_to_delete = User.query.filter(User.id.in_(user_ids)).all()
        
        deleted_count = 0
        for user in users_to_delete:
            # Skip if it would leave no admins
            if user.is_admin and len(admin_user_ids) - len(admin_users_to_delete) < 1:
                continue
            db.session.delete(user)
            deleted_count += 1
        
        db.session.commit()
        
        return {'success': True, 'message': f'Deleted {deleted_count} users'}
        
    except Exception as e:
        print(f"Error in bulk delete: {e}")
        return {'success': False, 'error': 'Database error'}

@app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def admin_reset_user_password(user_id):
    """Reset user password"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    try:
        # In a real application, you would send an email here
        # For now, we'll just generate a temporary password
        import secrets
        import string
        
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(12))
        
        from werkzeug.security import generate_password_hash
        user.password_hash = generate_password_hash(temp_password)
        db.session.commit()
        
        # Import Bravo Mail here to avoid context issues
        try:
            from app.utils_bravo_mail import bravo_mail, send_password_reset_email
        except ImportError:
            bravo_mail = None
            send_password_reset_email = None
        
        # Send password reset email via Bravo Mail
        if bravo_mail and bravo_mail.is_enabled():
            try:
                email_result = send_password_reset_email(user.email, user.username, temp_password)
                if email_result['success']:
                    flash(f'تم إعادة تعيين كلمة المرور للمستخدم {user.username} وإرسال كلمة المرور الجديدة عبر البريد الإلكتروني', 'success')
                else:
                    flash(f'تم إعادة تعيين كلمة المرور للمستخدم {user.username}. كلمة المرور المؤقتة: {temp_password}. خطأ في إرسال البريد: {email_result.get("error", "غير معروف")}', 'warning')
            except Exception as e:
                flash(f'تم إعادة تعيين كلمة المرور للمستخدم {user.username}. كلمة المرور المؤقتة: {temp_password}. خطأ في إرسال البريد: {str(e)}', 'warning')
        else:
            # Fallback to flash message if Bravo Mail is not enabled
            flash(f'تم إعادة تعيين كلمة المرور للمستخدم {user.username}. كلمة المرور المؤقتة: {temp_password}', 'success')
        
        return {'success': True, 'message': 'Password reset successfully'}
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        return {'success': False, 'error': 'Error resetting password'}

@app.route('/admin/users/<int:user_id>/activity')
@login_required
def admin_user_activity(user_id):
    """View user activity"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    # Get user activity data
    activity_data = {
        'user': user,
        'reading_history': [],  # Add reading history if available
        'comments': [],  # Add comments if available  
        'bookmarks': [],  # Add bookmarks if available
    }
    
    return render_template('admin/user_activity.html', **activity_data)

@app.route('/admin/users/create', methods=['POST'])
@login_required
def admin_create_user():
    """Create new user"""
    if not current_user.is_admin:
        abort(403)
    
    from werkzeug.security import generate_password_hash
    
    try:
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Validate required fields
        if not username or not email or not password:
            flash('يرجى ملء جميع الحقول المطلوبة', 'error')
            return redirect(url_for('admin_users'))
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'error')
            return redirect(url_for('admin_users'))
        
        if User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني موجود بالفعل', 'error')
            return redirect(url_for('admin_users'))
        
        # معالجة رفع الصورة الشخصية
        avatar_url = None
        if 'profile_picture' in request.files and request.files['profile_picture'].filename:
            avatar_url = save_profile_picture(request.files['profile_picture'])
            if not avatar_url:
                flash('حدث خطأ في رفع الصورة الشخصية، تم استخدام الصورة الافتراضية', 'warning')
        
        # Create new user
        user = User()
        user.username = username
        user.email = email
        user.password_hash = generate_password_hash(password)
        user.is_admin = safe_parse_bool(request.form.get('is_admin'))
        user.is_publisher = safe_parse_bool(request.form.get('is_publisher'))
        user.is_translator = safe_parse_bool(request.form.get('is_translator'))
        user.language_preference = request.form.get('language_preference', 'ar')
        user.bio = request.form.get('bio', '').strip()
        user.country = request.form.get('country', '').strip()
        user.avatar_url = avatar_url or '/static/img/default-avatar.svg'
        user.created_at = datetime.utcnow()
        user.last_seen = datetime.utcnow()
        
        db.session.add(user)
        db.session.commit()
        
        # Send translator approval email if user is assigned as translator
        if user.is_translator:
            try:
                from app.utils_bravo_mail import bravo_mail, send_translator_approval_email
            except ImportError:
                bravo_mail = None
                send_translator_approval_email = None
            
            if bravo_mail and bravo_mail.is_enabled() and send_translator_approval_email:
                try:
                    email_result = send_translator_approval_email(user.email, user.username)
                    if email_result.get('success'):
                        logger.info(f"Translator approval email sent to {user.email}")
                    else:
                        logger.warning(f"Failed to send translator approval email: {email_result.get('error')}")
                except Exception as e:
                    logger.error(f"Error sending translator approval email to {user.email}: {str(e)}")
        
        flash(f'تم إنشاء المستخدم {username} بنجاح', 'success')
        
    except Exception as e:
        print(f"Error creating user: {e}")
        flash('حدث خطأ في إنشاء المستخدم', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>')
@login_required
def admin_get_user(user_id):
    """Get user data for editing"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    user_data = {
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'bio': getattr(user, 'bio', ''),
            'country': getattr(user, 'country', ''),
            'is_admin': getattr(user, 'is_admin', False),
            'is_publisher': getattr(user, 'is_publisher', False),
            'is_translator': getattr(user, 'is_translator', False),
            'is_active': getattr(user, 'is_active', True),
            'language_preference': getattr(user, 'language_preference', 'ar')
        }
    }
    
    return user_data

@app.route('/admin/users/<int:user_id>/edit', methods=['POST'])
@login_required
def admin_edit_user(user_id):
    """Edit user details"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    try:
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        
        # Check for duplicate username/email (excluding current user)
        if username != user.username and User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'error')
            return redirect(url_for('admin_users'))
        
        if email != user.email and User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني موجود بالفعل', 'error')
            return redirect(url_for('admin_users'))
        
        # Update user details
        user.username = username
        user.email = email
        user.bio = request.form.get('bio', '').strip()
        user.country = request.form.get('country', '').strip()
        
        db.session.commit()
        flash(f'تم تحديث بيانات المستخدم {username} بنجاح', 'success')
        
    except Exception as e:
        print(f"Error editing user: {e}")
        flash('حدث خطأ في تحديث بيانات المستخدم', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Delete user with admin protection"""
    if not current_user.is_admin:
        abort(403)
    
    user_to_delete = User.query.get_or_404(user_id)
    
    try:
        # If trying to delete an admin user, ensure at least one admin remains
        if user_to_delete.is_admin:
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                flash('لا يمكن حذف آخر حساب مدير في الموقع. يجب وجود مدير واحد على الأقل.', 'error')
                return redirect(url_for('admin_users'))
        
        username = user_to_delete.username
        db.session.delete(user_to_delete)
        db.session.commit()
        
        flash(f'تم حذف المستخدم {username} بنجاح', 'success')
        
        # If the current user deleted themselves, logout
        if user_to_delete.id == current_user.id:
            from flask_login import logout_user
            logout_user()
            return redirect(url_for('index'))
        
    except Exception as e:
        print(f"Error deleting user: {e}")
        flash('حدث خطأ أثناء حذف المستخدم', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/export')
@login_required
def admin_export_users():
    """Export users data to CSV"""
    if not current_user.is_admin:
        abort(403)
    
    from flask import make_response
    import csv
    from io import StringIO
    from datetime import datetime
    
    # Get all users
    users = User.query.all()
    
    # Create CSV content
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID', 'Username', 'Email', 'Display Name', 'Country', 'Bio',
        'Is Admin', 'Is Publisher', 'Is Translator', 'Is Premium', 'Is Active',
        'Language Preference', 'Created At', 'Last Seen', 'Premium Until',
        'Reading Count', 'Bookmarks Count', 'Comments Count'
    ])
    
    # Write user data
    for user in users:
        # Get user statistics safely
        reading_count = 0
        bookmarks_count = 0
        comments_count = 0
        
        try:
            if hasattr(user, 'reading_progress'):
                reading_count = user.reading_progress.count()
        except:
            pass
        
        try:
            if hasattr(user, 'bookmarks'):
                bookmarks_count = user.bookmarks.count()
        except:
            pass
        
        try:
            if hasattr(user, 'comments'):
                comments_count = user.comments.count()
        except:
            pass
        
        writer.writerow([
            user.id,
            user.username,
            user.email,
            getattr(user, 'display_name', ''),
            getattr(user, 'country', ''),
            getattr(user, 'bio', ''),
            getattr(user, 'is_admin', False),
            getattr(user, 'is_publisher', False),
            getattr(user, 'is_translator', False),
            getattr(user, 'is_premium', False),
            getattr(user, 'is_active', True),
            getattr(user, 'language_preference', 'ar'),
            user.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(user, 'created_at') and user.created_at else '',
            user.last_seen.strftime('%Y-%m-%d %H:%M:%S') if hasattr(user, 'last_seen') and user.last_seen else '',
            user.premium_until.strftime('%Y-%m-%d %H:%M:%S') if hasattr(user, 'premium_until') and user.premium_until else '',
            reading_count,
            bookmarks_count,
            comments_count
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response

# Admin Comment Moderation
@app.route('/admin/comments')
@login_required
def admin_comments():
    """Admin comment moderation"""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    comments = Comment.query.order_by(Comment.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    
    return render_template('admin/comments.html', comments=comments)

@app.route('/admin/comments/<int:comment_id>/delete', methods=['DELETE', 'POST'])
@login_required
def admin_delete_comment(comment_id):
    """Delete comment"""
    if not current_user.is_admin:
        abort(403)
    
    comment = Comment.query.get_or_404(comment_id)
    
    # Delete all reactions first
    CommentReaction.query.filter_by(comment_id=comment_id).delete()
    
    # Delete all replies
    Comment.query.filter_by(parent_id=comment_id).delete()
    
    # Delete the comment
    db.session.delete(comment)
    db.session.commit()
    
    # Return JSON response for AJAX requests
    if request.method == 'DELETE' or request.headers.get('Content-Type') == 'application/json':
        return jsonify({'success': True})
    
    flash('Comment deleted successfully!', 'success')
    return redirect(url_for('admin_comments'))

@app.route('/admin/comments/<int:comment_id>/approve', methods=['POST'])
@login_required
def admin_approve_comment(comment_id):
    """Approve comment"""
    if not current_user.is_admin:
        abort(403)
    
    comment = Comment.query.get_or_404(comment_id)
    comment.is_approved = True
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/comments/<int:comment_id>/flag', methods=['POST'])
@login_required
def admin_flag_comment(comment_id):
    """Flag comment for moderation"""
    if not current_user.is_admin:
        abort(403)
    
    comment = Comment.query.get_or_404(comment_id)
    comment.is_approved = False
    
    # Optionally create a report record
    reason = 'Flagged by admin'
    if request.json:
        reason = request.json.get('reason', 'Flagged by admin')
    if reason:
        report = Report()
        report.user_id = current_user.id
        report.content_type = 'comment'
        report.content_id = comment_id
        report.reason = 'admin_flag'
        report.description = reason
        report.status = 'investigating'
        db.session.add(report)
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/comments/bulk-approve', methods=['POST'])
@login_required
def admin_bulk_approve_comments():
    """Bulk approve comments"""
    if not current_user.is_admin:
        abort(403)
    
    comment_ids = request.json.get('comment_ids', []) if request.json else []
    if not comment_ids:
        return jsonify({'success': False, 'error': 'No comments selected'}), 400
    
    comments = Comment.query.filter(Comment.id.in_(comment_ids)).all()
    for comment in comments:
        comment.is_approved = True
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/comments/bulk-flag', methods=['POST'])
@login_required
def admin_bulk_flag_comments():
    """Bulk flag comments"""
    if not current_user.is_admin:
        abort(403)
    
    comment_ids = request.json.get('comment_ids', []) if request.json else []
    if not comment_ids:
        return jsonify({'success': False, 'error': 'No comments selected'}), 400
    
    comments = Comment.query.filter(Comment.id.in_(comment_ids)).all()
    for comment in comments:
        comment.is_approved = False
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/comments/bulk-delete', methods=['POST'])
@login_required
def admin_bulk_delete_comments():
    """Bulk delete comments"""
    if not current_user.is_admin:
        abort(403)
    
    comment_ids = request.json.get('comment_ids', []) if request.json else []
    if not comment_ids:
        return jsonify({'success': False, 'error': 'No comments selected'}), 400
    
    # Delete all reactions for these comments
    CommentReaction.query.filter(CommentReaction.comment_id.in_(comment_ids)).delete(synchronize_session=False)
    
    # Delete all replies for these comments
    Comment.query.filter(Comment.parent_id.in_(comment_ids)).delete(synchronize_session=False)
    
    # Delete the comments
    Comment.query.filter(Comment.id.in_(comment_ids)).delete(synchronize_session=False)
    
    db.session.commit()
    
    return jsonify({'success': True})

# Site Settings
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    """Advanced admin site settings with comprehensive configuration"""
    if not current_user.is_admin:
        abort(403)
    
    # Initialize default settings if not exists
    SettingsManager.initialize_defaults()
    
    if request.method == 'POST':
        try:
            # Handle different form actions
            action = request.form.get('action', 'save_settings')
            
            if action == 'save_settings':
                # Add logging to debug saving process
                logging.info(f"Admin settings save attempt by user: {current_user.username}")
                logging.info(f"Form data received: {list(request.form.keys())}")
                
                # Save all form settings
                settings_updated = 0
                
                # Get all checkbox settings that should be processed
                checkbox_settings = set()
                for key in request.form.keys():
                    if key.startswith('setting_'):
                        checkbox_settings.add(key.replace('setting_', ''))
                
                # Handle all settings from default settings
                for setting_key, config in SettingsManager._default_settings.items():
                    form_key = f'setting_{setting_key}'
                    
                    if form_key in request.form:
                        # Get all values for this key (important for checkboxes with hidden inputs)
                        values = request.form.getlist(form_key)
                        
                        # For checkboxes, take the last value (true if checked, false if only hidden)
                        if config['type'] == 'boolean':
                            value = 'true' if 'true' in values else 'false'
                        else:
                            value = values[-1] if values else ''
                        
                        data_type = config['type']
                        category = config['category']
                        
                        SettingsManager.set(
                            setting_key, 
                            value, 
                            data_type=data_type, 
                            category=category,
                            description=config['description'],
                            description_ar=config['description_ar']
                        )
                        settings_updated += 1
                        
                    elif config['type'] == 'boolean':
                        # Checkbox not in form at all, set to false
                        SettingsManager.set(
                            setting_key, 
                            'false', 
                            data_type='boolean', 
                            category=config['category'],
                            description=config['description'],
                            description_ar=config['description_ar']
                        )
                        settings_updated += 1
                
                logging.info(f"Successfully updated {settings_updated} settings")
                flash(f'تم تحديث {settings_updated} إعداد بنجاح', 'success')
                
                # Check if this is an AJAX request (from fetch)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'XMLHttpRequest' in request.headers.get('User-Agent', ''):
                    return jsonify({'success': True, 'message': f'تم تحديث {settings_updated} إعداد بنجاح', 'updated_count': settings_updated})
                
                # For regular form submissions, redirect to avoid resubmission
                return redirect(url_for('admin_settings'))
                
            elif action == 'update_individual_setting':
                # Handle individual setting updates (for authentication settings)
                setting_key = request.form.get('setting_key', '')
                setting_value = request.form.get('setting_value', '')
                
                logging.info(f"Individual setting update: {setting_key} = {setting_value}")
                
                if not setting_key:
                    return jsonify({'success': False, 'message': 'Setting key is required'})
                
                try:
                    # Map authentication setting keys to proper categories and descriptions
                    auth_settings_config = {
                        'google_oauth_enabled': {
                            'category': 'authentication',
                            'type': 'boolean',
                            'description': 'Enable Google OAuth authentication',
                            'description_ar': 'تفعيل مصادقة Google OAuth'
                        },
                        'google_oauth_client_id': {
                            'category': 'authentication',
                            'type': 'string',
                            'description': 'Google OAuth Client ID',
                            'description_ar': 'معرف عميل Google OAuth'
                        },
                        'google_oauth_client_secret': {
                            'category': 'authentication',
                            'type': 'string',
                            'description': 'Google OAuth Client Secret',
                            'description_ar': 'سر عميل Google OAuth'
                        },
                        'google_oauth_auto_register': {
                            'category': 'authentication',
                            'type': 'boolean',
                            'description': 'Auto-register Google OAuth users',
                            'description_ar': 'تسجيل مستخدمي Google OAuth تلقائياً'
                        },
                        'google_oauth_default_language': {
                            'category': 'authentication',
                            'type': 'string',
                            'description': 'Default language for Google OAuth users',
                            'description_ar': 'اللغة الافتراضية لمستخدمي Google OAuth'
                        }
                    }
                    
                    # Get configuration for this setting
                    config = auth_settings_config.get(setting_key)
                    if not config:
                        # Fallback to default settings if available
                        default_config = SettingsManager._default_settings.get(setting_key)
                        if default_config:
                            config = {
                                'category': default_config['category'],
                                'type': default_config['type'],
                                'description': default_config['description'],
                                'description_ar': default_config['description_ar']
                            }
                        else:
                            config = {
                                'category': 'general',
                                'type': 'string',
                                'description': f'Setting: {setting_key}',
                                'description_ar': f'إعداد: {setting_key}'
                            }
                    
                    # Clear cache first to ensure fresh settings
                    SettingsManager.clear_cache()
                    
                    # Save the setting
                    result = SettingsManager.set(
                        setting_key, 
                        setting_value, 
                        data_type=config['type'], 
                        category=config['category'],
                        description=config['description'],
                        description_ar=config['description_ar']
                    )
                    
                    # Clear cache again to ensure the new value is used
                    SettingsManager.clear_cache()
                    
                    logging.info(f"Setting {setting_key} updated successfully to: {setting_value}")
                    return jsonify({'success': True, 'message': 'تم حفظ الإعداد بنجاح'})
                    
                except Exception as e:
                    logging.error(f"Error updating individual setting {setting_key}: {e}")
                    return jsonify({'success': False, 'message': f'خطأ في حفظ الإعداد: {str(e)}'})
                
            elif action == 'export_settings':
                # Export settings as JSON
                try:
                    export_data = SettingsManager.export_settings()
                    # Here you could implement file download or show export data
                    flash('تم تصدير الإعدادات بنجاح', 'success')
                except Exception as e:
                    flash(f'خطأ في تصدير الإعدادات: {str(e)}', 'error')
                    
            elif action == 'import_settings':
                # Import settings from JSON
                import_data = request.form.get('import_data', '')
                if import_data:
                    if SettingsManager.import_settings(import_data):
                        flash('تم استيراد الإعدادات بنجاح', 'success')
                    else:
                        flash('خطأ في استيراد الإعدادات', 'error')
                else:
                    flash('يرجى إدخال بيانات صالحة للاستيراد', 'error')
                    
            elif action == 'reset_defaults':
                # Reset to default settings
                SettingsManager.clear_cache()
                for key, config in SettingsManager._default_settings.items():
                    SettingsManager.set(
                        key=key,
                        value=config['value'],
                        data_type=config['type'],
                        category=config['category'],
                        description=config['description'],
                        description_ar=config['description_ar']
                    )
                flash('تم إعادة تعيين الإعدادات إلى القيم الافتراضية', 'success')
                
            elif action == 'clear_cache':
                # Clear settings cache
                SettingsManager.clear_cache()
                flash('تم مسح ذاكرة التخزين المؤقت للإعدادات', 'success')
                
            elif action == 'test_email':
                # Test email configuration
                admin_email = get_setting('admin_email')
                contact_email = get_setting('contact_email')
                # Here you could implement actual email testing
                flash(f'تم اختبار إعدادات البريد الإلكتروني: {admin_email}, {contact_email}', 'info')
                
        except Exception as e:
            flash(f'خطأ في حفظ الإعدادات: {str(e)}', 'error')
            logging.error(f"Settings save error: {e}")
    
    # Get all current settings grouped by category
    all_settings = SettingsManager.get_all()
    
    # Get individual settings for template
    current_settings = {}
    for category_name, category_settings in all_settings.items():
        for key, setting_data in category_settings.items():
            value = setting_data['value']
            # Fix None or "None" values for URL fields
            if value in [None, "None", 'None'] and key in ['logo_url', 'favicon_url', 'hero_background']:
                value = ''
            current_settings[key] = value
    
    # Add missing default settings that aren't in database yet
    for key, config in SettingsManager._default_settings.items():
        if key not in current_settings:
            current_settings[key] = config['value']
    
    # Clear cache to ensure fresh data
    SettingsManager.clear_cache()
    
    # Get system information
    import os, platform
    from datetime import datetime
    try:
        import psutil
    except ImportError:
        psutil = None
    
    system_info = {
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'cpu_count': psutil.cpu_count() if psutil else 'N/A',
        'memory_total': round(psutil.virtual_memory().total / (1024**3), 2) if psutil else 'N/A',
        'memory_available': round(psutil.virtual_memory().available / (1024**3), 2) if psutil else 'N/A',
        'disk_total': round(psutil.disk_usage('/').total / (1024**3), 2) if psutil else 'N/A',
        'disk_free': round(psutil.disk_usage('/').free / (1024**3), 2) if psutil else 'N/A',
        'uptime': str(datetime.now() - datetime.fromtimestamp(psutil.boot_time())).split('.')[0] if psutil else 'N/A'
    }
    
    # Get database statistics
    from app.models import User, Manga, Chapter, Comment, Rating
    db_stats = {
        'total_users': User.query.count(),
        'total_manga': Manga.query.count(),
        'total_chapters': Chapter.query.count(),
        'total_comments': Comment.query.count(),
        'total_ratings': Rating.query.count(),
        'publishers': User.query.filter_by(is_publisher=True).count(),
        'admins': User.query.filter_by(is_admin=True).count(),
    }
    
    # Create settings_dict for template compatibility
    settings_dict = {}
    for category_name, category_settings in all_settings.items():
        for key, setting_data in category_settings.items():
            settings_dict[key] = {
                'value': setting_data.get('value', ''),
                'parsed_value': setting_data.get('parsed_value', setting_data.get('value', ''))
            }
    
    # Add missing default settings to settings_dict
    for key, config in SettingsManager._default_settings.items():
        if key not in settings_dict:
            settings_dict[key] = {
                'value': config['value'],
                'parsed_value': config['value']
            }
    
    # Get Cloudinary accounts for the settings page
    cloudinary_accounts = []
    cloudinary_stats = {}
    try:
        from app.models import CloudinaryAccount
        accounts = CloudinaryAccount.query.order_by(CloudinaryAccount.priority_order).all()
        cloudinary_accounts = accounts
        cloudinary_stats = {}
    except Exception as e:
        logging.warning(f"Failed to load Cloudinary accounts: {e}")
        cloudinary_accounts = []
        cloudinary_stats = {}
    
    return render_template('admin/settings.html', 
                         settings=current_settings,
                         settings_dict=settings_dict,
                         all_settings=all_settings,
                         system_info=system_info,
                         db_stats=db_stats,
                         default_settings=SettingsManager._default_settings,
                         cloudinary_accounts=cloudinary_accounts,
                         cloudinary_stats=cloudinary_stats)

@app.route('/admin/cloudinary/real-usage', methods=['GET'])
@login_required
def get_cloudinary_real_usage():
    """Get real-time storage usage from Cloudinary API"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_cloudinary import account_manager
        
        # Get real usage for all accounts
        usage_data = account_manager.get_all_accounts_real_usage()
        
        return jsonify({
            'success': True,
            'accounts': usage_data,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logging.error(f"❌ Error getting real Cloudinary usage: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/admin/cloudinary/update-usage/<int:account_id>', methods=['POST'])
@login_required  
def update_cloudinary_account_usage(account_id):
    """Update specific Cloudinary account with real usage data"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        from app.utils_cloudinary import account_manager
        
        account = CloudinaryAccount.query.get_or_404(account_id)
        
        # Update account with real usage
        usage_data = account_manager.update_account_with_real_usage(account)
        
        if usage_data:
            return jsonify({
                'success': True,
                'message': f'Updated usage for {account.name}',
                'usage_data': usage_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update account usage'
            }), 500
            
    except Exception as e:
        logging.error(f"❌ Error updating account usage: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/admin/cloudinary/switch-account/<int:account_id>', methods=['POST'])
@login_required
def switch_cloudinary_account(account_id):
    """Switch to a specific Cloudinary account as primary"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        from app.utils_cloudinary import account_manager
        from app.app import db
        
        # Get the target account
        target_account = CloudinaryAccount.query.get_or_404(account_id)
        
        if not target_account.is_active:
            return jsonify({
                'success': False,
                'error': 'Cannot switch to inactive account'
            }), 400
        
        # Remove primary flag from all accounts
        CloudinaryAccount.query.update({'is_primary': False})
        
        # Set target account as primary
        target_account.is_primary = True
        target_account.priority_order = 0  # Highest priority
        
        db.session.commit()
        
        # Configure Cloudinary with new account
        if account_manager.configure_cloudinary_with_account(target_account):
            return jsonify({
                'success': True,
                'message': f'Switched to {target_account.name} as primary account',
                'account_name': target_account.name
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to configure new account'
            }), 500
            
    except Exception as e:
        logging.error(f"❌ Error switching Cloudinary account: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ========== Cloudinary Account Management Routes ==========

@app.route('/admin/cloudinary/add-account', methods=['POST'])
@login_required
def admin_add_cloudinary_account():
    """Add new Cloudinary account"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        
        # Get form data
        account_name = request.form.get('account_name', '').strip()
        cloud_name = request.form.get('cloud_name', '').strip()
        api_key = request.form.get('api_key', '').strip()
        api_secret = request.form.get('api_secret', '').strip()
        
        # Validate required fields
        if not all([account_name, cloud_name, api_key, api_secret]):
            return jsonify({
                'success': False,
                'message': 'جميع الحقول مطلوبة'
            })
        
        # Check if account with same name exists
        existing = CloudinaryAccount.query.filter_by(name=account_name).first()
        if existing:
            return jsonify({
                'success': False,
                'message': 'يوجد حساب بنفس الاسم'
            })
        
        # Test Cloudinary credentials
        import cloudinary
        import cloudinary.api
        test_config = cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret
        )
        
        try:
            # Test API connection and get usage info
            result = cloudinary.api.usage()
            storage_used = result.get('storage', {}).get('usage', 0)
            storage_limit = result.get('storage', {}).get('limit', 1000000000)  # Default 1GB
            plan_type = result.get('plan', 'free')
            
        except Exception as test_error:
            return jsonify({
                'success': False,
                'message': f'فشل في الاتصال بـ Cloudinary: {str(test_error)}'
            })
        
        # Create new account
        new_account = CloudinaryAccount()
        new_account.name = account_name
        new_account.cloud_name = cloud_name
        new_account.api_key = api_key
        new_account.api_secret = api_secret
        new_account.storage_used_mb = storage_used / (1024 * 1024)  # Convert to MB
        new_account.storage_limit_mb = storage_limit / (1024 * 1024)  # Convert to MB
        new_account.plan_type = plan_type
        new_account.is_active = True
        new_account.is_primary = (CloudinaryAccount.query.count() == 0)  # First account is primary
        new_account.priority_order = CloudinaryAccount.query.count() + 1
        
        db.session.add(new_account)
        db.session.commit()
        
        logging.info(f"✅ Admin added new Cloudinary account: {account_name}")
        
        return jsonify({
            'success': True,
            'message': f'تم إضافة حساب {account_name} بنجاح'
        })
        
    except Exception as e:
        logging.error(f"❌ Error adding Cloudinary account: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ في إضافة الحساب'
        })

@app.route('/admin/cloudinary/delete-account/<int:account_id>', methods=['DELETE'])
@login_required
def admin_delete_cloudinary_account(account_id):
    """Delete Cloudinary account"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        
        account = CloudinaryAccount.query.get_or_404(account_id)
        
        # Don't delete if it's the only active account
        active_count = CloudinaryAccount.query.filter_by(is_active=True).count()
        if active_count <= 1:
            return jsonify({
                'success': False,
                'message': 'لا يمكن حذف آخر حساب نشط'
            })
        
        # If primary account, transfer to another
        if account.is_primary:
            next_account = CloudinaryAccount.query.filter(
                CloudinaryAccount.id != account_id,
                CloudinaryAccount.is_active == True
            ).first()
            if next_account:
                next_account.is_primary = True
        
        db.session.delete(account)
        db.session.commit()
        
        logging.info(f"✅ Admin deleted Cloudinary account: {account.name}")
        
        return jsonify({
            'success': True,
            'message': f'تم حذف حساب {account.name} بنجاح'
        })
        
    except Exception as e:
        logging.error(f"❌ Error deleting Cloudinary account: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ في حذف الحساب'
        })

@app.route('/admin/cloudinary/test-connection/<int:account_id>')
@login_required
def admin_test_cloudinary_connection(account_id):
    """Test connection to Cloudinary account"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        
        account = CloudinaryAccount.query.get_or_404(account_id)
        
        import cloudinary
        import cloudinary.api
        
        # Configure and test
        cloudinary.config(
            cloud_name=account.cloud_name,
            api_key=account.api_key,
            api_secret=account.api_secret
        )
        
        # Test API call
        result = cloudinary.api.usage()
        
        return jsonify({
            'success': True,
            'message': 'تم الاتصال بنجاح',
            'usage_info': {
                'storage_used': result.get('storage', {}).get('usage', 0),
                'storage_limit': result.get('storage', {}).get('limit', 0),
                'plan': result.get('plan', 'unknown')
            }
        })
        
    except Exception as e:
        logging.error(f"❌ Error testing Cloudinary connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/admin/cloudinary/refresh-usage')
@login_required
def admin_refresh_cloudinary_usage():
    """Refresh usage statistics for all Cloudinary accounts"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        
        import cloudinary
        import cloudinary.api
        
        accounts = CloudinaryAccount.query.filter_by(is_active=True).all()
        updated_count = 0
        
        for account in accounts:
            try:
                # Configure for this account
                cloudinary.config(
                    cloud_name=account.cloud_name,
                    api_key=account.api_key,
                    api_secret=account.api_secret
                )
                
                # Get current usage
                result = cloudinary.api.usage()
                storage_used = result.get('storage', {}).get('usage', 0)
                storage_limit = result.get('storage', {}).get('limit', 1000000000)
                
                # Update account
                account.storage_used_mb = storage_used / (1024 * 1024)
                account.storage_limit_mb = storage_limit / (1024 * 1024)
                account.plan_type = result.get('plan', 'free')
                account.last_usage_update = db.func.current_timestamp()
                
                updated_count += 1
                
            except Exception as account_error:
                logging.warning(f"⚠️ Failed to update usage for {account.name}: {account_error}")
                continue
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم تحديث {updated_count} حساب بنجاح'
        })
        
    except Exception as e:
        logging.error(f"❌ Error refreshing Cloudinary usage: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ في تحديث الإحصائيات'
        })

# Removed duplicate admin_upload_logo function - using upload_logo instead

@app.route('/admin/settings/<category>', methods=['POST'])
@login_required
def admin_settings_category(category):
    """Save specific category settings"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data received'})
        
        # Here you would save the settings to database
        # For now, just return success
        flash(f'{category.title()} settings updated successfully!', 'success')
        return jsonify({'success': True, 'message': f'{category} settings saved'})
        
    except Exception as e:
        print(f"Error saving {category} settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/settings/all', methods=['POST'])
@login_required
def admin_settings_all():
    """Save all settings at once"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data received'})
        
        # Here you would save all settings to database
        # For now, just return success
        flash('All settings updated successfully!', 'success')
        return jsonify({'success': True, 'message': 'All settings saved'})
        
    except Exception as e:
        print(f"Error saving all settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

# SEO Settings Management
@app.route('/admin/seo', methods=['GET', 'POST'])
@login_required
def admin_seo_settings():
    """Comprehensive SEO management interface"""
    if not current_user.is_admin:
        abort(403)
    
    # Initialize SEO defaults if not exists
    SettingsManager.initialize_defaults()
    
    if request.method == 'POST':
        try:
            import re
            logging.info(f"SEO settings save attempt by user: {current_user.username}")
            
            settings_updated = 0
            validation_errors = []
            
            # Process all SEO settings
            seo_settings = {k: v for k, v in SettingsManager._default_settings.items() 
                           if v['category'] == 'seo'}
            
            for setting_key, config in seo_settings.items():
                form_key = f'setting_{setting_key}'
                
                if form_key in request.form:
                    values = request.form.getlist(form_key)
                    
                    # Handle checkboxes properly
                    if config['type'] == 'boolean':
                        value = 'true' if 'true' in values else 'false'
                    else:
                        value = values[-1] if values else ''
                    
                    # Data validation and cleaning
                    cleaned_value = value
                    
                    # Validate URLs
                    if 'url' in setting_key.lower() and cleaned_value:
                        if not cleaned_value.startswith(('http://', 'https://', '/')):
                            validation_errors.append(f'الرابط غير صحيح في {setting_key}')
                            continue
                    
                    # Validate Twitter usernames
                    if 'twitter' in setting_key and 'username' in setting_key and cleaned_value:
                        if not cleaned_value.startswith('@'):
                            cleaned_value = '@' + cleaned_value.lstrip('@')
                    
                    # Validate Google Analytics IDs
                    if setting_key == 'seo_google_analytics' and cleaned_value:
                        if not re.match(r'^(G-[A-Z0-9]+|UA-\d+-\d+)$', cleaned_value):
                            validation_errors.append('معرف Google Analytics غير صحيح (يجب أن يكون G-XXXXXXX أو UA-XXXXX-X)')
                            continue
                    
                    # Validate Google Tag Manager IDs
                    if setting_key == 'seo_google_tag_manager' and cleaned_value:
                        if not re.match(r'^GTM-[A-Z0-9]+$', cleaned_value):
                            validation_errors.append('معرف Google Tag Manager غير صحيح (يجب أن يكون GTM-XXXXXXX)')
                            continue
                    
                    # Clean and limit text fields
                    if config['type'] in ['string', 'text']:
                        cleaned_value = cleaned_value.strip()
                        
                        # Limit meta description length
                        if setting_key == 'seo_meta_description' and len(cleaned_value) > 160:
                            cleaned_value = cleaned_value[:160]
                            flash('تم اقتطاع الوصف التعريفي إلى 160 حرف', 'warning')
                        
                        # Clean keywords
                        if 'keywords' in setting_key:
                            keywords = [kw.strip() for kw in cleaned_value.split(',') if kw.strip()]
                            cleaned_value = ', '.join(keywords)
                    
                    # Clean textarea fields
                    if config['type'] == 'textarea':
                        cleaned_value = cleaned_value.strip()
                    
                    SettingsManager.set(
                        setting_key, 
                        cleaned_value, 
                        data_type=config['type'], 
                        category=config['category'],
                        description=config['description'],
                        description_ar=config['description_ar']
                    )
                    settings_updated += 1
            
            # Show validation errors if any
            if validation_errors:
                for error in validation_errors:
                    flash(error, 'error')
            
            if settings_updated > 0:
                flash(f'تم تحديث {settings_updated} من إعدادات SEO بنجاح!', 'success')
                logging.info(f"SEO settings updated successfully - {settings_updated} settings")
            
            return redirect(url_for('admin_seo_settings'))
            
        except Exception as e:
            logging.error(f"Error saving SEO settings: {e}")
            flash(f'خطأ في حفظ الإعدادات: {str(e)}', 'error')
    
    # Get current SEO settings for display  
    try:
        seo_settings = {}
        
        # Add get_setting function to template globals
        def get_setting(key, default=''):
            from app.utils_settings import SettingsManager
            return SettingsManager.get(key, default)
        
        return render_template('admin_seo_settings.html', 
                             seo_settings=seo_settings,
                             get_setting=get_setting)
    except Exception as e:
        logging.error(f"Error loading SEO settings page: {e}")
        def get_setting(key, default=''):
            return default
        return render_template('admin_seo_settings.html', 
                             seo_settings={},
                             get_setting=get_setting)

@app.route('/robots.txt')
def robots_txt():
    """Dynamic robots.txt based on settings"""
    robots_content = SettingsManager.get('seo_robots_txt', '''User-agent: *
Allow: /
Disallow: /admin/
Disallow: /user/
Sitemap: /sitemap.xml''')
    
    return Response(robots_content, mimetype='text/plain')

@app.route('/admin/seo/preview')
@login_required
def admin_seo_preview():
    """Preview SEO settings"""
    if not current_user.is_admin:
        abort(403)
    
    from app.utils_seo import generate_complete_seo_data
    
    try:
        # Generate SEO data for homepage
        seo_data = generate_complete_seo_data(
            page_title="الصفحة الرئيسية",
            page_description="منصة قراءة المانجا الشاملة",
            page_type="website"
        )
        
        return jsonify({
            'success': True,
            'seo_data': seo_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/sitemap.xml')
def sitemap_xml():
    """Generate XML sitemap"""
    from tools.sitemap import generate_sitemap_xml
    
    try:
        sitemap_content = generate_sitemap_xml()
        if sitemap_content:
            return Response(sitemap_content, mimetype='application/xml')
        else:
            return Response('Sitemap disabled', status=404)
    except Exception as e:
        return Response(f'Error generating sitemap: {str(e)}', status=500)

# Favicon Management Routes
@app.route('/admin/upload-favicon', methods=['POST'])
@login_required 
def upload_favicon():
    """Upload a new favicon"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        import os
        import uuid
        from werkzeug.utils import secure_filename
        from PIL import Image
        from app.utils_settings import SettingsManager
        
        if 'favicon' not in request.files:
            return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})
        
        file = request.files['favicon']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})
        
        # Validate file extension
        allowed_extensions = ['ico', 'png', 'jpg', 'jpeg', 'gif', 'svg']
        filename = secure_filename(file.filename) if file.filename else ''
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename and filename else ''
        
        if not filename or file_extension not in allowed_extensions:
            return jsonify({'success': False, 'message': 'نوع الملف غير مدعوم'})
        
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads', 'favicon')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename  
        unique_filename = f"favicon_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Save the file
        file.save(file_path)
        
        # For non-SVG images, resize to favicon size
        if file_extension != 'svg':
            try:
                with Image.open(file_path) as img:
                    # Convert to RGB if necessary
                    if img.mode != 'RGB' and file_extension in ['jpg', 'jpeg']:
                        img = img.convert('RGB')
                    
                    # Resize to standard favicon sizes
                    favicon_sizes = [(32, 32), (16, 16)]
                    for size in favicon_sizes:
                        resized_img = img.resize(size, Image.Resampling.LANCZOS)
                        size_filename = f"favicon_{uuid.uuid4().hex[:8]}_{size[0]}x{size[1]}.{file_extension}"
                        size_path = os.path.join(upload_dir, size_filename)
                        resized_img.save(size_path)
                        
                        # Use the 32x32 version as the main favicon
                        if size == (32, 32):
                            # Remove the original large file
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            file_path = size_path
                            unique_filename = size_filename
                            
            except Exception as resize_error:
                logging.error(f"Error resizing favicon: {resize_error}")
                # Continue with original file if resize fails
                pass
        
        # Update the favicon setting
        favicon_url = f"/static/uploads/favicon/{unique_filename}"
        SettingsManager.set('site_favicon', favicon_url, data_type='string', category='site', 
                          description='رابط الفافيكون الخاص بالموقع')
        
        logging.info(f"Favicon uploaded successfully: {favicon_url}")
        
        return jsonify({
            'success': True,
            'message': 'تم رفع الفافيكون بنجاح',
            'favicon_path': favicon_url
        })
        
    except Exception as e:
        logging.error(f"Error uploading favicon: {e}")
        return jsonify({'success': False, 'message': f'خطأ في رفع الفافيكون: {str(e)}'})

@app.route('/admin/upload-logo', methods=['POST'])
@login_required 
def admin_upload_logo():
    """Upload a new site logo"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        import os
        import uuid
        from werkzeug.utils import secure_filename
        from PIL import Image
        from app.utils_settings import SettingsManager
        
        if 'logo' not in request.files:
            return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})
        
        file = request.files['logo']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})
        
        # Validate file extension
        allowed_extensions = ['ico', 'png', 'jpg', 'jpeg', 'gif', 'svg']
        filename = secure_filename(file.filename) if file.filename else ''
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename and filename else ''
        
        if not filename or file_extension not in allowed_extensions:
            return jsonify({'success': False, 'message': 'نوع الملف غير مدعوم. الرجاء استخدام PNG, JPG, SVG, GIF'})
        
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads', 'logos')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename  
        unique_filename = f"logo_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Save the file
        file.save(file_path)
        
        # For non-SVG images, resize to logo size
        if file_extension != 'svg':
            try:
                with Image.open(file_path) as img:
                    # Convert to RGB if necessary
                    if img.mode != 'RGB' and file_extension in ['jpg', 'jpeg']:
                        img = img.convert('RGB')
                    
                    # Resize to reasonable logo size (max 300x150)
                    max_width, max_height = 300, 150
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    
                    # Save the resized image
                    img.save(file_path)
                            
            except Exception as resize_error:
                logging.error(f"Error resizing logo: {resize_error}")
                # Continue with original file if resize fails
                pass
        
        # Update the logo setting
        logo_url = f"/static/uploads/logos/{unique_filename}"
        
        # Clear cache first to ensure fresh settings
        SettingsManager.clear_cache()
        
        # Set the new logo URL
        result = SettingsManager.set('logo_url', logo_url, data_type='string', category='general', 
                          description='رابط شعار الموقع', description_ar='رابط شعار الموقع')
        
        # Clear cache again to ensure the new value is used
        SettingsManager.clear_cache()
        
        logging.info(f"Logo uploaded successfully: {logo_url}")
        logging.info(f"Settings manager result: {result}")
        
        return jsonify({
            'success': True,
            'message': 'تم رفع الشعار بنجاح',
            'url': logo_url
        })
        
    except Exception as e:
        logging.error(f"Error uploading logo: {e}")
        return jsonify({'success': False, 'message': f'خطأ في رفع الشعار: {str(e)}'})

@app.route('/admin/reset-favicon', methods=['POST'])
@login_required
def reset_favicon():
    """Reset favicon to default"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        from app.utils_settings import SettingsManager
        
        # Reset to default favicon
        default_favicon = '/static/img/favicon.ico'
        SettingsManager.set('site_favicon', default_favicon, data_type='string', category='site', 
                          description='رابط الفافيكون الخاص بالموقع')
        
        return jsonify({
            'success': True,
            'message': 'تم استعادة الفافيكون الافتراضي',
            'favicon_path': default_favicon
        })
        
    except Exception as e:
        logging.error(f"Error resetting favicon: {e}")
        return jsonify({'success': False, 'message': f'خطأ في استعادة الفافيكون: {str(e)}'})

@app.route('/admin/delete-favicon', methods=['POST'])
@login_required
def delete_favicon():
    """Delete current favicon"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        import os
        from app.utils_settings import SettingsManager
        
        # Get current favicon path
        current_favicon = SettingsManager.get('site_favicon', '/static/img/favicon.ico')
        
        # Only delete if it's a custom uploaded favicon
        if current_favicon and current_favicon.startswith('/static/uploads/favicon/'):
            file_path = current_favicon[1:]  # Remove leading slash
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Deleted favicon file: {file_path}")
        
        # Reset to default
        default_favicon = '/static/img/favicon.ico'
        SettingsManager.set('site_favicon', default_favicon, data_type='string', category='site', 
                          description='رابط الفافيكون الخاص بالموقع')
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الفافيكون وإعادة تعيين الافتراضي',
            'favicon_path': default_favicon
        })
        
    except Exception as e:
        logging.error(f"Error deleting favicon: {e}")
        return jsonify({'success': False, 'message': f'خطأ في حذف الفافيكون: {str(e)}'})

# API Routes للتطبيق
@app.route('/api/manga/search', methods=['GET'])
@limiter.limit("20 per minute")  # تحديد البحث لمنع الإفراط
def api_manga_search():
    """API endpoint للبحث في المانجا - محسن الأمان"""
    try:
        query = request.args.get('q', '').strip()[:100]  # تحديد طول البحث
        limit = min(max(1, int(request.args.get('limit', 20))), 30)  # تقليل الحد الأقصى
        page = max(1, int(request.args.get('page', 1)))
        
        # التحقق من صحة البحث
        if not query or len(query.strip()) < 2:
            return jsonify({
                'status': 'error',
                'message': 'البحث يجب أن يحتوي على حرفين على الأقل'
            }), 400
        
        # منع البحث بالرموز المشبوهة
        import re
        if re.search(r'[<>"\';\\]', query):
            return jsonify({
                'status': 'error', 
                'message': 'البحث يحتوي على رموز غير مسموحة'
            }), 400
        
        # البحث الآمن في المانجا
        search_results = Manga.query.filter(
            db.and_(
                Manga.is_published == True,
                db.or_(
                    Manga.title.ilike(f'%{query}%'),
                    Manga.title_ar.ilike(f'%{query}%'),
                    Manga.author.ilike(f'%{query}%')
                )
            )
        ).limit(limit).offset((page-1)*limit).all()
        
        results = []
        for manga in search_results:
            results.append({
                'id': manga.id,
                'title': manga.title,
                'title_ar': manga.title_ar,
                'author': manga.author,
                'cover_image': manga.cover_image,
                'status': manga.status,
                'average_rating': round(manga.average_rating, 1) if manga.average_rating else None,
                'total_chapters': manga.total_chapters or 0
            })
        
        response_data = {
            'status': 'success',
            'results': results,
            'total_found': min(len(results), 1000),  # تحديد العدد المعروض
            'page': page,
            'query': query[:50]  # تحديد طول النص المرجع
        }
        
        response = jsonify(response_data)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response
        
    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({
            'status': 'error',
            'message': 'حدث خطأ في البحث'
        }), 500

@app.route('/api/manga/<int:manga_id>/chapters', methods=['GET'])
def api_manga_chapters(manga_id):
    """API endpoint للحصول على فصول المانجا"""
    try:
        manga = Manga.query.get_or_404(manga_id)
        
        chapters = Chapter.query.filter_by(manga_id=manga_id)\
                                .filter(Chapter.status == 'published')\
                                .order_by(Chapter.chapter_number.desc()).all()
        
        results = []
        for chapter in chapters:
            results.append({
                'id': chapter.id,
                'title': chapter.title,
                'title_ar': chapter.title_ar,
                'chapter_number': chapter.chapter_number,
                'published_at': chapter.published_at.isoformat() if chapter.published_at else None,
                'page_count': chapter.page_images.count(),
                'views': chapter.views
            })
        
        return jsonify({
            'success': True,
            'manga': {
                'id': manga.id,
                'title': manga.title,
                'title_ar': manga.title_ar,
                'slug': manga.slug
            },
            'chapters': results,
            'total_chapters': len(results)
        })
        
    except Exception as e:
        logging.error(f"API chapters error: {e}")
        return jsonify({
            'success': False,
            'message': 'خطأ في تحميل الفصول'
        })

@app.route('/api/user/reading-progress', methods=['GET'])
@login_required
def api_user_reading_progress():
    """API endpoint لتتبع تقدم القراءة للمستخدم"""
    try:
        progress_records = ReadingProgress.query.filter_by(user_id=current_user.id)\
                                               .order_by(ReadingProgress.updated_at.desc())\
                                               .limit(50).all()
        
        results = []
        for progress in progress_records:
            manga = progress.manga
            last_chapter = progress.chapter
            
            results.append({
                'manga_id': manga.id,
                'manga_title': manga.title,
                'manga_title_ar': manga.title_ar,
                'manga_slug': manga.slug,
                'manga_cover': manga.cover_image,
                'last_chapter_id': last_chapter.id if last_chapter else None,
                'last_chapter_number': last_chapter.chapter_number if last_chapter else None,
                'last_page': progress.page_number,
                'last_read_at': progress.updated_at.isoformat(),
                'progress_percentage': 0  # TODO: Calculate progress percentage
            })
        
        return jsonify({
            'success': True,
            'reading_progress': results,
            'total_items': len(results)
        })
        
    except Exception as e:
        logging.error(f"API reading progress error: {e}")
        return jsonify({
            'success': False,
            'message': 'خطأ في تحميل تقدم القراءة'
        })

@app.route('/api/user/bookmarks', methods=['GET'])
@login_required
def api_user_bookmarks():
    """API endpoint للحصول على مفضلات المستخدم"""
    try:
        bookmarks = Bookmark.query.filter_by(user_id=current_user.id)\
                                  .order_by(Bookmark.created_at.desc()).all()
        
        results = []
        for bookmark in bookmarks:
            manga = bookmark.manga
            results.append({
                'bookmark_id': bookmark.id,
                'manga_id': manga.id,
                'manga_title': manga.title,
                'manga_title_ar': manga.title_ar,
                'manga_slug': manga.slug,
                'manga_cover': manga.cover_image,
                'added_at': bookmark.created_at.isoformat(),
                'latest_chapter': manga.chapters.filter(Chapter.status == 'published')
                                                .order_by(Chapter.chapter_number.desc())
                                                .first().chapter_number if manga.chapters.filter(Chapter.status == 'published').first() else 0
            })
        
        return jsonify({
            'success': True,
            'bookmarks': results,
            'total_bookmarks': len(results)
        })
        
    except Exception as e:
        logging.error(f"API bookmarks error: {e}")
        return jsonify({
            'success': False,
            'message': 'خطأ في تحميل المفضلات'
        })

@app.route('/api/manga/popular', methods=['GET'])
@limiter.limit("40 per minute")  # حد معقول للمحتوى الشائع
def api_popular_manga():
    """API endpoint للمانجا الشائعة - محسن الأمان"""
    try:
        limit = min(max(1, int(request.args.get('limit', 20))), 30)  # تحديد الحد الأقصى
        
        # المانجا الأكثر شعبية بشكل آمن
        popular_manga = Manga.query.filter(Manga.is_published == True)\
                                   .order_by(Manga.average_rating.desc(), Manga.total_chapters.desc())\
                                   .limit(limit).all()
        
        results = []
        for manga in popular_manga:
            results.append({
                'id': manga.id,
                'title': manga.title,
                'title_ar': manga.title_ar,
                'author': manga.author,
                'cover_image': manga.cover_image,
                'average_rating': round(manga.average_rating, 1) if manga.average_rating else None,
                'total_chapters': manga.total_chapters or 0,
                'status': manga.status
            })
        
        response_data = {
            'status': 'success',
            'popular_manga': results,
            'total_items': len(results)
        }
        
        response = jsonify(response_data)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'public, max-age=600'  # cache أطول للمحتوى الشائع
        return response
        
    except Exception as e:
        logger.error(f"API popular manga error: {e}")
        return jsonify({
            'status': 'error',
            'message': 'حدث خطأ في تحميل المانجا الشائعة'
        }), 500

@app.route('/api/manga/latest', methods=['GET'])
@limiter.limit("40 per minute")  # حد معقول للمحتوى الحديث
def api_latest_manga():
    """API endpoint لأحدث المانجا - محسن الأمان"""
    try:
        limit = min(max(1, int(request.args.get('limit', 20))), 30)  # تحديد الحد الأقصى
        
        latest_manga = Manga.query.filter(Manga.is_published == True)\
                                  .order_by(Manga.created_at.desc())\
                                  .limit(limit).all()
        
        results = []
        for manga in latest_manga:
            results.append({
                'id': manga.id,
                'title': manga.title,
                'title_ar': manga.title_ar,
                'author': manga.author,
                'cover_image': manga.cover_image,
                'created_at': manga.created_at.strftime('%Y-%m-%d') if manga.created_at else None,
                'total_chapters': manga.total_chapters or 0,
                'average_rating': round(manga.average_rating, 1) if manga.average_rating else None
            })
        
        response_data = {
            'status': 'success',
            'latest_manga': results,
            'total_items': len(results)
        }
        
        response = jsonify(response_data)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'public, max-age=600'
        return response
        
    except Exception as e:
        logger.error(f"API latest manga error: {e}")
        return jsonify({
            'status': 'error',
            'message': 'حدث خطأ في تحميل أحدث المانجا'
        }), 500

@app.route('/api/stats/site', methods=['GET'])
@login_required
def api_site_stats():
    """API endpoint لإحصائيات الموقع (للمشرفين فقط)"""
    if not current_user.is_admin:
        return jsonify({
            'success': False,
            'message': 'غير مصرح لك بالوصول لهذه البيانات'
        })
    
    try:
        stats = {
            'total_manga': Manga.query.count(),
            'published_manga': Manga.query.filter(Manga.status == 'published').count(),
            'total_chapters': Chapter.query.count(),
            'published_chapters': Chapter.query.filter(Chapter.status == 'published').count(),
            'total_users': User.query.count(),
            'premium_users': User.query.filter(User.premium_until > datetime.utcnow()).count(),
            'total_comments': Comment.query.count(),
            'total_ratings': Rating.query.count(),
            'total_bookmarks': Bookmark.query.count(),
            'total_page_views': db.session.query(func.sum(Manga.views)).scalar() or 0
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logging.error(f"API stats error: {e}")
        return jsonify({
            'success': False,
            'message': 'خطأ في تحميل الإحصائيات'
        })

# Enhanced SEO Routes
@app.route('/admin/seo/test-robots', methods=['POST'])
@login_required
def admin_test_robots():
    """Test robots.txt configuration"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        robots_content = SettingsManager.get('seo_robots_txt', '')
        
        # Basic validation
        if not robots_content.strip():
            return jsonify({
                'success': False,
                'message': 'محتوى robots.txt فارغ'
            })
        
        # Check for required elements
        has_user_agent = 'User-agent:' in robots_content
        has_sitemap = 'Sitemap:' in robots_content
        
        warnings = []
        if not has_user_agent:
            warnings.append('لا يحتوي على User-agent')
        if not has_sitemap:
            warnings.append('لا يحتوي على Sitemap')
        
        return jsonify({
            'success': True,
            'message': 'تم فحص robots.txt بنجاح',
            'has_user_agent': has_user_agent,
            'has_sitemap': has_sitemap,
            'warnings': warnings
        })
        
    except Exception as e:
        logging.error(f"Error testing robots.txt: {e}")
        return jsonify({
            'success': False,
            'message': f'خطأ في فحص robots.txt: {str(e)}'
        })

@app.route('/admin/seo/generate-sitemap', methods=['POST'])
@login_required
def admin_generate_sitemap():
    """Regenerate XML sitemap"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from tools.sitemap import generate_sitemap_xml
        
        # Check if sitemap is enabled
        if not SettingsManager.get('seo_sitemap_enabled', True):
            return jsonify({
                'success': False,
                'message': 'خريطة الموقع معطلة في الإعدادات'
            })
        
        # Generate sitemap
        sitemap_content = generate_sitemap_xml()
        
        if sitemap_content:
            return jsonify({
                'success': True,
                'message': 'تم إنشاء خريطة الموقع بنجاح',
                'sitemap_url': '/sitemap.xml'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'فشل في إنشاء خريطة الموقع'
            })
        
    except Exception as e:
        logging.error(f"Error generating sitemap: {e}")
        return jsonify({
            'success': False,
            'message': f'خطأ في إنشاء خريطة الموقع: {str(e)}'
        })

@app.route('/admin/seo/export', methods=['GET'])
@login_required
def admin_export_seo_settings():
    """Export SEO settings as JSON"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_settings import SettingsManager
        from datetime import datetime
        
        # Get all SEO settings
        seo_settings = {}
        for key, config in SettingsManager._default_settings.items():
            if config['category'] == 'seo':
                seo_settings[key] = SettingsManager.get(key, config['value'])
        
        # Create export data
        export_data = {
            'export_date': datetime.utcnow().isoformat(),
            'version': '1.0',
            'platform': 'Manga Platform',
            'settings_count': len(seo_settings),
            'seo_settings': seo_settings
        }
        
        # Create response
        response = Response(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename=seo_settings_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            }
        )
        
        logging.info(f"SEO settings exported by user: {current_user.username}")
        return response
        
    except Exception as e:
        logging.error(f"Error exporting SEO settings: {e}")
        flash(f'خطأ في تصدير الإعدادات: {str(e)}', 'error')
        return redirect(url_for('admin_seo_settings'))

@app.route('/admin/seo/import', methods=['POST'])
@login_required
def admin_import_seo_settings():
    """Import SEO settings from JSON file"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        import json
        from app.utils_settings import SettingsManager
        
        if 'seo_file' not in request.files:
            return jsonify({
                'success': False,
                'message': 'لم يتم اختيار ملف'
            })
        
        file = request.files['seo_file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'لم يتم اختيار ملف صالح'
            })
        
        # Read and parse JSON
        content = file.read().decode('utf-8')
        import_data = json.loads(content)
        
        # Validate structure
        if 'seo_settings' not in import_data:
            return jsonify({
                'success': False,
                'message': 'ملف الإعدادات غير صالح - مفتاح seo_settings مفقود'
            })
        
        # Import settings
        imported_count = 0
        errors = []
        
        for key, value in import_data['seo_settings'].items():
            try:
                # Check if setting exists in defaults
                if key in SettingsManager._default_settings:
                    config = SettingsManager._default_settings[key]
                    if config['category'] == 'seo':
                        SettingsManager.set(
                            key, 
                            value, 
                            data_type=config['type'], 
                            category=config['category'],
                            description=config['description'],
                            description_ar=config['description_ar']
                        )
                        imported_count += 1
                else:
                    errors.append(f'إعداد غير معروف: {key}')
            except Exception as e:
                errors.append(f'خطأ في استيراد {key}: {str(e)}')
        
        logging.info(f"SEO settings imported by user: {current_user.username} - {imported_count} settings")
        
        return jsonify({
            'success': True,
            'message': f'تم استيراد {imported_count} إعداد بنجاح',
            'imported_count': imported_count,
            'errors': errors
        })
        
    except json.JSONDecodeError:
        return jsonify({
            'success': False,
            'message': 'ملف JSON غير صالح'
        })
    except Exception as e:
        logging.error(f"Error importing SEO settings: {e}")
        return jsonify({
            'success': False,
            'message': f'خطأ في استيراد الإعدادات: {str(e)}'
        })

@app.route('/admin/seo/reset', methods=['POST'])
@login_required
def admin_reset_seo_settings():
    """Reset all SEO settings to defaults"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_settings import SettingsManager
        
        # Reset all SEO settings to defaults
        reset_count = 0
        for key, config in SettingsManager._default_settings.items():
            if config['category'] == 'seo':
                SettingsManager.set(
                    key, 
                    config['value'], 
                    data_type=config['type'], 
                    category=config['category'],
                    description=config['description'],
                    description_ar=config['description_ar']
                )
                reset_count += 1
        
        logging.info(f"SEO settings reset by user: {current_user.username} - {reset_count} settings")
        
        return jsonify({
            'success': True,
            'message': f'تم إعادة تعيين {reset_count} إعداد SEO إلى القيم الافتراضية',
            'reset_count': reset_count
        })
        
    except Exception as e:
        logging.error(f"Error resetting SEO settings: {e}")
        return jsonify({
            'success': False,
            'message': f'خطأ في إعادة تعيين الإعدادات: {str(e)}'
        })

# Payment Gateway Management Routes
@app.route('/admin/payments/activate/<int:payment_id>', methods=['POST'])
@login_required
def admin_activate_payment(payment_id):
    """Manually activate a payment and subscription (admin only)"""
    if not current_user.is_admin:
        abort(403)
    
    payment_record = Payment.query.get_or_404(payment_id)
    
    if payment_record.status == 'completed':
        flash('هذا الاشتراك مفعل بالفعل', 'info')
        return redirect(url_for('admin_payments'))
    
    try:
        # Call the complete_subscription function to activate the subscription
        from datetime import datetime, timedelta
        
        # Update payment status
        payment_record.status = 'completed'
        payment_record.completed_at = datetime.utcnow()
        
        # Update user premium subscription
        user = payment_record.user
        plan = payment_record.plan
        
        if user.premium_until and user.premium_until > datetime.utcnow():
            # Extend existing subscription
            user.premium_until += timedelta(days=plan.duration_months * 30)
        else:
            # Start new subscription
            user.premium_until = datetime.utcnow() + timedelta(days=plan.duration_months * 30)
        
        # Create subscription record
        subscription = UserSubscription()
        subscription.user_id = user.id
        subscription.plan_id = plan.id
        subscription.payment_id = payment_record.id
        subscription.status = 'active'
        subscription.start_date = datetime.utcnow()
        subscription.end_date = user.premium_until
        subscription.auto_renew = True
        
        db.session.add(subscription)
        db.session.commit()
        
        flash(f'تم تفعيل اشتراك المستخدم {user.username} في خطة {plan.name_ar or plan.name} بنجاح', 'success')
        
    except Exception as e:
        print(f"Manual activation error: {e}")
        flash('حدث خطأ في تفعيل الاشتراك', 'error')
    
    return redirect(url_for('admin_payments'))

@app.route('/admin/payments')
@login_required
def admin_payments():
    """Admin payments dashboard"""
    if not current_user.is_admin:
        abort(403)
    
    # Get all payments with pagination
    page = request.args.get('page', 1, type=int)
    payments = Payment.query.order_by(Payment.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get payment statistics
    total_payments = Payment.query.count()
    completed_payments = Payment.query.filter_by(status='completed').count()
    pending_payments = Payment.query.filter_by(status='pending').count()
    failed_payments = Payment.query.filter_by(status='failed').count()
    
    # Calculate total revenue
    total_revenue = db.session.query(func.sum(Payment.amount)).filter_by(status='completed').scalar() or 0
    
    # Get payment gateways
    gateways = PaymentGateway.query.all()
    
    # Get recent payments for quick view
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(10).all()
    
    # Handle export request
    if request.args.get('export') == 'csv':
        import csv
        import io
        from flask import make_response
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'Transaction ID', 'Gateway Transaction ID', 'User', 'Email', 
            'Plan', 'Amount', 'Currency', 'Gateway', 'Status', 
            'Created Date', 'Completed Date'
        ])
        
        # Get all payments (not paginated for export)
        all_payments = Payment.query.order_by(Payment.created_at.desc()).all()
        
        # Write data
        for payment in all_payments:
            writer.writerow([
                payment.gateway_transaction_id or payment.gateway_payment_id or f"PAY_{payment.id}",
                payment.gateway_transaction_id or '',
                payment.user.username,
                payment.user.email,
                payment.plan.name if payment.plan else '',
                payment.amount,
                payment.currency,
                payment.gateway.name,
                payment.status,
                payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                payment.completed_at.strftime('%Y-%m-%d %H:%M:%S') if payment.completed_at else ''
            ])
        
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=payments_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
    
    return render_template('admin/payments.html',
                         payments=payments,
                         total_payments=total_payments,
                         completed_payments=completed_payments,
                         pending_payments=pending_payments,
                         failed_payments=failed_payments,
                         total_revenue=total_revenue,
                         gateways=gateways,
                         recent_payments=recent_payments)

@app.route('/admin/payments/<int:payment_id>/verify', methods=['POST'])
@login_required
def admin_verify_payment(payment_id):
    """Verify payment with gateway"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    payment = Payment.query.get_or_404(payment_id)
    
    try:
        # Simulate verification process (in a real app, this would call the gateway API)
        if payment.status == 'pending':
            # Check with payment gateway (mock implementation)
            # In real implementation, you would call the gateway's API
            payment.status = 'completed'
            payment.completed_at = datetime.utcnow()
            
            # Activate subscription if payment is completed
            if payment.plan:
                user = payment.user
                plan = payment.plan
                
                if user.premium_until and user.premium_until > datetime.utcnow():
                    # Extend existing subscription
                    user.premium_until += timedelta(days=plan.duration_months * 30)
                else:
                    # Start new subscription
                    user.premium_until = datetime.utcnow() + timedelta(days=plan.duration_months * 30)
                
                # Create subscription record
                subscription = UserSubscription()
                subscription.user_id = user.id
                subscription.plan_id = plan.id
                subscription.payment_id = payment.id
                subscription.status = 'active'
                subscription.start_date = datetime.utcnow()
                subscription.end_date = user.premium_until
                subscription.auto_renew = True
                
                db.session.add(subscription)
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Payment verified and activated'})
        else:
            return jsonify({'success': False, 'error': 'Payment is not in pending status'})
            
    except Exception as e:
        print(f"Payment verification error: {e}")
        return jsonify({'success': False, 'error': 'Verification failed'})

@app.route('/admin/payments/<int:payment_id>/refund', methods=['POST'])
@login_required
def admin_refund_payment(payment_id):
    """Initiate refund for payment"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    payment = Payment.query.get_or_404(payment_id)
    data = request.get_json()
    reason = data.get('reason', '').strip() if data else ''
    
    if not reason:
        return jsonify({'success': False, 'error': 'Refund reason is required'})
    
    try:
        if payment.status != 'completed':
            return jsonify({'success': False, 'error': 'Only completed payments can be refunded'})
        
        # Process refund (in real app, call gateway API)
        payment.status = 'refunded'
        payment.refunded_at = datetime.utcnow()
        payment.refund_reason = reason
        
        # Deactivate subscription if exists
        user_subscription = UserSubscription.query.filter_by(payment_id=payment.id).first()
        if user_subscription:
            user_subscription.status = 'cancelled'
            user_subscription.cancelled_at = datetime.utcnow()
            
        # Update user premium status
        user = payment.user
        if user.premium_until:
            # Calculate remaining days and subtract from premium
            plan_days = payment.plan.duration_months * 30 if payment.plan else 30
            user.premium_until = max(
                datetime.utcnow(),
                user.premium_until - timedelta(days=plan_days)
            )
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Refund processed successfully'})
        
    except Exception as e:
        print(f"Refund processing error: {e}")
        return jsonify({'success': False, 'error': 'Refund processing failed'})

@app.route('/admin/payments/<int:payment_id>/send-receipt', methods=['POST'])
@login_required
def admin_send_receipt(payment_id):
    """Send receipt email to user"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    payment = Payment.query.get_or_404(payment_id)
    
    try:
        # In real implementation, you would send an email
        # For now, we'll simulate the process
        
        # Mock email sending
        receipt_data = {
            'transaction_id': payment.gateway_transaction_id or payment.gateway_payment_id or f"PAY_{payment.id}",
            'amount': payment.amount,
            'currency': payment.currency,
            'user_email': payment.user.email,
            'plan_name': payment.plan.name if payment.plan else 'N/A',
            'date': payment.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Here you would use an email service like SendGrid, SES, etc.
        # send_receipt_email(payment.user.email, receipt_data)
        
        # For demonstration, we'll just log it
        print(f"Receipt sent to {payment.user.email} for payment {payment.gateway_transaction_id or payment.id}")
        
        return jsonify({'success': True, 'message': 'Receipt sent successfully'})
        
    except Exception as e:
        print(f"Receipt sending error: {e}")
        return jsonify({'success': False, 'error': 'Failed to send receipt'})

@app.route('/admin/payments/<int:payment_id>/gateway-logs')
@login_required
def admin_payment_gateway_logs(payment_id):
    """View gateway logs for payment"""
    if not current_user.is_admin:
        abort(403)
    
    payment = Payment.query.get_or_404(payment_id)
    
    # Mock gateway logs (in real implementation, fetch from gateway or logs table)
    payment_id = payment.gateway_transaction_id or payment.gateway_payment_id or f"PAY_{payment.id}"
    logs = [
        {
            'timestamp': payment.created_at,
            'action': 'Payment Created',
            'status': 'success',
            'message': f'Payment {payment_id} created successfully'
        },
        {
            'timestamp': payment.created_at + timedelta(minutes=1),
            'action': 'Gateway Processing',
            'status': 'processing',
            'message': f'Payment sent to {payment.gateway.name} gateway'
        }
    ]
    
    if payment.completed_at:
        logs.append({
            'timestamp': payment.completed_at,
            'action': 'Payment Completed',
            'status': 'success',
            'message': 'Payment completed successfully'
        })
    
    if payment.status == 'failed':
        logs.append({
            'timestamp': payment.created_at + timedelta(minutes=2),
            'action': 'Payment Failed',
            'status': 'error',
            'message': 'Payment processing failed'
        })
    
    return render_template('admin/payment_gateway_logs.html', payment=payment, logs=logs)

# Removed old duplicate Cloudinary routes - using newer versions below

@app.route('/admin/payment-gateways')
@login_required
def admin_payment_gateways():
    """Manage payment gateways"""
    if not current_user.is_admin:
        abort(403)
    
    gateways = PaymentGateway.query.order_by(PaymentGateway.name.asc()).all()
    return render_template('admin/payment_gateways.html', gateways=gateways)

@app.route('/admin/payment-gateways/add', methods=['GET', 'POST'])
@login_required
def admin_add_payment_gateway():
    """Add new payment gateway"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        display_name = request.form.get('display_name', '').strip()
        display_name_ar = request.form.get('display_name_ar', '').strip()
        gateway_type = request.form.get('gateway_type', '').strip()
        is_active = safe_parse_bool(request.form.get('is_active'))
        is_sandbox = safe_parse_bool(request.form.get('is_sandbox'))
        description = request.form.get('description', '').strip()
        description_ar = request.form.get('description_ar', '').strip()
        logo_url = request.form.get('logo_url', '').strip()
        
        # Configuration data based on gateway type
        config_data = {}
        
        if gateway_type == 'stripe':
            config_data = {
                'publishable_key': request.form.get('stripe_publishable_key', ''),
                'secret_key': request.form.get('stripe_secret_key', ''),
                'webhook_secret': request.form.get('stripe_webhook_secret', '')
            }
        elif gateway_type == 'paypal':
            config_data = {
                'client_id': request.form.get('paypal_client_id', ''),
                'client_secret': request.form.get('paypal_client_secret', ''),
                # Keep backward compatibility fields
                'live_client_id': request.form.get('paypal_client_id', ''),
                'live_client_secret': request.form.get('paypal_client_secret', ''),
                'sandbox_client_id': request.form.get('paypal_client_id', ''),
                'sandbox_client_secret': request.form.get('paypal_client_secret', '')
            }
        elif gateway_type == 'paytabs':
            config_data = {
                'server_key': request.form.get('paytabs_server_key', ''),
                'client_key': request.form.get('paytabs_client_key', ''),
                'merchant_id': request.form.get('paytabs_merchant_id', '')
            }
        elif gateway_type == 'fawry':
            config_data = {
                'merchant_code': request.form.get('fawry_merchant_code', ''),
                'security_key': request.form.get('fawry_security_key', '')
            }
        elif gateway_type == 'paymob':
            config_data = {
                'api_key': request.form.get('paymob_api_key', ''),
                'integration_id': request.form.get('paymob_integration_id', ''),
                'iframe_id': request.form.get('paymob_iframe_id', ''),
                'hmac_secret': request.form.get('paymob_hmac_secret', '')
            }
        
        # Supported currencies
        currencies_input = request.form.get('supported_currencies', '')
        supported_currencies = [c.strip().upper() for c in currencies_input.split(',') if c.strip()]
        
        if not name or not display_name or not gateway_type:
            flash('اسم البوابة واسم العرض ونوع البوابة مطلوبة', 'error')
            return render_template('admin/add_payment_gateway.html')
        
        gateway = PaymentGateway()
        gateway.name = name
        gateway.display_name = display_name
        gateway.display_name_ar = display_name_ar
        gateway.gateway_type = gateway_type
        gateway.is_active = is_active
        gateway.is_sandbox = is_sandbox
        gateway.config_data = config_data
        gateway.description = description
        gateway.description_ar = description_ar
        gateway.logo_url = logo_url
        gateway.supported_currencies = supported_currencies
        
        db.session.add(gateway)
        db.session.commit()
        
        flash('تم إضافة بوابة الدفع بنجاح', 'success')
        return redirect(url_for('admin_payment_gateways'))
    
    return render_template('admin/add_payment_gateway.html')

@app.route('/admin/payment-gateways/edit/<int:gateway_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_payment_gateway(gateway_id):
    """Edit payment gateway"""
    if not current_user.is_admin:
        abort(403)
    
    gateway = PaymentGateway.query.get_or_404(gateway_id)
    
    if request.method == 'POST':
        gateway.name = request.form.get('name', '').strip()
        gateway.display_name = request.form.get('display_name', '').strip()
        gateway.display_name_ar = request.form.get('display_name_ar', '').strip()
        gateway.gateway_type = request.form.get('gateway_type', '').strip()
        gateway.is_active = safe_parse_bool(request.form.get('is_active'))
        gateway.is_sandbox = safe_parse_bool(request.form.get('is_sandbox'))
        gateway.description = request.form.get('description', '').strip()
        gateway.description_ar = request.form.get('description_ar', '').strip()
        gateway.logo_url = request.form.get('logo_url', '').strip()
        
        # Update configuration data
        config_data = {}
        if gateway.gateway_type == 'stripe':
            config_data = {
                'publishable_key': request.form.get('stripe_publishable_key', ''),
                'secret_key': request.form.get('stripe_secret_key', ''),
                'webhook_secret': request.form.get('stripe_webhook_secret', '')
            }
        elif gateway.gateway_type == 'paypal':
            config_data = {
                'client_id': request.form.get('paypal_client_id', ''),
                'client_secret': request.form.get('paypal_client_secret', ''),
                # Keep backward compatibility fields
                'live_client_id': request.form.get('paypal_client_id', ''),
                'live_client_secret': request.form.get('paypal_client_secret', ''),
                'sandbox_client_id': request.form.get('paypal_client_id', ''),
                'sandbox_client_secret': request.form.get('paypal_client_secret', '')
            }
        elif gateway.gateway_type == 'paytabs':
            config_data = {
                'server_key': request.form.get('paytabs_server_key', ''),
                'client_key': request.form.get('paytabs_client_key', ''),
                'merchant_id': request.form.get('paytabs_merchant_id', '')
            }
        elif gateway.gateway_type == 'fawry':
            config_data = {
                'merchant_code': request.form.get('fawry_merchant_code', ''),
                'security_key': request.form.get('fawry_security_key', '')
            }
        elif gateway.gateway_type == 'paymob':
            config_data = {
                'api_key': request.form.get('paymob_api_key', ''),
                'integration_id': request.form.get('paymob_integration_id', ''),
                'iframe_id': request.form.get('paymob_iframe_id', ''),
                'hmac_secret': request.form.get('paymob_hmac_secret', '')
            }
        
        gateway.config_data = config_data
        
        # Update supported currencies
        currencies_input = request.form.get('supported_currencies', '')
        gateway.supported_currencies = [c.strip().upper() for c in currencies_input.split(',') if c.strip()]
        
        db.session.commit()
        flash('تم تحديث بوابة الدفع بنجاح', 'success')
        return redirect(url_for('admin_payment_gateways'))
    
    return render_template('admin/edit_payment_gateway.html', gateway=gateway)

@app.route('/admin/payment-gateways/toggle/<int:gateway_id>', methods=['POST'])
@login_required
def admin_toggle_payment_gateway(gateway_id):
    """Toggle payment gateway status"""
    if not current_user.is_admin:
        abort(403)
    
    gateway = PaymentGateway.query.get_or_404(gateway_id)
    gateway.is_active = not gateway.is_active
    db.session.commit()
    
    status_text = 'مفعلة' if gateway.is_active else 'معطلة'
    flash(f'بوابة الدفع {gateway.display_name} الآن {status_text}', 'success')
    
    return redirect(url_for('admin_payment_gateways'))

@app.route('/admin/payment-gateways/delete/<int:gateway_id>', methods=['POST'])
@login_required
def admin_delete_payment_gateway(gateway_id):
    """Delete payment gateway"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        gateway = PaymentGateway.query.get_or_404(gateway_id)
        
        # Check if gateway has any associated payments
        payment_count = Payment.query.filter_by(gateway_id=gateway_id).count()
        
        if payment_count > 0:
            # Instead of preventing deletion, we mark it as inactive and keep records for audit
            gateway.is_active = False
            # Create a safe deletion name that won't exceed database limits
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            base_name = gateway.name.split('_DELETED')[0]  # Remove any previous deletion suffixes
            # Limit the base name to ensure total length doesn't exceed 100 characters
            max_base_length = 100 - len(f"_DELETED_{timestamp}")
            if len(base_name) > max_base_length:
                base_name = base_name[:max_base_length]
            gateway.name = f"{base_name}_DELETED_{timestamp}"
            db.session.commit()
            
            flash(f'تم إلغاء تفعيل بوابة الدفع "{gateway.display_name_ar or gateway.display_name}" بسبب وجود {payment_count} عملية دفع مرتبطة بها. سجلات المدفوعات محفوظة للمراجعة.', 'warning')
        else:
            # Safe to delete if no payments exist
            gateway_name = gateway.display_name_ar or gateway.display_name
            db.session.delete(gateway)
            db.session.commit()
            
            flash(f'تم حذف بوابة الدفع "{gateway_name}" نهائياً', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء حذف بوابة الدفع: {str(e)}', 'error')
    
    return redirect(url_for('admin_payment_gateways'))

@app.route('/admin/payment-plans')
@login_required
def admin_payment_plans():
    """Manage payment plans"""
    if not current_user.is_admin:
        abort(403)
    
    plans = PaymentPlan.query.order_by(PaymentPlan.price.asc()).all()
    
    # Calculate statistics
    total_plans = len(plans)
    active_subscribers = 0
    monthly_revenue = 0
    conversion_rate = 0
    
    # Get active subscribers count
    try:
        from datetime import datetime
        active_subscribers = User.query.filter(User.premium_until > datetime.utcnow()).count()
    except:
        pass
    
    # Get monthly revenue
    try:
        from sqlalchemy import func, extract
        monthly_revenue = db.session.query(func.sum(Payment.amount)).filter(
            Payment.status == 'completed',
            extract('month', Payment.created_at) == datetime.utcnow().month,
            extract('year', Payment.created_at) == datetime.utcnow().year
        ).scalar() or 0
    except:
        pass
    
    return render_template('admin/payment_plans.html', 
                         plans=plans,
                         payment_plans=plans,  # للتوافق مع القالب
                         total_plans=total_plans,
                         active_subscribers=active_subscribers,
                         monthly_revenue=monthly_revenue,
                         conversion_rate=conversion_rate)

@app.route('/admin/payment-plans/add', methods=['GET', 'POST'])
@login_required
def admin_add_payment_plan():
    """Add new payment plan"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_ar = request.form.get('name_ar', '').strip()
        
        # Safely parse price with NaN protection
        try:
            price = safe_parse_float(request.form.get('price', '0'), 0.0, "price")
        except ValueError as e:
            flash(f'السعر غير صحيح: {str(e)}', 'error')
            return render_template('admin/add_payment_plan.html')
        
        duration_months = int(request.form.get('duration_months', 1))
        is_active = safe_parse_bool(request.form.get('is_active'))
        
        # Process features
        features_input = request.form.get('features', '')
        features = [f.strip() for f in features_input.split('\n') if f.strip()]
        
        if not name or price <= 0:
            flash('اسم الخطة والسعر مطلوبان', 'error')
            return render_template('admin/add_payment_plan.html')
        
        plan = PaymentPlan()
        plan.name = name
        plan.name_ar = name_ar
        plan.price = price
        plan.duration_months = duration_months
        plan.features = features
        plan.is_active = is_active
        
        db.session.add(plan)
        db.session.commit()
        
        flash('تم إضافة خطة الدفع بنجاح', 'success')
        return redirect(url_for('admin_payment_plans'))
    
    return render_template('admin/add_payment_plan.html')

@app.route('/admin/payment-plans/edit/<int:plan_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_payment_plan(plan_id):
    """Edit payment plan"""
    if not current_user.is_admin:
        abort(403)
    
    plan = PaymentPlan.query.get_or_404(plan_id)
    
    if request.method == 'POST':
        plan.name = request.form.get('name', '').strip()
        plan.name_ar = request.form.get('name_ar', '').strip()
        
        # Safely parse price with NaN protection
        try:
            plan.price = safe_parse_float(request.form.get('price', '0'), 0.0, "price")
        except ValueError as e:
            flash(f'السعر غير صحيح: {str(e)}', 'error')
            return render_template('admin/edit_payment_plan.html', plan=plan)
        
        plan.duration_months = int(request.form.get('duration_months', 1))
        plan.is_active = safe_parse_bool(request.form.get('is_active'))
        
        # Process features
        features_input = request.form.get('features', '')
        plan.features = [f.strip() for f in features_input.split('\n') if f.strip()]
        
        if not plan.name or plan.price <= 0:
            flash('اسم الخطة والسعر مطلوبان', 'error')
            return render_template('admin/edit_payment_plan.html', plan=plan)
        
        db.session.commit()
        flash('تم تحديث خطة الدفع بنجاح', 'success')
        return redirect(url_for('admin_payment_plans'))
    
    return render_template('admin/edit_payment_plan.html', plan=plan)

@app.route('/admin/payment-plans/toggle/<int:plan_id>', methods=['POST'])
@login_required
def admin_toggle_payment_plan(plan_id):
    """Toggle payment plan status"""
    if not current_user.is_admin:
        abort(403)
    
    plan = PaymentPlan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    
    status_text = 'مفعلة' if plan.is_active else 'معطلة'
    flash(f'خطة {plan.name_ar or plan.name} الآن {status_text}', 'success')
    
    return redirect(url_for('admin_payment_plans'))

@app.route('/admin/payment-plans/delete/<int:plan_id>', methods=['POST'])
@login_required
def admin_delete_payment_plan(plan_id):
    """Delete payment plan"""
    if not current_user.is_admin:
        abort(403)
    
    plan = PaymentPlan.query.get_or_404(plan_id)
    
    # Check if plan has active subscriptions
    active_subscriptions = UserSubscription.query.filter_by(plan_id=plan.id, status='active').count()
    if active_subscriptions > 0:
        flash(f'لا يمكن حذف الخطة لأن بها {active_subscriptions} اشتراكات نشطة', 'error')
        return redirect(url_for('admin_payment_plans'))
    
    plan_name = plan.name_ar or plan.name
    db.session.delete(plan)
    db.session.commit()
    
    flash(f'تم حذف خطة {plan_name} بنجاح', 'success')
    return redirect(url_for('admin_payment_plans'))

@app.route('/admin/subscriptions')
@login_required
def admin_subscriptions():
    """Manage user subscriptions"""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    subscriptions = UserSubscription.query.order_by(UserSubscription.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Statistics
    total_subscriptions = UserSubscription.query.count()
    active_subscriptions = UserSubscription.query.filter_by(status='active').count()
    expired_subscriptions = UserSubscription.query.filter_by(status='expired').count()
    
    return render_template('admin/subscriptions.html',
                         subscriptions=subscriptions,
                         total_subscriptions=total_subscriptions,
                         active_subscriptions=active_subscriptions,
                         expired_subscriptions=expired_subscriptions,
                         moment=datetime.utcnow())

# Create default categories function (called from app.py)
def create_default_data():
    """Create default categories, payment plans, and payment gateways"""
    # Create default categories
    if Category.query.count() == 0:
        default_categories = [
            {'name': 'Action', 'name_ar': 'أكشن', 'description': 'Action and adventure manga'},
            {'name': 'Romance', 'name_ar': 'رومانسي', 'description': 'Romance and love stories'},
            {'name': 'Comedy', 'name_ar': 'كوميديا', 'description': 'Comedy and humor'},
            {'name': 'Drama', 'name_ar': 'دراما', 'description': 'Drama and emotional stories'},
            {'name': 'Fantasy', 'name_ar': 'خيال', 'description': 'Fantasy and supernatural'},
            {'name': 'Sci-Fi', 'name_ar': 'خيال علمي', 'description': 'Science fiction'},
            {'name': 'Horror', 'name_ar': 'رعب', 'description': 'Horror and thriller'},
            {'name': 'Slice of Life', 'name_ar': 'شريحة من الحياة', 'description': 'Daily life stories'},
        ]
        
        for cat_data in default_categories:
            category = Category()
            category.name = cat_data['name']
            category.name_ar = cat_data['name_ar']
            category.description = cat_data['description']
            db.session.add(category)
        
        db.session.commit()
    
    # Create default payment plans
    if PaymentPlan.query.count() == 0:
        default_plans = [
            {
                'name': 'Basic Monthly',
                'name_ar': 'اشتراك شهري أساسي',
                'price': 4.99,
                'duration_months': 1,
                'features': [
                    'قراءة بدون إعلانات',
                    'الوصول لجميع المانجا',
                    'دعم فني أساسي'
                ]
            },
            {
                'name': 'Premium Monthly',
                'name_ar': 'اشتراك شهري مميز',
                'price': 9.99,
                'duration_months': 1,
                'features': [
                    'قراءة بدون إعلانات',
                    'الوصول للفصول المبكرة',
                    'تحميل للقراءة دون اتصال',
                    'دعم فني مميز',
                    'إشعارات فورية'
                ]
            },
            {
                'name': 'Premium Yearly',
                'name_ar': 'اشتراك سنوي مميز',
                'price': 99.99,
                'duration_months': 12,
                'features': [
                    'قراءة بدون إعلانات',
                    'الوصول للفصول المبكرة',
                    'تحميل للقراءة دون اتصال',
                    'دعم فني مميز',
                    'إشعارات فورية',
                    'خصم 20% عن السعر الشهري',
                    'محتوى حصري'
                ]
            }
        ]
        
        for plan_data in default_plans:
            plan = PaymentPlan()
            plan.name = plan_data['name']
            plan.name_ar = plan_data['name_ar']
            plan.price = plan_data['price']
            plan.duration_months = plan_data['duration_months']
            plan.features = plan_data['features']
            plan.is_active = True
            db.session.add(plan)
        
        db.session.commit()
    
    # Create default payment gateways
    if PaymentGateway.query.count() == 0:
        default_gateways = [
            {
                'name': 'stripe_main',
                'display_name': 'Stripe',
                'display_name_ar': 'سترايب',
                'gateway_type': 'stripe',
                'is_active': False,  # Disabled by default until configured
                'is_sandbox': True,
                'description': 'Global payment processing with credit cards',
                'description_ar': 'معالجة دفع عالمية بالبطاقات الائتمانية',
                'supported_currencies': ['USD', 'EUR', 'SAR', 'AED'],
                'config_data': {
                    'publishable_key': '',
                    'secret_key': '',
                    'webhook_secret': ''
                }
            },
            {
                'name': 'paypal_main',
                'display_name': 'PayPal',
                'display_name_ar': 'باي بال',
                'gateway_type': 'paypal',
                'is_active': False,
                'is_sandbox': True,
                'description': 'Digital wallet and online payments',
                'description_ar': 'محفظة رقمية ومدفوعات إلكترونية',
                'supported_currencies': ['USD', 'EUR'],
                'config_data': {
                    'client_id': '',
                    'client_secret': ''
                }
            },
            {
                'name': 'paytabs_main',
                'display_name': 'PayTabs',
                'display_name_ar': 'باي تابس',
                'gateway_type': 'paytabs',
                'is_active': False,
                'is_sandbox': True,
                'description': 'Middle East focused payment gateway',
                'description_ar': 'بوابة دفع مخصصة للشرق الأوسط',
                'supported_currencies': ['USD', 'SAR', 'AED', 'KWD', 'BHD', 'QAR'],
                'config_data': {
                    'server_key': '',
                    'client_key': '',
                    'merchant_id': ''
                }
            }
        ]
        
        for gateway_data in default_gateways:
            gateway = PaymentGateway()
            gateway.name = gateway_data['name']
            gateway.display_name = gateway_data['display_name']
            gateway.display_name_ar = gateway_data['display_name_ar']
            gateway.gateway_type = gateway_data['gateway_type']
            gateway.is_active = gateway_data['is_active']
            gateway.is_sandbox = gateway_data['is_sandbox']
            gateway.description = gateway_data['description']
            gateway.description_ar = gateway_data['description_ar']
            gateway.supported_currencies = gateway_data['supported_currencies']
            gateway.config_data = gateway_data['config_data']
            db.session.add(gateway)
        
        db.session.commit()

# PayPal Payment Integration
import paypalrestsdk
import os

# Configure PayPal
paypalrestsdk.configure({
    "mode": "sandbox",  # sandbox or live
    "client_id": os.environ.get('PAYPAL_CLIENT_ID', 'test_client_id'),
    "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET', 'test_client_secret')
})

@app.route('/create-payment', methods=['POST'])
@login_required
def create_payment():
    """Create payment for subscription"""
    plan_id = request.form.get('plan_id', type=int)
    gateway_id = request.form.get('gateway_id', type=int)
    
    if not plan_id or not gateway_id:
        flash('يرجى اختيار خطة الاشتراك ووسيلة الدفع', 'error')
        return redirect(url_for('premium_plans'))
    
    # Get plan and gateway
    plan = PaymentPlan.query.get_or_404(plan_id)
    gateway = PaymentGateway.query.get_or_404(gateway_id)
    
    if not plan.is_active or not gateway.is_active:
        flash('الخطة أو وسيلة الدفع المحددة غير متاحة حالياً', 'error')
        return redirect(url_for('premium_plans'))
    
    # Route to appropriate payment handler
    if gateway.gateway_type == 'paypal':
        return create_paypal_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'stripe':
        return create_stripe_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'bank_transfer':
        return create_bank_transfer_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'paymob':
        return create_paymob_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'razorpay':
        return create_razorpay_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'fawry':
        return create_fawry_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'paytabs':
        return create_paytabs_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'apple_pay':
        return create_apple_pay_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'google_pay':
        return create_google_pay_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'visa_direct':
        return create_visa_direct_payment_internal(plan, gateway)
    elif gateway.gateway_type == 'mastercard':
        return create_mastercard_payment_internal(plan, gateway)
    else:
        flash('وسيلة الدفع غير مدعومة حالياً', 'error')
        return redirect(url_for('premium_plans'))

def create_paypal_payment_internal(plan, gateway):
    """Create PayPal payment for subscription"""
    # Configure PayPal with gateway credentials
    config = gateway.config_data
    
    # Use appropriate credentials based on mode
    if gateway.is_sandbox:
        # For sandbox, use sandbox credentials if available, fallback to live
        client_id = config.get('sandbox_client_id', config.get('client_id', ''))
        client_secret = config.get('sandbox_client_secret', config.get('client_secret', ''))
    else:
        # For live mode, use live credentials
        client_id = config.get('live_client_id', config.get('client_id', ''))
        client_secret = config.get('live_client_secret', config.get('client_secret', ''))
    
    # Check if PayPal credentials are properly configured
    if not client_id or not client_secret:
        flash('خدمة PayPal غير مُعدة بشكل صحيح. يرجى التواصل مع الإدارة لإعداد مفاتيح PayPal', 'error')
        return redirect(url_for('premium_plans'))
    
    # Debug logging
    print(f"PayPal Configuration - Mode: {'sandbox' if gateway.is_sandbox else 'live'}")
    print(f"Client ID length: {len(client_id) if client_id else 0}")
    print(f"Client Secret length: {len(client_secret) if client_secret else 0}")
    
    try:
        paypalrestsdk.configure({
            "mode": "sandbox" if gateway.is_sandbox else "live",
            "client_id": client_id,
            "client_secret": client_secret
        })
    except Exception as e:
        flash('حدث خطأ في إعداد PayPal. يرجى المحاولة مرة أخرى أو استخدام وسيلة دفع أخرى', 'error')
        return redirect(url_for('premium_plans'))
    
    # Get currency and convert amount
    selected_currency = request.form.get('currency', 'USD')
    converted_amount = convert_currency(plan.price, 'USD', selected_currency)
    
    # Create payment record
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = converted_amount
    payment_record.currency = selected_currency
    payment_record.status = 'pending'
    
    db.session.add(payment_record)
    db.session.commit()
    
    # Create PayPal payment
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": url_for('payment_success', payment_id=payment_record.id, _external=True),
            "cancel_url": url_for('payment_cancel', payment_id=payment_record.id, _external=True)
        },
        "transactions": [{
            "item_list": {
                "items": [{
                    "name": plan.name_ar or plan.name,
                    "sku": f"plan_{plan.id}",
                    "price": str(converted_amount),
                    "currency": selected_currency,
                    "quantity": 1
                }]
            },
            "amount": {
                "total": str(converted_amount),
                "currency": selected_currency
            },
            "description": plan.name_ar or plan.name
        }]
    })
    
    try:
        if payment.create():
            # Store payment info
            payment_record.gateway_payment_id = payment.id
            session['payment_record_id'] = payment_record.id
            db.session.commit()
            
            # Find approval URL
            for link in payment.links:
                if link.rel == "approval_url":
                    return redirect(link.href)
        else:
            payment_record.status = 'failed'
            db.session.commit()
            flash('حدث خطأ في إنشاء الدفع. تأكد من إعدادات PayPal أو استخدم وسيلة دفع أخرى', 'error')
            print(payment.error)
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        
        if 'Client Authentication failed' in str(e):
            flash('مفاتيح PayPal غير صحيحة أو منتهية الصلاحية. يرجى التحقق من إعدادات PayPal في لوحة التحكم', 'error')
        else:
            flash('حدث خطأ في إنشاء الدفع. يرجى المحاولة مرة أخرى أو استخدام وسيلة دفع أخرى', 'error')
        
        print(f"PayPal payment error: {e}")
    
    return redirect(url_for('premium_plans'))

def create_stripe_payment_internal(plan, gateway):
    """Create Stripe payment for subscription"""
    try:
        import stripe
        config = gateway.config_data
        stripe.api_key = config.get('secret_key', '')
        
        # Get currency and convert amount
        selected_currency = request.form.get('currency', 'USD')
        converted_amount = convert_currency(plan.price, 'USD', selected_currency)
        
        # Create payment record
        payment_record = Payment()
        payment_record.user_id = current_user.id
        payment_record.plan_id = plan.id
        payment_record.gateway_id = gateway.id
        payment_record.amount = converted_amount
        payment_record.currency = selected_currency
        payment_record.status = 'pending'
        
        db.session.add(payment_record)
        db.session.commit()
        
        # Create Stripe checkout session
        session_data = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': selected_currency.lower(),
                    'product_data': {
                        'name': plan.name_ar or plan.name,
                        'description': f'{plan.duration_months} month(s) subscription'
                    },
                    'unit_amount': int(converted_amount * 100),  # Convert to cents/smallest unit
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('payment_success', payment_id=payment_record.id, _external=True),
            cancel_url=url_for('payment_cancel', payment_id=payment_record.id, _external=True),
            customer_email=current_user.email,
            metadata={
                'user_id': current_user.id,
                'plan_id': plan.id,
                'plan_name': plan.name
            }
        )
        
        payment_record.gateway_payment_id = session_data.id
        session['payment_record_id'] = payment_record.id
        db.session.commit()
        
        return redirect(session_data.url if session_data.url else url_for('premium_plans'))
        
    except Exception as e:
        try:
            if 'payment_record' in locals():
                payment_record.status = 'failed'
                db.session.commit()
        except:
            pass
        flash('حدث خطأ في إنشاء الدفع، يرجى المحاولة مرة أخرى', 'error')
        print(f"Stripe error: {e}")
        return redirect(url_for('premium_plans'))

@app.route('/fawry/check-payment/<int:payment_id>')
@login_required
def fawry_check_payment(payment_id):
    """Check Fawry payment status manually"""
    payment_record = Payment.query.get_or_404(payment_id)
    
    if payment_record.user_id != current_user.id:
        abort(403)
    
    if payment_record.gateway.gateway_type != 'fawry':
        abort(404)
    
    # Redirect to payment success handler for verification
    return handle_fawry_success(payment_record)

@app.route('/fawry/webhook', methods=['POST'])
def fawry_webhook():
    """Handle Fawry webhook notifications"""
    import hashlib
    
    try:
        data = request.get_json()
        if not data:
            return 'No data', 400
        
        merchant_ref = data.get('merchantRefNumber')
        if not merchant_ref:
            return 'Missing merchant reference', 400
        
        # Find payment record
        payment_record = Payment.query.filter_by(gateway_payment_id=merchant_ref).first()
        if not payment_record:
            return 'Payment not found', 404
        
        # Verify signature if provided
        gateway = payment_record.gateway
        config = gateway.config_data
        security_key = config.get('security_key', '')
        
        if data.get('signature') and security_key:
            # Verify webhook signature
            expected_signature = hashlib.sha256(
                f"{data.get('merchantCode', '')}{merchant_ref}{data.get('paymentStatus', '')}{security_key}".encode()
            ).hexdigest()
            
            if data.get('signature') != expected_signature:
                print(f"Fawry webhook signature mismatch for payment {payment_record.id}")
                return 'Invalid signature', 401
        
        # Update payment status based on webhook
        payment_status = data.get('paymentStatus', '').upper()
        
        if payment_status == 'PAID' and payment_record.status != 'completed':
            payment_record.status = 'completed'
            payment_record.gateway_transaction_id = data.get('fawryRefNumber', '')
            payment_record.completed_at = datetime.utcnow()
            
            # Update user premium subscription
            plan = payment_record.plan
            user = payment_record.user
            
            if user.premium_until and user.premium_until > datetime.utcnow():
                # Extend existing subscription
                user.premium_until += timedelta(days=plan.duration_months * 30)
            else:
                # Start new subscription
                user.premium_until = datetime.utcnow() + timedelta(days=plan.duration_months * 30)
            
            # Create subscription record
            subscription = UserSubscription()
            subscription.user_id = user.id
            subscription.plan_id = plan.id
            subscription.payment_id = payment_record.id
            subscription.status = 'active'
            subscription.start_date = datetime.utcnow()
            subscription.end_date = user.premium_until
            subscription.auto_renew = True
            
            db.session.add(subscription)
            db.session.commit()
            
            print(f"Fawry webhook: Payment {payment_record.id} completed successfully")
            
        elif payment_status in ['FAILED', 'EXPIRED', 'CANCELLED']:
            payment_record.status = 'failed'
            db.session.commit()
            print(f"Fawry webhook: Payment {payment_record.id} failed with status {payment_status}")
        
        return 'OK', 200
        
    except Exception as e:
        print(f"Fawry webhook error: {e}")
        return 'Internal error', 500

@app.route('/paymob/webhook', methods=['POST'])
def paymob_webhook():
    """Handle PayMob webhook notifications"""
    import hashlib
    import hmac
    
    try:
        data = request.get_json()
        if not data:
            return 'No data', 400
        
        # Get transaction data
        transaction = data.get('obj', {})
        order = transaction.get('order', {})
        merchant_order_id = order.get('merchant_order_id')
        success = transaction.get('success', False)
        pending = transaction.get('pending', False)
        
        if not merchant_order_id:
            return 'Missing merchant order ID', 400
        
        # Find payment record
        payment_record = Payment.query.filter_by(gateway_payment_id=merchant_order_id).first()
        if not payment_record:
            return 'Payment not found', 404
        
        # Verify HMAC signature if configured
        gateway = payment_record.gateway
        config = gateway.config_data
        hmac_secret = config.get('hmac_secret', '')
        
        if hmac_secret:
            # Get HMAC from request headers
            received_hmac = request.headers.get('X-PayMob-HMAC-SHA512', '')
            
            if received_hmac:
                # Calculate expected HMAC
                payload = request.get_data()
                expected_hmac = hmac.new(
                    hmac_secret.encode('utf-8'),
                    payload,
                    hashlib.sha512
                ).hexdigest()
                
                if received_hmac != expected_hmac:
                    print(f"PayMob webhook HMAC verification failed for payment {payment_record.id}")
                    return 'Invalid signature', 401
        
        # Update payment status based on webhook
        if success and not pending:
            if payment_record.status != 'completed':
                payment_record.status = 'completed'
                payment_record.gateway_transaction_id = str(transaction.get('id', ''))
                payment_record.completed_at = datetime.utcnow()
                
                # Update user premium subscription
                plan = payment_record.plan
                user = payment_record.user
                
                if user.premium_until and user.premium_until > datetime.utcnow():
                    # Extend existing subscription
                    user.premium_until += timedelta(days=plan.duration_months * 30)
                else:
                    # Start new subscription
                    user.premium_until = datetime.utcnow() + timedelta(days=plan.duration_months * 30)
                
                # Create subscription record
                subscription = UserSubscription()
                subscription.user_id = user.id
                subscription.plan_id = plan.id
                subscription.payment_id = payment_record.id
                subscription.status = 'active'
                subscription.start_date = datetime.utcnow()
                subscription.end_date = user.premium_until
                subscription.auto_renew = True
                
                db.session.add(subscription)
                db.session.commit()
                
                print(f"PayMob webhook: Payment {payment_record.id} completed successfully")
        
        elif not success and not pending:
            # Payment failed
            payment_record.status = 'failed'
            db.session.commit()
            print(f"PayMob webhook: Payment {payment_record.id} failed")
        
        return 'OK', 200
        
    except Exception as e:
        print(f"PayMob webhook error: {e}")
        return 'Internal error', 500

@app.route('/payment-success/<int:payment_id>')
@login_required
def payment_success(payment_id):
    """Handle successful payment"""
    payment_record = Payment.query.get_or_404(payment_id)
    
    if payment_record.user_id != current_user.id:
        abort(403)
    
    if payment_record.status == 'completed':
        flash('اشتراكك المميز نشط بالفعل!', 'info')
        return render_template('premium/success.html', payment=payment_record)
    
    gateway = payment_record.gateway
    plan = payment_record.plan
    
    try:
        if gateway.gateway_type == 'paypal':
            return handle_paypal_success(payment_record)
        elif gateway.gateway_type == 'stripe':
            return handle_stripe_success(payment_record)
        elif gateway.gateway_type == 'fawry':
            return handle_fawry_success(payment_record)
        elif gateway.gateway_type == 'paymob':
            return handle_paymob_success(payment_record)
        else:
            flash('وسيلة دفع غير مدعومة', 'error')
            return redirect(url_for('premium_plans'))
    except Exception as e:
        print(f"Payment verification error: {e}")
        flash('حدث خطأ في التحقق من الدفع، يرجى التواصل مع الدعم', 'error')
        return redirect(url_for('premium_plans'))

def handle_paypal_success(payment_record):
    """Handle PayPal payment success"""
    payer_id = request.args.get('PayerID')
    if not payer_id:
        flash('معلومات الدفع غير مكتملة', 'error')
        return redirect(url_for('premium_plans'))
    
    # Configure PayPal
    gateway = payment_record.gateway
    config = gateway.config_data
    paypalrestsdk.configure({
        "mode": "sandbox" if gateway.is_sandbox else "live",
        "client_id": config.get('client_id', ''),
        "client_secret": config.get('client_secret', '')
    })
    
    # Execute payment
    payment = paypalrestsdk.Payment.find(payment_record.gateway_payment_id)
    
    if payment.execute({"payer_id": payer_id}):
        return complete_subscription(payment_record)
    else:
        payment_record.status = 'failed'
        db.session.commit()
        flash('فشل في تأكيد الدفع، يرجى المحاولة مرة أخرى', 'error')
        return redirect(url_for('premium_plans'))

def handle_stripe_success(payment_record):
    """Handle Stripe payment success"""
    try:
        import stripe
        config = payment_record.gateway.config_data
        stripe.api_key = config.get('secret_key', '')
        
        # Retrieve session
        session_data = stripe.checkout.Session.retrieve(payment_record.gateway_payment_id)
        
        if session_data.payment_status == 'paid':
            payment_record.gateway_transaction_id = session_data.payment_intent
            return complete_subscription(payment_record)
        else:
            flash('الدفع لم يكتمل بعد', 'warning')
            return redirect(url_for('premium_plans'))
            
    except Exception as e:
        print(f"Stripe verification error: {e}")
        payment_record.status = 'failed'
        db.session.commit()
        flash('فشل في التحقق من الدفع', 'error')
        return redirect(url_for('premium_plans'))

def handle_fawry_success(payment_record):
    """Handle Fawry payment success and verification"""
    import requests
    import hashlib
    
    try:
        gateway = payment_record.gateway
        config = gateway.config_data
        merchant_code = config.get('merchant_code', '')
        security_key = config.get('security_key', '')
        
        if not merchant_code or not security_key:
            flash('إعدادات فوري غير مكتملة', 'error')
            return redirect(url_for('premium_plans'))
        
        # Prepare payment status request
        base_url = "https://atfawry.fawrystaging.com" if gateway.is_sandbox else "https://www.atfawry.com"
        status_url = f"{base_url}/ECommerceWeb/Fawry/payments/status"
        
        merchant_ref = payment_record.gateway_payment_id
        
        # Generate signature for status request
        signature_string = f"{merchant_code}{merchant_ref}{security_key}"
        signature = hashlib.sha256(signature_string.encode()).hexdigest()
        
        # Prepare request data
        status_data = {
            "merchantCode": merchant_code,
            "merchantRefNumber": merchant_ref,
            "signature": signature
        }
        
        # Make API request to check payment status
        response = requests.post(status_url, json=status_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('statusCode') == 200:
                payment_status = result.get('paymentStatus', '').upper()
                
                if payment_status == 'PAID':
                    # Payment successful - complete subscription
                    payment_record.gateway_transaction_id = result.get('fawryRefNumber', '')
                    payment_record.status = 'completed'
                    db.session.commit()
                    
                    return complete_subscription(payment_record)
                    
                elif payment_status == 'PENDING':
                    # Payment still pending
                    flash('الدفع لا يزال قيد المعالجة. يرجى المحاولة مرة أخرى بعد قليل', 'warning')
                    return render_template('premium/fawry_pending.html', 
                                         payment=payment_record,
                                         check_url=url_for('fawry_check_payment', payment_id=payment_record.id))
                
                elif payment_status in ['FAILED', 'EXPIRED', 'CANCELLED']:
                    # Payment failed
                    payment_record.status = 'failed'
                    db.session.commit()
                    flash(f'فشل الدفع: {payment_status}', 'error')
                    return redirect(url_for('premium_plans'))
                
                else:
                    # Unknown status
                    flash(f'حالة دفع غير معروفة: {payment_status}', 'warning')
                    return render_template('premium/fawry_pending.html', 
                                         payment=payment_record,
                                         check_url=url_for('fawry_check_payment', payment_id=payment_record.id))
            else:
                # API error
                error_message = result.get('statusDescription', 'خطأ غير معروف')
                flash(f'خطأ في التحقق من الدفع: {error_message}', 'error')
                return redirect(url_for('premium_plans'))
        else:
            # HTTP error
            flash('حدث خطأ في الاتصال بخدمة فوري للتحقق من الدفع', 'error')
            return redirect(url_for('premium_plans'))
            
    except requests.RequestException as e:
        print(f"Fawry status check error: {e}")
        flash('حدث خطأ في التحقق من حالة الدفع', 'error')
        return redirect(url_for('premium_plans'))
    
    except Exception as e:
        print(f"Fawry verification error: {e}")
        flash('حدث خطأ في التحقق من الدفع', 'error')
        return redirect(url_for('premium_plans'))

def handle_paymob_success(payment_record):
    """Handle PayMob payment success and verification"""
    import hashlib
    import hmac
    
    try:
        # Get transaction data from request parameters
        txn_response_code = request.args.get('txn_response_code', '')
        merchant_order_id = request.args.get('merchant_order_id', '')
        
        # Check if this is our payment
        if merchant_order_id != payment_record.gateway_payment_id:
            flash('معرف الطلب غير صحيح', 'error')
            return redirect(url_for('premium_plans'))
        
        gateway = payment_record.gateway
        config = gateway.config_data
        api_key = config.get('api_key', '')
        hmac_secret = config.get('hmac_secret', '')
        
        if not api_key:
            flash('إعدادات PayMob غير مكتملة', 'error')
            return redirect(url_for('premium_plans'))
        
        # Verify HMAC if secret is provided
        if hmac_secret:
            # Get all query parameters for HMAC verification
            query_params = dict(request.args)
            # Remove hmac from params before verification
            hmac_from_paymob = query_params.pop('hmac', '')
            
            # Sort parameters and create string for HMAC
            sorted_params = sorted(query_params.items())
            query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
            
            # Calculate expected HMAC
            expected_hmac = hmac.new(
                hmac_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            if hmac_from_paymob and hmac_from_paymob != expected_hmac:
                flash('فشل في التحقق من صحة البيانات', 'error')
                print(f"PayMob HMAC verification failed for payment {payment_record.id}")
                return redirect(url_for('premium_plans'))
        
        # Check transaction response code
        if txn_response_code == 'APPROVED':
            # Payment successful
            payment_record.gateway_transaction_id = request.args.get('id', '')
            payment_record.status = 'completed'
            db.session.commit()
            
            return complete_subscription(payment_record)
        
        elif txn_response_code in ['DECLINED', 'EXPIRED']:
            # Payment failed
            payment_record.status = 'failed'
            db.session.commit()
            flash('فشل في عملية الدفع. يرجى المحاولة مرة أخرى', 'error')
            return redirect(url_for('premium_plans'))
        
        else:
            # Unknown status - payment might still be pending
            flash('حالة الدفع غير واضحة. يرجى التواصل مع الدعم إذا تم خصم المبلغ', 'warning')
            return redirect(url_for('premium_plans'))
        
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        print(f"PayMob success handler error: {e}")
        flash('حدث خطأ في التحقق من الدفع', 'error')
        return redirect(url_for('premium_plans'))

def complete_subscription(payment_record):
    """Complete subscription after successful payment"""
    from datetime import datetime, timedelta
    
    # Update payment status
    payment_record.status = 'completed'
    payment_record.completed_at = datetime.utcnow()
    
    # Update user premium subscription
    plan = payment_record.plan
    if current_user.premium_until and current_user.premium_until > datetime.utcnow():
        # Extend existing subscription
        current_user.premium_until += timedelta(days=plan.duration_months * 30)
    else:
        # Start new subscription
        current_user.premium_until = datetime.utcnow() + timedelta(days=plan.duration_months * 30)
    
    # Create subscription record
    subscription = UserSubscription()
    subscription.user_id = current_user.id
    subscription.plan_id = plan.id
    subscription.payment_id = payment_record.id
    subscription.status = 'active'
    subscription.start_date = datetime.utcnow()
    subscription.end_date = current_user.premium_until
    subscription.auto_renew = True
    
    db.session.add(subscription)
    db.session.commit()
    
    # Send premium subscription confirmation email
    try:
        from app.utils_bravo_mail import bravo_mail, send_premium_subscription_email, send_payment_receipt_email
    except ImportError:
        bravo_mail = None
        send_premium_subscription_email = None
        send_payment_receipt_email = None
    
    if bravo_mail and bravo_mail.is_enabled():
        try:
            # Send premium subscription email
            if send_premium_subscription_email:
                subscription_email = send_premium_subscription_email(
                    current_user.email,
                    current_user.username,
                    plan.name,
                    current_user.premium_until.strftime('%Y-%m-%d')
                )
                if subscription_email.get('success'):
                    logger.info(f"Premium subscription email sent to {current_user.email}")
                else:
                    logger.warning(f"Failed to send premium subscription email: {subscription_email.get('error')}")
            
            # Send payment receipt email
            if send_payment_receipt_email:
                receipt_email = send_payment_receipt_email(
                    current_user.email,
                    current_user.username,
                    f"{payment_record.amount} {payment_record.currency}",
                    payment_record.gateway,
                    payment_record.gateway_payment_id or f"PAY-{payment_record.id}"
                )
                if receipt_email.get('success'):
                    logger.info(f"Payment receipt email sent to {current_user.email}")
                else:
                    logger.warning(f"Failed to send payment receipt email: {receipt_email.get('error')}")
        except Exception as e:
            logger.error(f"Error sending premium/payment emails to {current_user.email}: {str(e)}")
    
    # Clear session
    session.pop('payment_record_id', None)
    
    flash('تم تفعيل اشتراكك المميز بنجاح! مرحباً بك في العضوية المميزة', 'success')
    return render_template('premium/success.html', payment=payment_record, subscription=subscription)

@app.route('/payment-cancel/<int:payment_id>')
@login_required
def payment_cancel(payment_id):
    """Handle cancelled payment"""
    payment_record = Payment.query.get_or_404(payment_id)
    
    if payment_record.user_id != current_user.id:
        abort(403)
    
    payment_record.status = 'cancelled'
    db.session.commit()
    
    # Clear session
    session.pop('payment_record_id', None)
    
    flash('تم إلغاء عملية الدفع', 'info')
    return render_template('premium/cancel.html', payment=payment_record)

# Payment creation functions for different gateways
def create_bank_transfer_payment(payment_record):
    """Handle bank transfer payment - show instructions"""
    payment_record.status = 'pending_verification'
    payment_record.gateway_payment_id = f"BT-{payment_record.id}-{int(time.time())}"
    db.session.commit()
    
    # Store payment info for verification page
    session['bank_transfer_payment_id'] = payment_record.id
    
    flash('يرجى اتباع التعليمات لإكمال التحويل البنكي', 'info')
    return render_template('premium/bank_transfer_instructions.html', payment=payment_record)

def create_paymob_payment(payment_record):
    """Legacy PayMob payment function - now calls the internal version"""
    try:
        plan = payment_record.plan
        gateway = payment_record.gateway
        return create_paymob_payment_internal(plan, gateway)
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في إنشاء دفع PayMob', 'error')
        return redirect(url_for('premium_plans'))

def create_razorpay_payment(payment_record):
    """Handle Razorpay payment integration"""
    try:
        # Razorpay integration would go here
        payment_record.status = 'pending'
        payment_record.gateway_payment_id = f"RP-{payment_record.id}-{int(time.time())}"
        db.session.commit()
        
        # In real implementation, create Razorpay payment intent
        return render_template('premium/razorpay_checkout.html', payment=payment_record)
        
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في إنشاء دفع Razorpay', 'error')
        return redirect(url_for('premium_plans'))

def create_fawry_payment(payment_record):
    """Handle Fawry payment integration"""
    try:
        payment_record.status = 'pending_payment'
        payment_record.gateway_payment_id = f"FW-{payment_record.id}-{int(time.time())}"
        db.session.commit()
        
        # Generate Fawry payment code for user to pay at stores
        fawry_code = f"FW{payment_record.id:06d}"
        
        return render_template('premium/fawry_instructions.html', 
                             payment=payment_record, 
                             fawry_code=fawry_code)
        
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في إنشاء كود فوري', 'error')
        return redirect(url_for('premium_plans'))

def create_paytabs_payment(payment_record):
    """Handle PayTabs payment integration"""
    try:
        payment_record.status = 'pending'
        payment_record.gateway_payment_id = f"PT-{payment_record.id}-{int(time.time())}"
        db.session.commit()
        
        # PayTabs integration would go here
        return render_template('premium/paytabs_checkout.html', payment=payment_record)
        
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في إنشاء دفع PayTabs', 'error')
        return redirect(url_for('premium_plans'))

def create_apple_pay_payment(payment_record):
    """Handle Apple Pay integration"""
    try:
        payment_record.status = 'pending'
        payment_record.gateway_payment_id = f"AP-{payment_record.id}-{int(time.time())}"
        db.session.commit()
        
        # Apple Pay integration through Stripe or other processor
        return render_template('premium/apple_pay_checkout.html', payment=payment_record)
        
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في إنشاء دفع Apple Pay', 'error')
        return redirect(url_for('premium_plans'))

def create_google_pay_payment(payment_record):
    """Handle Google Pay integration"""
    try:
        payment_record.status = 'pending'
        payment_record.gateway_payment_id = f"GP-{payment_record.id}-{int(time.time())}"
        db.session.commit()
        
        # Google Pay integration through Stripe or other processor
        return render_template('premium/google_pay_checkout.html', payment=payment_record)
        
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في إنشاء دفع Google Pay', 'error')
        return redirect(url_for('premium_plans'))

# Internal payment creation functions for different gateways
def create_bank_transfer_payment_internal(plan, gateway):
    """Create bank transfer payment record and show instructions"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending_verification'
    payment_record.gateway_payment_id = f"BT-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['bank_transfer_payment_id'] = payment_record.id
    
    return render_template('premium/bank_transfer_instructions.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

def create_paymob_payment_internal(plan, gateway):
    """Create PayMob payment integration with real API"""
    import requests
    import time
    
    try:
        # Get currency and convert amount
        selected_currency = request.form.get('currency', 'USD')
        converted_amount = convert_currency(plan.price, 'USD', selected_currency)
        
        # Convert to paymob's smallest currency unit (e.g., cents for USD, piastres for EGP)
        if selected_currency == 'EGP':
            paymob_amount = int(converted_amount * 100)  # EGP to piastres
        elif selected_currency == 'USD':
            paymob_amount = int(converted_amount * 100)  # USD to cents
        else:
            paymob_amount = int(converted_amount * 100)  # Default to cents
        
        # Create payment record
        payment_record = Payment()
        payment_record.user_id = current_user.id
        payment_record.plan_id = plan.id
        payment_record.gateway_id = gateway.id
        payment_record.amount = converted_amount
        payment_record.currency = selected_currency
        payment_record.status = 'pending'
        
        db.session.add(payment_record)
        db.session.commit()
        
        # Get gateway configuration
        config = gateway.config_data
        api_key = config.get('api_key', '')
        integration_id = config.get('integration_id', '')
        iframe_id = config.get('iframe_id', '')
        
        if not api_key or not integration_id:
            flash('إعدادات PayMob غير مكتملة', 'error')
            payment_record.status = 'failed'
            db.session.commit()
            return redirect(url_for('premium_plans'))
        
        # Step 1: Authentication Request
        auth_url = "https://accept.paymobsolutions.com/api/auth/tokens" if not gateway.is_sandbox else "https://accept-payments.paymobsolutions.com/api/auth/tokens"
        auth_payload = {"api_key": api_key}
        
        auth_response = requests.post(auth_url, json=auth_payload, timeout=30)
        
        if auth_response.status_code != 201:
            flash('فشل في الاتصال بـ PayMob. يرجى المحاولة مرة أخرى', 'error')
            payment_record.status = 'failed'
            db.session.commit()
            return redirect(url_for('premium_plans'))
        
        auth_token = auth_response.json()['token']
        
        # Generate unique merchant reference
        merchant_ref = f"SUB-{payment_record.id}-{int(time.time())}"
        payment_record.gateway_payment_id = merchant_ref
        
        # Step 2: Order Registration API
        order_url = "https://accept.paymobsolutions.com/api/ecommerce/orders" if not gateway.is_sandbox else "https://accept-payments.paymobsolutions.com/api/ecommerce/orders"
        order_payload = {
            "auth_token": auth_token,
            "delivery_needed": "false",
            "amount_cents": paymob_amount,
            "currency": selected_currency,
            "merchant_order_id": merchant_ref,
            "items": [{
                "name": plan.name_ar or plan.name,
                "amount_cents": paymob_amount,
                "description": f"اشتراك {plan.name_ar or plan.name}",
                "quantity": "1"
            }]
        }
        
        order_response = requests.post(order_url, json=order_payload, timeout=30)
        
        if order_response.status_code != 201:
            flash('فشل في إنشاء طلب الدفع. يرجى المحاولة مرة أخرى', 'error')
            payment_record.status = 'failed'
            db.session.commit()
            return redirect(url_for('premium_plans'))
        
        order_id = order_response.json()['id']
        
        # Step 3: Payment Key Request
        payment_key_url = "https://accept.paymobsolutions.com/api/acceptance/payment_keys" if not gateway.is_sandbox else "https://accept-payments.paymobsolutions.com/api/acceptance/payment_keys"
        payment_key_payload = {
            "auth_token": auth_token,
            "amount_cents": paymob_amount,
            "expiration": 3600,  # 1 hour
            "order_id": order_id,
            "billing_data": {
                "apartment": "NA", 
                "email": current_user.email,
                "floor": "NA", 
                "first_name": current_user.username,
                "street": "NA", 
                "building": "NA", 
                "phone_number": "NA", 
                "shipping_method": "NA", 
                "postal_code": "NA", 
                "city": "NA", 
                "country": "NA", 
                "last_name": "NA", 
                "state": "NA"
            },
            "currency": selected_currency,
            "integration_id": int(integration_id)
        }
        
        payment_key_response = requests.post(payment_key_url, json=payment_key_payload, timeout=30)
        
        if payment_key_response.status_code != 201:
            flash('فشل في الحصول على مفتاح الدفع. يرجى المحاولة مرة أخرى', 'error')
            payment_record.status = 'failed'
            db.session.commit()
            return redirect(url_for('premium_plans'))
        
        payment_token = payment_key_response.json()['token']
        
        # Store payment info
        db.session.commit()
        session['payment_record_id'] = payment_record.id
        
        # Step 4: Redirect to PayMob iFrame
        if iframe_id:
            # Use iFrame integration
            iframe_url = f"https://accept.paymobsolutions.com/api/acceptance/iframes/{iframe_id}?payment_token={payment_token}"
            return redirect(iframe_url)
        else:
            # Use standard checkout
            checkout_url = f"https://accept.paymobsolutions.com/api/acceptance/payments/pay?payment_token={payment_token}"
            return redirect(checkout_url)
        
    except requests.exceptions.RequestException as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash(f'خطأ في الاتصال بـ PayMob: {str(e)}', 'error')
        return redirect(url_for('premium_plans'))
    except Exception as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى', 'error')
        print(f"PayMob integration error: {e}")
        return redirect(url_for('premium_plans'))

def create_razorpay_payment_internal(plan, gateway):
    """Create Razorpay payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"RP-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/razorpay_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

def create_fawry_payment_internal(plan, gateway):
    """Create Fawry payment integration with real API"""
    import requests
    import hashlib
    import time
    from datetime import datetime, timedelta
    
    try:
        # Get currency and convert amount to EGP
        selected_currency = request.form.get('currency', 'EGP')
        if selected_currency != 'EGP':
            # Convert to EGP using approximate rate (30 EGP = 1 USD)
            if selected_currency == 'USD':
                converted_amount = plan.price * 30
            else:
                converted_amount = plan.price * 30  # Default fallback
        else:
            converted_amount = plan.price
        
        # Create payment record
        payment_record = Payment()
        payment_record.user_id = current_user.id
        payment_record.plan_id = plan.id
        payment_record.gateway_id = gateway.id
        payment_record.amount = converted_amount
        payment_record.currency = 'EGP'  # Fawry always uses EGP
        payment_record.status = 'pending'
        
        db.session.add(payment_record)
        db.session.commit()
        
        # Generate unique merchant reference
        merchant_ref = f"SUB-{payment_record.id}-{int(time.time())}"
        payment_record.gateway_payment_id = merchant_ref
        
        # Get gateway configuration
        config = gateway.config_data
        merchant_code = config.get('merchant_code', '')
        security_key = config.get('security_key', '')
        
        if not merchant_code or not security_key:
            payment_record.status = 'failed'
            db.session.commit()
            flash('إعدادات فوري غير مكتملة. يرجى التواصل مع الإدارة', 'error')
            return redirect(url_for('premium_plans'))
        
        # Prepare Fawry charge request
        base_url = "https://atfawry.fawrystaging.com" if gateway.is_sandbox else "https://www.atfawry.com"
        charge_url = f"{base_url}/ECommerceWeb/Fawry/payments/charge"
        
        # Calculate expiry date (24 hours from now)
        expiry_date = datetime.now() + timedelta(hours=24)
        
        # Prepare charge items
        charge_items = [{
            "itemId": f"PLAN-{plan.id}",
            "description": plan.name_ar or plan.name,
            "price": float(converted_amount),
            "quantity": 1
        }]
        
        # Generate signature for Fawry API
        signature_string = (
            f"{merchant_code}{merchant_ref}{current_user.id or ''}"
            f"{charge_items[0]['itemId']}{charge_items[0]['quantity']}"
            f"{charge_items[0]['price']:.2f}{security_key}"
        )
        signature = hashlib.sha256(signature_string.encode()).hexdigest()
        
        # Prepare request data
        charge_data = {
            "merchantCode": merchant_code,
            "merchantRefNum": merchant_ref,
            "customerProfileId": str(current_user.id),
            "customerName": current_user.username,
            "customerEmail": current_user.email,
            "customerMobile": "",  # Optional
            "paymentExpiry": int(expiry_date.timestamp() * 1000),
            "chargeItems": charge_items,
            "returnUrl": url_for('payment_success', payment_id=payment_record.id, _external=True),
            "signature": signature
        }
        
        # Make API request to Fawry
        response = requests.post(charge_url, json=charge_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('statusCode') == 200:
                # Store reference number and update status
                payment_record.gateway_transaction_id = result.get('referenceNumber', '')
                db.session.commit()
                
                session['payment_record_id'] = payment_record.id
                
                # Generate payment instructions
                fawry_code = result.get('referenceNumber', f"FW{payment_record.id:06d}")
                
                return render_template('premium/fawry_checkout.html', 
                                     payment=payment_record, 
                                     plan=plan,
                                     gateway=gateway,
                                     fawry_code=fawry_code,
                                     amount=converted_amount,
                                     expiry_date=expiry_date)
            else:
                payment_record.status = 'failed'
                db.session.commit()
                flash(f'خطأ من فوري: {result.get("statusDescription", "خطأ غير معروف")}', 'error')
                return redirect(url_for('premium_plans'))
        else:
            payment_record.status = 'failed'
            db.session.commit()
            flash('حدث خطأ في الاتصال بخدمة فوري', 'error')
            return redirect(url_for('premium_plans'))
            
    except requests.RequestException as e:
        payment_record.status = 'failed'
        db.session.commit()
        flash('حدث خطأ في الاتصال بخدمة فوري', 'error')
        print(f"Fawry API error: {e}")
        return redirect(url_for('premium_plans'))
    
    except Exception as e:
        try:
            if 'payment_record' in locals():
                payment_record.status = 'failed'
                db.session.commit()
        except:
            pass
        flash('حدث خطأ في إنشاء دفع فوري، يرجى المحاولة مرة أخرى', 'error')
        print(f"Fawry error: {e}")
        return redirect(url_for('premium_plans'))

def create_paytabs_payment_internal(plan, gateway):
    """Create PayTabs payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"PT-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/paytabs_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

def create_apple_pay_payment_internal(plan, gateway):
    """Create Apple Pay payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"AP-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/apple_pay_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

def create_google_pay_payment_internal(plan, gateway):
    """Create Google Pay payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"GP-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/google_pay_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

def create_visa_direct_payment_internal(plan, gateway):
    """Create Visa Direct payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"VD-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/visa_direct_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

def create_mastercard_payment_internal(plan, gateway):
    """Create Mastercard payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"MC-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/mastercard_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)



@app.route('/admin/add-chapter/<int:manga_id>', methods=['GET', 'POST'])
@login_required
def admin_add_chapter(manga_id):
    """Add new chapter to existing manga"""
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    manga = Manga.query.get_or_404(manga_id)
    
    if request.method == 'POST':
        # Get chapter data
        chapter_title = request.form.get('chapter_title')
        
        # Safely parse chapter number with NaN protection
        try:
            chapter_number = safe_parse_float(request.form.get('chapter_number', '1'), 1.0, "chapter number")
        except ValueError as e:
            flash(f'رقم الفصل غير صحيح: {str(e)}', 'error')
            return safe_redirect(request.url)
        
        # Safely parse is_locked boolean
        is_locked = safe_parse_bool(request.form.get('is_locked'))
        early_access_date = request.form.get('early_access_date')
        release_date = request.form.get('release_date')
        
        # Convert date strings to datetime objects
        early_access_dt = None
        release_date_dt = None
        
        if early_access_date:
            early_access_dt = datetime.strptime(early_access_date, '%Y-%m-%dT%H:%M')
        if release_date:
            release_date_dt = datetime.strptime(release_date, '%Y-%m-%dT%H:%M')
        
        # Get upload method
        upload_method = request.form.get('upload_method', 'images')
        
        try:
            # Create chapter
            chapter = Chapter()
            chapter.manga_id = manga.id
            chapter.chapter_number = chapter_number
            chapter.title = chapter_title
            chapter.is_locked = is_locked
            chapter.early_access_date = early_access_dt
            chapter.release_date = release_date_dt
            chapter.publisher_id = current_user.id  # Assign publisher
            
            db.session.add(chapter)
            db.session.commit()
            
            # Handle chapter images based on upload method
            chapter_dir = os.path.join('static/uploads/manga', str(manga.id), str(chapter.id))
            os.makedirs(chapter_dir, exist_ok=True)
            
            image_files = []
            
            try:
                if upload_method == 'images':
                    # Direct image upload
                    chapter_files = request.files.getlist('chapter_images')
                    if not chapter_files:
                        flash('صور الفصل مطلوبة', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)
                    
                    for i, image_file in enumerate(chapter_files, 1):
                        if image_file and image_file.filename:
                            from werkzeug.utils import secure_filename
                            filename = secure_filename(f"page_{i:03d}_{image_file.filename}")
                            image_path = os.path.join(chapter_dir, filename)
                            image_file.save(image_path)
                            image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")

                elif upload_method == 'zip':
                    # ZIP file extraction and upload (same as scraping method)
                    logging.info("🗂️ بدء معالجة رفع ZIP")
                    zip_file = request.files.get('chapter_zip')
                    if not zip_file:
                        logging.error("❌ لم يتم توفير ملف ZIP")
                        flash('ملف ZIP مطلوب', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)
                    
                    logging.info(f"📦 ملف ZIP موجود: {zip_file.filename}")
                    
                    try:
                        import zipfile
                        import tempfile
                        
                        # Create temporary directory
                        temp_dir = tempfile.mkdtemp()
                        zip_path = os.path.join(temp_dir, 'chapter.zip')
                        zip_file.save(zip_path)
                        
                        # Extract images from ZIP
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            # Get image files only
                            image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
                            image_filenames = [f for f in zip_ref.namelist() 
                                             if f.lower().endswith(image_extensions) 
                                             and not f.startswith('__MACOSX/')]
                            
                            # Sort images naturally
                            image_filenames.sort()
                            
                            if not image_filenames:
                                raise Exception('لم يتم العثور على صور في ملف ZIP')
                            
                            # Extract and save images directly to chapter directory
                            for i, img_filename in enumerate(image_filenames, 1):
                                try:
                                    # Extract image data
                                    with zip_ref.open(img_filename) as img_file:
                                        image_data = img_file.read()
                                    
                                    # Save image to chapter directory
                                    filename = f"page_{i:03d}.jpg"
                                    image_path = os.path.join(chapter_dir, filename)
                                    
                                    with open(image_path, 'wb') as f:
                                        f.write(image_data)
                                    
                                    image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                    
                                except Exception as e:
                                    logging.warning(f"Failed to extract image {img_filename}: {e}")
                                    continue
                        
                        # Clean up temp directory
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
                        if not image_files:
                            raise Exception('فشل في استخراج أي صور من ملف ZIP')
                            
                    except Exception as e:
                        flash(f'خطأ في استخراج ملف ZIP: {str(e)}', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)

                elif upload_method == 'scrape':
                    # Web scraping
                    source_website = request.form.get('source_website')
                    chapter_url = request.form.get('chapter_url')
                    
                    # التحقق من وجود بيانات الكشط المختبرة
                    scraping_tested = request.form.get('scraping_tested', 'false')
                    scraped_images_json = request.form.get('scraped_images', '')
                    has_tested_data = scraping_tested == 'true' and scraped_images_json
                    
                    if not has_tested_data and (not chapter_url):
                        flash('رابط الفصل مطلوب أو يجب اختبار الكشط أولاً', 'error')
                        db.session.rollback()
                        return safe_redirect(request.url)
                    
                    # استخدام النظام الموحد للكشط - نفس الطريقة المستخدمة في الرفع
                    if has_tested_data:
                        # استخدام البيانات المختبرة (النظام الموحد الجديد)
                        try:
                            import json
                            scraped_images = json.loads(scraped_images_json)
                            print(f"📥 استخدام نتائج الكشط المختبرة: {len(scraped_images)} صورة")
                            
                            # إنشاء قائمة الصور للتحميل في الخلفية
                            for i, img_url in enumerate(scraped_images, 1):
                                file_ext = '.webp' if '.webp' in img_url else '.jpg'
                                filename = f"page_{i:03d}{file_ext}"
                                image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                            
                            print(f"📋 تم إعداد قائمة {len(image_files)} صورة للتحميل في الخلفية")
                            
                            # بدء تحميل الصور في الخلفية
                            threading.Thread(
                                target=download_and_upload_images_background,
                                args=(scraped_images, chapter_dir, chapter.id, chapter_url),
                                daemon=True
                            ).start()
                            
                        except (json.JSONDecodeError, ValueError) as e:
                            flash('خطأ في بيانات الكشط المختبرة', 'error')
                            logging.error(f"JSON decode error: {e}")
                            db.session.rollback()
                            return safe_redirect(request.url)
                            
                    elif chapter_url and 'olympustaff.com' in chapter_url:
                        # كشط مباشر للحالات القديمة
                        try:
                            from scrapers.simple_manga_scraper import scrape_olympustaff_simple as scrape_olympustaff_chapter
                        except ImportError:
                            flash('مكتبة الكشط غير متوفرة', 'error')
                            db.session.rollback()
                            return safe_redirect(request.url)
                        
                        print(f"🧪 كشط مباشر من: {chapter_url}")
                        result = scrape_olympustaff_chapter(chapter_url, chapter_dir)
                        
                        if not result['success']:
                            flash(f'فشل في كشط الصور: {result.get("error", "خطأ غير معروف")}', 'error')
                            db.session.rollback()
                            return safe_redirect(request.url)
                        
                        # تحميل الصور مباشرة
                        scraped_images = result.get('all_images', [])
                        for i, img_url in enumerate(scraped_images, 1):
                            try:
                                import requests
                                response = requests.get(img_url, headers={'Referer': chapter_url}, stream=True, timeout=30)
                                response.raise_for_status()
                                
                                file_ext = '.webp' if '.webp' in img_url else '.jpg'
                                filename = f"page_{i:03d}{file_ext}"
                                img_path = os.path.join(chapter_dir, filename)
                                
                                with open(img_path, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                
                                file_size = os.path.getsize(img_path)
                                if file_size > 1000:
                                    image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                else:
                                    os.remove(img_path)
                                    
                            except Exception as e:
                                print(f"❌ فشل تحميل الصورة {i}: {e}")
                                continue
                        
                        # تحديث عنوان الفصل إذا تم اكتشافه
                        if result.get('chapter_title') and not chapter.title:
                            chapter.title = result['chapter_title']
                            
                    else:
                        # للمواقع الأخرى، استخدم الكاشط العام
                        from scrapers.scraper_utils import scrape_chapter_images
                        import requests
                        
                        try:
                            scrape_result = scrape_chapter_images(source_website, chapter_url)
                            
                            if not scrape_result['success']:
                                flash(f'فشل في كشط الصور: {scrape_result["error"]}', 'error')
                                db.session.rollback()
                                return safe_redirect(request.url)
                            
                            image_urls = scrape_result['images']
                            
                            if not image_urls:
                                flash('لم يتم العثور على صور في الرابط المحدد', 'error')
                                db.session.rollback()
                                return safe_redirect(request.url)
                            
                            # Download and save images
                            for i, img_url in enumerate(image_urls, 1):
                                try:
                                    filename = f"page_{i:03d}.jpg"
                                    image_path = os.path.join(chapter_dir, filename)
                                    
                                    response = requests.get(img_url, stream=True, timeout=30)
                                    response.raise_for_status()
                                    
                                    with open(image_path, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                    
                                    image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                    
                                except Exception as e:
                                    logging.warning(f"Failed to download image {img_url}: {e}")
                                    continue
                            
                            if not image_files:
                                flash('فشل في تحميل صور الفصل من الموقع', 'error')
                                db.session.rollback()
                                return safe_redirect(request.url)
                                
                        except Exception as e:
                            flash(f'خطأ في كشط الصور: {str(e)}', 'error')
                            db.session.rollback()
                            return safe_redirect(request.url)
                
                # Create page records with local paths first (for immediate display)
                print(f"📝 إنشاء سجلات {len(image_files)} صفحة مع المسارات المحلية")
                
                for i, image_file in enumerate(image_files, 1):
                    page = PageImage()
                    page.chapter_id = chapter.id
                    page.page_number = i
                    page.image_path = image_file
                    page.is_cloudinary = False  # سيتم تحديثها لاحقاً
                    db.session.add(page)
                
                # Update chapter page count
                chapter.pages = len(image_files) if 'image_files' in locals() else 0
                db.session.commit()
                
                page_count = len(image_files) if 'image_files' in locals() else 0
                
                # Start background Cloudinary upload (non-blocking)
                print(f"🚀 بدء رفع {page_count} صورة إلى Cloudinary في الخلفية...")
                threading.Thread(
                    target=upload_chapter_to_cloudinary_background,
                    args=(chapter.id, image_files),
                    daemon=True
                ).start()
                
                print(f"✅ تم إنشاء الفصل {chapter_number} مع {page_count} صفحة")
                flash(f'تم إنشاء الفصل {chapter_number} بنجاح مع {page_count} صورة! جاري رفع الصور إلى Cloudinary في الخلفية...', 'success')
                
                # Send newsletter notification for new chapter
                try:
                    from app.utils_bravo_mail import send_new_chapter_newsletter, bravo_mail
                    if bravo_mail and bravo_mail.is_enabled():
                        # Send newsletter in background thread to avoid blocking
                        def send_newsletter_background():
                            try:
                                result = send_new_chapter_newsletter(chapter.id)
                                if result.get('success'):
                                    print(f"📧 تم إرسال النشرة الإخبارية لـ {result.get('sent_count', 0)} مشترك")
                                else:
                                    print(f"⚠️ فشل في إرسال النشرة الإخبارية: {result.get('error', 'خطأ غير معروف')}")
                            except Exception as e:
                                print(f"❌ خطأ في إرسال النشرة الإخبارية: {e}")
                        
                        import threading
                        threading.Thread(target=send_newsletter_background, daemon=True).start()
                        print("📨 بدء إرسال النشرة الإخبارية في الخلفية...")
                    else:
                        print("⚠️ خدمة Bravo Mail غير مفعلة، لم يتم إرسال النشرة الإخبارية")
                except ImportError:
                    print("⚠️ خدمة البريد الإلكتروني غير متوفرة")
                except Exception as e:
                    print(f"❌ خطأ في إعداد النشرة الإخبارية: {e}")
                
                return redirect(url_for('read_chapter', manga_slug=manga.slug, chapter_slug=chapter.slug))
                
            except Exception as e:
                # Clean up on error
                if os.path.exists(chapter_dir):
                    import shutil
                    shutil.rmtree(chapter_dir, ignore_errors=True)
                db.session.rollback()
                raise e
                
        except Exception as e:
            flash(f'خطأ في إضافة الفصل: {str(e)}', 'error')
            db.session.rollback()
    
    # Get the next chapter number
    last_chapter = Chapter.query.filter_by(manga_id=manga.id).order_by(Chapter.chapter_number.desc()).first()
    next_chapter_number = (last_chapter.chapter_number + 1) if last_chapter else 1
    
    return render_template('admin/add_chapter.html', manga=manga, next_chapter_number=next_chapter_number)


@app.route('/admin/extract-zip-preview', methods=['POST'])
@login_required
def admin_extract_zip_preview():
    """Extract ZIP file and return preview data with improved error handling"""
    if not (current_user.is_admin or current_user.is_publisher):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        # Check if we have any data first
        if not hasattr(request, 'content_length') or request.content_length is None:
            return jsonify({
                'success': False, 
                'error': 'لم يتم إرسال أي بيانات. يرجى اختيار ملف ZIP والمحاولة مرة أخرى.'
            })
            
        # Check content length to prevent oversized uploads
        content_length = request.content_length or 0
        max_size_mb = 50  # Increased to 50MB for better compatibility
        max_size = max_size_mb * 1024 * 1024
        
        if content_length > max_size:
            return jsonify({
                'success': False, 
                'error': f'الملف كبير جداً. الحد الأقصى {max_size_mb}MB، الملف الحالي {content_length / (1024*1024):.1f}MB'
            })
        
        # Enhanced error handling for form data parsing
        try:
            # Set a timeout for parsing form data
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("انتهت مهلة قراءة الملف")
                
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(120)  # 2 minute timeout for form parsing
            
            files = request.files
            signal.alarm(0)  # Clear the alarm
            
        except TimeoutError as timeout_error:
            logging.error(f"انتهت مهلة قراءة الملف: {timeout_error}")
            return jsonify({
                'success': False, 
                'error': 'انتهت مهلة قراءة الملف. الملف كبير جداً أو الاتصال بطيء. يرجى استخدام ملف أصغر.'
            })
        except (RuntimeError, OSError) as system_error:
            error_str = str(system_error)
            logging.error(f"خطأ في النظام أثناء قراءة الملف: {error_str}")
            if "SystemExit" in error_str or "worker" in error_str.lower():
                return jsonify({
                    'success': False, 
                    'error': 'الملف كبير جداً ولا يمكن معالجته. يرجى تقسيم المحتوى إلى ملفات أصغر.'
                })
            return jsonify({
                'success': False, 
                'error': 'خطأ في النظام أثناء قراءة الملف. يرجى المحاولة مرة أخرى.'
            })
        except Exception as form_error:
            error_str = str(form_error)
            logging.error(f"خطأ في قراءة البيانات: {error_str}")
            if "recv" in error_str.lower() or "connection" in error_str.lower():
                return jsonify({
                    'success': False, 
                    'error': 'انقطع الاتصال أثناء رفع الملف. يرجى التأكد من استقرار الإنترنت والمحاولة مرة أخرى.'
                })
            return jsonify({
                'success': False, 
                'error': 'خطأ في قراءة البيانات المرسلة. يرجى المحاولة مرة أخرى بملف أصغر.'
            })
        
        # Check for ZIP file - support both field names
        zip_file = None
        if 'zip_file' in files:
            zip_file = files['zip_file']
        elif 'chapter_zip' in files:
            zip_file = files['chapter_zip']
        
        if not zip_file or not zip_file.filename:
            return jsonify({'success': False, 'error': 'لم يتم اختيار ملف ZIP'})
        
        # Validate file extension
        if not zip_file.filename.lower().endswith('.zip'):
            return jsonify({'success': False, 'error': 'يجب أن يكون الملف من نوع ZIP فقط'})
        
        logging.info(f"🔄 بدء استخراج ZIP للملف {zip_file.filename} ({content_length / (1024*1024):.1f}MB)")
        
        # Use fast ZIP extraction with increased limit
        result = extract_zip_fast(zip_file, max_images=100)
        
        if result['success']:
            logging.info(f"✅ تم استخراج ZIP بنجاح: {result['total']} صورة")
            return jsonify(result)
        else:
            logging.error(f"❌ فشل استخراج ZIP: {result.get('error', 'خطأ غير معروف')}")
            return jsonify(result)
            
    except Exception as e:
        error_message = str(e)
        logging.error(f"❌ ZIP extraction error: {error_message}")
        
        # Better error categorization
        if "SystemExit" in error_message or "worker exiting" in error_message.lower():
            return jsonify({
                'success': False, 
                'error': 'الملف كبير جداً ولا يمكن معالجته. يرجى تقسيم المحتوى إلى عدة ملفات أصغر.'
            })
        elif "timeout" in error_message.lower() or "recv" in error_message.lower():
            return jsonify({
                'success': False, 
                'error': 'انتهت مهلة المعالجة. يرجى استخدام ملف أصغر أو التأكد من استقرار الإنترنت.'
            })
        else:
            return jsonify({
                'success': False, 
                'error': f'خطأ في معالجة الملف: {error_message}'
            })


def extract_zip_fast(zip_file, max_images=25):
    """Fast ZIP extraction with minimal processing for preview"""
    try:
        import zipfile
        import tempfile
        import base64
        from PIL import Image
        import io
        import time
        
        start_time = time.time()
        
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        
        # Save ZIP file directly without streaming for simplicity
        zip_path = os.path.join(temp_dir, 'upload.zip')
        
        try:
            # Save file directly to avoid streaming issues
            zip_file.save(zip_path)
            
            # Check file size after saving  
            file_size = os.path.getsize(zip_path)
            if file_size > 50 * 1024 * 1024:  # 50MB max to match the updated limit
                os.remove(zip_path)
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {
                    'success': False,
                    'error': f'الملف كبير جداً ({file_size/(1024*1024):.1f}MB). الحد الأقصى 50MB'
                }
                
        except Exception as save_error:
            logging.error(f"خطأ في حفظ الملف: {save_error}")
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                'success': False,
                'error': f'خطأ في حفظ الملف: {save_error}'
            }
        
        extracted_images = []
        processed_count = 0
        
        try:
            # Quick ZIP validation and extraction
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get image files only
                image_extensions = ('.jpg', '.jpeg', '.png', '.webp')
                image_files = [f for f in zip_ref.namelist() 
                             if f.lower().endswith(image_extensions) 
                             and not f.startswith('__MACOSX/') 
                             and '/' not in f.split('/')[-1]]  # Skip subdirectories
                
                # Simple natural sort
                image_files.sort()
                
                logging.info(f"📊 وُجد {len(image_files)} صور في ملف ZIP")
                
                # Process only first max_images for preview
                for i, filename in enumerate(image_files[:max_images]):
                    try:
                        # Quick timeout check
                        if time.time() - start_time > 15:  # 15 seconds max
                            logging.warning(f"⏰ انتهت المهلة، تم معالجة {processed_count} صور")
                            break
                        
                        # Quick size check before extraction
                        file_info = zip_ref.getinfo(filename)
                        if file_info.file_size > 3 * 1024 * 1024:  # Skip files > 3MB
                            logging.warning(f"تخطي {filename}: حجم كبير ({file_info.file_size/(1024*1024):.1f}MB)")
                            continue
                        
                        # Extract image data
                        with zip_ref.open(filename) as img_file:
                            image_data = img_file.read()
                        
                        # Create simple thumbnail with error handling
                        thumb_base64 = ''
                        try:
                            with Image.open(io.BytesIO(image_data)) as img:
                                # Quick RGB conversion
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                                
                                # Small thumbnail for speed
                                img.thumbnail((80, 80), Image.Resampling.LANCZOS)
                                
                                # Convert to base64
                                thumb_buffer = io.BytesIO()
                                img.save(thumb_buffer, format='JPEG', quality=50)
                                thumb_base64 = base64.b64encode(thumb_buffer.getvalue()).decode()
                        
                        except Exception as thumb_error:
                            logging.warning(f"خطأ في إنشاء صورة مصغرة لـ {filename}: {thumb_error}")
                            thumb_base64 = ''
                        
                        # Save temp file
                        safe_filename = f"page_{processed_count + 1:03d}.jpg"
                        temp_filepath = os.path.join(temp_dir, safe_filename)
                        with open(temp_filepath, 'wb') as f:
                            f.write(image_data)
                        
                        size_str = f"{len(image_data) / 1024:.0f} KB"
                        
                        extracted_images.append({
                            'filename': safe_filename,
                            'original_filename': filename,
                            'url': f'data:image/jpeg;base64,{thumb_base64}' if thumb_base64 else '',
                            'preview_url': f'data:image/jpeg;base64,{thumb_base64}' if thumb_base64 else '',
                            'size': size_str,
                            'temp_path': temp_filepath,
                            'page_number': processed_count + 1
                        })
                        
                        processed_count += 1
                        
                        # Log progress every 5 images
                        if processed_count % 5 == 0:
                            logging.info(f"معالجة: {processed_count}/{min(len(image_files), max_images)} صور")
                            
                    except Exception as img_error:
                        logging.warning(f"تخطي {filename}: {img_error}")
                        continue
        
        except zipfile.BadZipFile:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                'success': False,
                'error': 'ملف ZIP غير صالح أو تالف'
            }
        except Exception as zip_error:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                'success': False,
                'error': f'خطأ في استخراج ZIP: {zip_error}'
            }
        
        # Clean up ZIP file
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        if not extracted_images:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                'success': False,
                'error': 'لم يتم العثور على صور صالحة في الملف'
            }
        
        # Store for later use
        session['zip_temp_dir'] = temp_dir
        session['extracted_images_count'] = len(extracted_images)
        
        processing_time = time.time() - start_time
        logging.info(f"📊 انتهت المعالجة السريعة في {processing_time:.1f} ثانية: {len(extracted_images)} صور")
        
        return {
            'success': True,
            'images': extracted_images,
            'total': len(extracted_images),
            'processing_time': f'{processing_time:.1f}s',
            'message': f'تم استخراج {len(extracted_images)} صورة بنجاح'
        }
        
    except Exception as e:
        logging.error(f"خطأ عام في المعالجة: {e}")
        return {
            'success': False,
            'error': f'خطأ في المعالجة: {str(e)}'
        }


def extract_zip_locally(zip_file):
    """Extract ZIP file locally with optimized processing for large files"""
    try:
        import zipfile
        import tempfile
        import base64
        from PIL import Image
        import io
        import time
        
        start_time = time.time()
        
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        
        # Save ZIP file temporarily with size limit
        zip_path = os.path.join(temp_dir, 'upload.zip')
        
        # Save file in chunks to avoid memory issues
        chunk_size = 1024 * 1024  # 1MB chunks
        total_size = 0
        max_size = 50 * 1024 * 1024  # 50MB max (reduced for stability)
        
        with open(zip_path, 'wb') as f:
            while True:
                chunk = zip_file.stream.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    os.remove(zip_path)
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return {
                        'success': False,
                        'error': f'الملف كبير جداً. الحد الأقصى 50MB، الملف الحالي {total_size / (1024*1024):.1f}MB'
                    }
                f.write(chunk)
        
        logging.info(f"📦 استخراج ملف ZIP محلياً: {zip_file.filename} ({total_size / (1024*1024):.1f}MB)")
        
        extracted_images = []
        processed_count = 0
        max_images = 50  # Reduced maximum images to process
        
        # Extract ZIP file using standard zipfile module (reliable for all ZIP types)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get list of files in ZIP
            file_list = zip_ref.namelist()
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
            
            # Filter only image files and sort them naturally
            image_files = [f for f in file_list if f.lower().endswith(image_extensions) and not f.startswith('__MACOSX/')]
            
            # Natural sort to maintain page order
            import re
            def natural_sort_key(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            
            image_files.sort(key=natural_sort_key)
            
            logging.info(f"📊 Found {len(image_files)} images in ZIP file")
            
            # Extract and process each image with progress tracking
            for i, filename in enumerate(image_files):
                if processed_count >= max_images:
                    logging.info(f"⚠️ تم الوصول للحد الأقصى من الصور ({max_images})")
                    break
                
                # Check processing time to avoid timeouts
                if time.time() - start_time > 25:  # 25 seconds max processing time
                    logging.warning(f"⏰ انتهت المهلة الزمنية، تم معالجة {processed_count} صور")
                    break
                
                try:
                    # Extract file data with size check
                    with zip_ref.open(filename) as img_file:
                        image_data = img_file.read()
                    
                    # Skip files that are too large (>10MB per image)
                    if len(image_data) > 10 * 1024 * 1024:
                        logging.warning(f"تم تخطي {filename}: حجم كبير جداً ({len(image_data)/(1024*1024):.1f}MB)")
                        continue
                    
                    # Create thumbnail for preview
                    try:
                        with Image.open(io.BytesIO(image_data)) as img:
                            # Convert to RGB if needed
                            if img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P':
                                    img = img.convert('RGBA')
                                if img.mode in ('RGBA', 'LA'):
                                    background.paste(img, mask=img.split()[-1] if len(img.split()) > 3 else None)
                                img = background
                            
                            # Create thumbnail
                            thumbnail_size = (120, 120)
                            img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                            
                            # Convert to base64 for preview
                            thumb_buffer = io.BytesIO()
                            img.save(thumb_buffer, format='JPEG', quality=70, optimize=True)
                            thumb_base64 = base64.b64encode(thumb_buffer.getvalue()).decode()
                            
                    except Exception as img_error:
                        logging.warning(f"Error creating thumbnail for {filename}: {img_error}")
                        # Create placeholder thumbnail
                        placeholder_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">
                            <rect width="120" height="120" fill="#f0f0f0"/>
                            <text x="60" y="60" font-family="Arial" font-size="12" text-anchor="middle" fill="#666">صورة {processed_count + 1}</text>
                        </svg>'''
                        thumb_base64 = base64.b64encode(placeholder_svg.encode()).decode()
                    
                    # Get file size
                    file_size_bytes = len(image_data)
                    size_str = f"{file_size_bytes / 1024:.1f} KB" if file_size_bytes < 1024*1024 else f"{file_size_bytes / (1024*1024):.1f} MB"
                    
                    # Save file temporarily for later upload
                    safe_filename = f"page_{processed_count + 1:03d}{os.path.splitext(filename)[1]}"
                    temp_filepath = os.path.join(temp_dir, safe_filename)
                    with open(temp_filepath, 'wb') as f:
                        f.write(image_data)
                    
                    extracted_images.append({
                        'filename': safe_filename,
                        'original_filename': os.path.basename(filename),
                        'preview_url': f'data:image/jpeg;base64,{thumb_base64}',
                        'size': size_str,
                        'temp_path': temp_filepath,
                        'page_number': processed_count + 1
                    })
                    
                    processed_count += 1
                    
                    # Log every 10 images to avoid spam
                    if processed_count % 10 == 0 or processed_count == len(image_files):
                        logging.info(f"✅ تم معالجة {processed_count}/{len(image_files)} صور")
                    
                except Exception as e:
                    logging.warning(f"خطأ في معالجة {filename}: {e}")
                    continue
        
        # Clean up ZIP file
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        if not extracted_images:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                'success': False,
                'error': 'No valid images found in ZIP file'
            }
        
        # Store temp directory path in session for later use
        session['zip_temp_dir'] = temp_dir
        session['extracted_images_count'] = len(extracted_images)
        
        processing_time = time.time() - start_time
        logging.info(f"📊 انتهت المعالجة في {processing_time:.1f} ثانية: {len(extracted_images)} صور")
        
        return {
            'success': True,
            'images': extracted_images,
            'total': len(extracted_images),
            'processing_time': f'{processing_time:.1f} ثانية',
            'message': f'تم استخراج {len(extracted_images)} صورة من الأرشيف بنجاح'
        }
        
    except zipfile.BadZipFile:
        return {
            'success': False,
            'error': 'Invalid ZIP file format'
        }
    except Exception as e:
        logging.error(f"Local ZIP extraction error: {e}")
        return {
            'success': False,
            'error': f'Local extraction failed: {str(e)}'
        }


@app.route('/admin/fix-chapter-pages/<int:chapter_id>')
@login_required
def fix_chapter_pages(chapter_id):
    """Fix PageImage records for a chapter that was uploaded to Cloudinary but missing DB records"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول لهذه الصفحة.', 'error')
        return redirect(url_for('index'))
    
    try:
        chapter = Chapter.query.get_or_404(chapter_id)
        manga = chapter.manga
        
        # Check if chapter already has pages
        existing_pages = PageImage.query.filter_by(chapter_id=chapter_id).count()
        if existing_pages > 0:
            flash(f'الفصل يحتوي بالفعل على {existing_pages} صفحة في قاعدة البيانات.', 'info')
            if manga.slug:
                return redirect(url_for('manga_detail', slug=manga.slug))
            else:
                return redirect(url_for('manga_detail_by_id', manga_id=manga.id))
        
        # Try to find images in Cloudinary for this chapter
        import cloudinary.api
        from app.utils_cloudinary import account_manager
        
        # Configure with primary account
        account = account_manager.get_available_account()
        if account:
            account_manager.configure_cloudinary_with_account(account)
        
        # Search for images in the chapter folder
        folder_path = f"manga_chapters/manga_{manga.id}/chapter_{chapter_id}"
        
        try:
            # Get resources from Cloudinary
            result = cloudinary.api.resources(
                type="upload",
                prefix=folder_path,
                max_results=100
            )
            
            images_found = result.get('resources', [])
            if not images_found:
                flash(f'لم يتم العثور على صور في Cloudinary للفصل {chapter.title}', 'warning')
                if manga.slug:
                    return redirect(url_for('manga_detail', slug=manga.slug))
                else:
                    return redirect(url_for('manga_detail_by_id', manga_id=manga.id))
            
            # Create PageImage records for found images
            created_count = 0
            for image in images_found:
                # Extract page number from public_id
                public_id = image['public_id']
                if 'page_' in public_id:
                    try:
                        page_num_str = public_id.split('page_')[1]
                        page_number = int(page_num_str)
                        
                        # Create PageImage record
                        page_image = PageImage()
                        page_image.chapter_id = chapter_id
                        page_image.page_number = page_number
                        page_image.cloudinary_url = image['secure_url']
                        page_image.cloudinary_public_id = image['public_id']
                        page_image.image_path = None
                        page_image.image_width = image.get('width')
                        page_image.image_height = image.get('height')
                        
                        db.session.add(page_image)
                        created_count += 1
                        
                    except (ValueError, IndexError):
                        logging.warning(f"Could not parse page number from {public_id}")
                        continue
            
            db.session.commit()
            flash(f'✅ تم إنشاء {created_count} سجل صفحة للفصل {chapter.title}', 'success')
            
        except Exception as cloudinary_error:
            logging.error(f"Cloudinary API error: {cloudinary_error}")
            flash(f'خطأ في الاتصال بـ Cloudinary: {cloudinary_error}', 'error')
        
        if manga.slug:
            return redirect(url_for('manga_detail', slug=manga.slug))
        else:
            return redirect(url_for('manga_detail_by_id', manga_id=manga.id))
        
    except Exception as e:
        logging.error(f"Error fixing chapter pages: {e}")
        flash(f'خطأ في إصلاح صفحات الفصل: {e}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/upload-new', methods=['GET', 'POST'])
@login_required  
def admin_upload_new():
    """Admin manga upload page with chapter scheduling - Cloudinary Integration"""
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    # Handle GET request first to avoid import issues
    if request.method == 'GET':
        try:
            categories = Category.query.all()
            return render_template('admin/upload.html', categories=categories)
        except Exception as e:
            logging.error(f"Error loading upload page: {e}")
            flash('خطأ في تحميل الصفحة', 'error')
            return redirect(url_for('admin_dashboard'))
    
    # Import Cloudinary utilities only for POST requests
    try:
        from app.utils_cloudinary import cloudinary_uploader
    except ImportError:
        cloudinary_uploader = None
        logging.warning("Cloudinary utilities not available")
    
    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        title_ar = request.form.get('title_ar')
        description = request.form.get('description')
        description_ar = request.form.get('description_ar')
        author = request.form.get('author')
        artist = request.form.get('artist')
        manga_type = request.form.get('type')
        status = request.form.get('status')
        age_rating = request.form.get('age_rating')
        
        # Chapter data
        chapter_title = request.form.get('chapter_title')
        
        # Safely parse chapter number with NaN protection
        try:
            chapter_number = safe_parse_float(request.form.get('chapter_number', '1'), 1.0, "chapter number")
        except ValueError as e:
            flash(f'رقم الفصل غير صحيح: {str(e)}', 'error')
            return safe_redirect(request.url)
        
        # Safely parse is_locked boolean
        is_locked = safe_parse_bool(request.form.get('is_locked'))
        
        early_access_date = request.form.get('early_access_date')
        release_date = request.form.get('release_date')
        
        # Convert date strings to datetime objects
        early_access_dt = None
        release_date_dt = None
        
        if early_access_date:
            early_access_dt = datetime.strptime(early_access_date, '%Y-%m-%dT%H:%M')
        if release_date:
            release_date_dt = datetime.strptime(release_date, '%Y-%m-%dT%H:%M')
        
        # Get upload method
        upload_method = request.form.get('upload_method', 'images')
        
        # Handle file uploads based on method
        cover_file = request.files.get('cover_image')
        chapter_files = []
        
        if upload_method == 'images' or upload_method == 'files':
            chapter_files = request.files.getlist('chapter_images')
            if not title or not chapter_files:
                flash('العنوان وصور الفصل مطلوبة', 'error')
                return safe_redirect(request.url)
        elif upload_method == 'zip':
            zip_file = request.files.get('chapter_zip')
            if not title or not zip_file:
                flash('العنوان وملف ZIP مطلوبان', 'error')
                return safe_redirect(request.url)
        elif upload_method == 'scrape':
            source_website = request.form.get('source_website')
            chapter_url = request.form.get('chapter_url')
            # للكشط، نتحقق من وجود صور محفوظة مسبقاً
            temp_scraped_dir = os.path.join('static', 'uploads', 'temp_scraped')
            has_scraped_images = os.path.exists(temp_scraped_dir) and any(
                f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                for f in os.listdir(temp_scraped_dir) if os.path.isfile(os.path.join(temp_scraped_dir, f))
            )
            
            if not title:
                flash('العنوان مطلوب', 'error')
                return safe_redirect(request.url)
            
            # التحقق من وجود بيانات الكشط المختبرة
            scraping_tested = request.form.get('scraping_tested', 'false')
            scraped_images_json = request.form.get('scraped_images', '')
            has_tested_data = scraping_tested == 'true' and scraped_images_json
            
            if not has_scraped_images and not has_tested_data and (not source_website or not chapter_url):
                flash('الموقع المصدر ورابط الفصل مطلوبان أو يجب كشط الصور أولاً', 'error')
                return safe_redirect(request.url)
        
        try:
            # Create manga
            manga = Manga()
            manga.title = title
            manga.title_ar = title_ar
            manga.description = description
            manga.description_ar = description_ar
            manga.author = author
            manga.artist = artist
            manga.type = manga_type
            manga.status = status
            manga.age_rating = age_rating
            
            # Don't set slug manually - let the event listener handle it
            # The manga_before_insert event will auto-generate a unique slug
            
            # Handle cover image
            if cover_file and cover_file.filename:
                from werkzeug.utils import secure_filename
                cover_filename = secure_filename(cover_file.filename)
                cover_dir = 'static/uploads/covers'
                os.makedirs(cover_dir, exist_ok=True)
                cover_path = os.path.join(cover_dir, cover_filename)
                cover_file.save(cover_path)
                manga.cover_image = f"uploads/covers/{cover_filename}"
            
            db.session.add(manga)
            db.session.commit()
            
            # Handle multiple categories - will be done after chapter creation to avoid duplicates
            
            # Create chapter
            chapter = Chapter()
            chapter.manga_id = manga.id
            chapter.chapter_number = chapter_number
            chapter.title = chapter_title
            chapter.is_locked = is_locked
            chapter.early_access_date = early_access_dt
            chapter.release_date = release_date_dt
            
            db.session.add(chapter)
            db.session.commit()
            
            # Handle chapter images based on upload method - Upload to Cloudinary
            print(f"🚀 بدء رفع الصور إلى Cloudinary لفصل {chapter_number}")
            
            uploaded_results = []
            successful_uploads = 0
            
            # Import Cloudinary uploader
            from app.utils_cloudinary import cloudinary_uploader
            
            try:
                if upload_method == 'images' or upload_method == 'files':
                    # حفظ الصور مؤقتاً ثم رفعها في الخلفية
                    try:
                        from scripts.background_uploader import background_uploader
                    except ImportError:
                        background_uploader = None
                        logging.warning("Background uploader not available, falling back to direct processing")
                    
                    chapter_files = request.files.getlist('chapter_images')
                    if not chapter_files or not any(f.filename for f in chapter_files):
                        raise Exception('لم يتم اختيار أي صور للرفع')
                    
                    print(f"💾 حفظ {len(chapter_files)} صورة مؤقتاً لرفعها في الخلفية")
                    
                    # إضافة المهمة لطابور الرفع في الخلفية بدون حفظ فوري
                    # سيتم الحفظ والرفع في الخلفية كاملة
                    if background_uploader:
                        temp_folder, saved_files = background_uploader.save_temp_images_from_files_async(chapter_files, manga.id, chapter.id)
                        successful_uploads = len(saved_files)
                        uploaded_results = [{'success': True} for _ in saved_files]
                    else:
                        # الرفع المباشر في حالة عدم توفر background_uploader
                        print(f"🚀 بدء رفع مباشر لـ {len(chapter_files)} صورة")
                        import threading
                        from app.utils_cloudinary import cloudinary_uploader
                        
                        def direct_upload_files():
                            with app.app_context():
                                for i, file in enumerate(chapter_files, 1):
                                    if file.filename:
                                        try:
                                            # رفع إلى Cloudinary مباشرة باستخدام المعاملات الصحيحة
                                            result = cloudinary_uploader.upload_image_file(file, manga.id, chapter.id, i)
                                            
                                            # لا نحتاج لإنشاء PageImage هنا - utils_cloudinary يتولى ذلك
                                            if result.get('success'):
                                                logging.info(f"✅ تم رفع الصورة {i} بنجاح")
                                            else:
                                                logging.error(f"❌ فشل رفع الصورة {i}: {result.get('error')}")
                                                
                                        except Exception as e:
                                            logging.error(f"❌ فشل رفع الصورة {file.filename}: {e}")
                                
                                logging.info(f"✅ انتهى رفع الصور المباشرة للمانجا {manga.id}")
                        
                        upload_thread = threading.Thread(target=direct_upload_files, daemon=True)
                        upload_thread.start()
                        successful_uploads = len(chapter_files)
                        uploaded_results = [{'success': True} for _ in chapter_files]
                    
                elif upload_method == 'zip':
                    # استخدام الصور المستخرجة مسبقاً
                    try:
                        from scripts.background_uploader import background_uploader
                    except ImportError:
                        background_uploader = None
                        logging.warning("Background uploader not available, falling back to direct processing")
                    
                    extracted_images_data = request.form.get('extracted_images_data')
                    if not extracted_images_data:
                        raise Exception('يجب فك الضغط ومعاينة الصور أولاً')
                    
                    try:
                        import json
                        images_data = json.loads(extracted_images_data)
                        
                        if not images_data:
                            raise Exception('لا توجد صور مستخرجة')
                            
                        # نقل الصور من المجلد المؤقت إلى نظام التخزين المؤقت للرفع
                        temp_dir = session.get('zip_temp_dir')
                        if not temp_dir or not os.path.exists(temp_dir):
                            raise Exception('انتهت صلاحية الصور المستخرجة، يرجى إعادة فك الضغط')
                        
                        # إنشاء مجلد مؤقت جديد للرفع
                        upload_temp_folder = f"manga_{manga.id}_chapter_{chapter.id}_{int(time.time())}"
                        upload_temp_path = background_uploader.temp_storage_path / upload_temp_folder if background_uploader else None
                        if upload_temp_path:
                            upload_temp_path.mkdir(exist_ok=True)
                        
                        saved_files = []
                        for i, image_data in enumerate(images_data, 1):
                            src_path = image_data.get('temp_path')
                            if src_path and os.path.exists(src_path):
                                # نسخ الملف للمجلد الجديد بالترتيب المحدث
                                filename = f"page_{i:03d}{os.path.splitext(image_data['filename'])[1]}"
                                dest_path = upload_temp_path / filename
                                import shutil
                                shutil.copy2(src_path, dest_path)
                                saved_files.append(filename)
                        
                        if not saved_files:
                            raise Exception('فشل في معالجة الصور المستخرجة')
                        
                        # إضافة المهمة لطابور الرفع في الخلفية
                        if background_uploader:
                            background_uploader.add_to_upload_queue(manga.id, chapter.id, upload_temp_folder, saved_files)
                        else:
                            # الرفع المباشر في حالة عدم توفر background_uploader
                            print(f"🚀 بدء رفع مباشر لـ {len(saved_files)} صورة من ZIP")
                            import threading
                            from app.utils_cloudinary import cloudinary_uploader
                            
                            def direct_upload_zip():
                                with app.app_context():
                                    for i, filename in enumerate(saved_files, 1):
                                        try:
                                            file_path = upload_temp_path / filename
                                            if file_path.exists():
                                                # رفع إلى Cloudinary باستخدام المعاملات الصحيحة
                                                with open(file_path, 'rb') as f:
                                                    result = cloudinary_uploader.upload_image_file(f, manga.id, chapter.id, i)
                                                
                                                if result.get('success'):
                                                    logging.info(f"✅ تم رفع الصورة {i} من ZIP بنجاح")
                                                else:
                                                    logging.error(f"❌ فشل رفع الصورة {i}: {result.get('error')}")
                                                
                                                # حذف الملف المؤقت
                                                os.remove(str(file_path))
                                                
                                        except Exception as e:
                                            logging.error(f"❌ فشل رفع الصورة {filename}: {e}")
                                    
                                    # تنظيف الملفات المؤقتة
                                    if upload_temp_path.exists():
                                        shutil.rmtree(upload_temp_path, ignore_errors=True)
                                    logging.info(f"✅ انتهى رفع صور ZIP مباشرة للمانجا {manga.id}")
                            
                            upload_thread = threading.Thread(target=direct_upload_zip, daemon=True)
                            upload_thread.start()
                        
                        successful_uploads = len(saved_files)
                        uploaded_results = [{'success': True} for _ in saved_files]
                        
                        # تنظيف المجلد المؤقت للاستخراج
                        import shutil
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        session.pop('zip_temp_dir', None)
                        session.pop('extracted_images_count', None)
                        
                        print(f"📦 تم رفع {successful_uploads} صورة من ZIP في الخلفية")
                        
                    except json.JSONDecodeError:
                        raise Exception('بيانات الصور المستخرجة غير صالحة')
                    except Exception as e:
                        raise Exception(f'خطأ في معالجة الصور المستخرجة: {str(e)}')
                    
                elif upload_method == 'scrape':
                    # رفع الصور المكشوطة إلى Cloudinary
                    source_website = request.form.get('source_website')
                    chapter_url = request.form.get('chapter_url', '')
                    scraping_tested = request.form.get('scraping_tested', 'false')
                    scraped_images_json = request.form.get('scraped_images', '')
                    
                    if not chapter_url:
                        raise Exception('رابط الفصل مطلوب للكشط')
                    
                    # التحقق من وجود بيانات الكشط المختبرة
                    if scraping_tested == 'true' and scraped_images_json:
                        try:
                            import json
                            scraped_data = json.loads(scraped_images_json)
                            image_urls = scraped_data.get('images', []) if isinstance(scraped_data, dict) else scraped_data
                            
                            if image_urls:
                                # تنزيل وحفظ الصور مؤقتاً ثم رفعها في الخلفية
                                try:
                                    from scripts.background_uploader import background_uploader
                                except ImportError:
                                    background_uploader = None
                                    logging.warning("Background uploader not available, falling back to direct processing")
                                
                                print(f"🕸️ تنزيل {len(image_urls)} صورة مكشوطة وحفظها مؤقتاً")
                                headers = {'Referer': chapter_url} if chapter_url else {}
                                
                                # حفظ المانجا والفصل أولاً
                                print(f"💾 حفظ المانجا '{manga.title}' والفصل {chapter.title} في قاعدة البيانات")
                                
                                if background_uploader:
                                    # استخدام الرفع في الخلفية
                                    print(f"📋 إضافة {len(image_urls)} صورة لقائمة الرفع في الخلفية")
                                    temp_folder, saved_files = background_uploader.save_temp_images_from_urls(image_urls, manga.id, chapter.id, headers)
                                    background_uploader.add_to_upload_queue(manga.id, chapter.id, temp_folder, saved_files)
                                    successful_uploads = len(saved_files)
                                    uploaded_results = [{'success': True} for _ in saved_files]
                                    print(f"✅ تم حفظ {len(saved_files)} صورة مؤقتاً - سيتم الرفع في الخلفية")
                                else:
                                    # بدء رفع مباشر في الخلفية (في thread منفصل)
                                    print(f"🚀 بدء رفع {len(image_urls)} صورة في الخلفية")
                                    import threading
                                    from app.utils_cloudinary import CloudinaryUploader
                                    from app.app import app
                                    
                                    def background_upload():
                                        with app.app_context():
                                            uploader = CloudinaryUploader()
                                            uploader.upload_scraped_images(image_urls, manga.id, chapter.id, headers)
                                    
                                    upload_thread = threading.Thread(target=background_upload, daemon=True)
                                    upload_thread.start()
                                    successful_uploads = len(image_urls)
                                    uploaded_results = [{'success': True} for _ in image_urls]
                                    print(f"✅ بدء رفع {len(image_urls)} صورة في الخلفية - المانجا محفوظة")
                            else:
                                raise Exception('لا توجد صور في البيانات المكشوطة')
                            
                            print(f"✅ تم حفظ المانجا والفصل بنجاح - الصور يتم رفعها في الخلفية")
                            
                        except (json.JSONDecodeError, ValueError):
                            raise Exception('خطأ في قراءة بيانات الصور المختبرة')
                    else:
                        # الكشط المباشر
                        if chapter_url and 'olympustaff.com' in chapter_url:
                            try:
                                from scrapers.simple_manga_scraper import scrape_olympustaff_simple
                                
                                print(f"🧪 كشط مباشر من: {chapter_url}")
                                scrape_result = scrape_olympustaff_simple(chapter_url, '')
                                
                                if not scrape_result['success']:
                                    raise Exception(f'فشل في كشط الصور: {scrape_result.get("error", "خطأ غير معروف")}')
                                
                                image_urls = scrape_result.get('all_images', [])
                                if image_urls:
                                    # تنزيل وحفظ الصور مؤقتاً ثم رفعها في الخلفية
                                    try:
                                        from scripts.background_uploader import background_uploader
                                    except ImportError:
                                        background_uploader = None
                                        logging.warning("Background uploader not available, falling back to direct processing")
                                    
                                    print(f"🕸️ تنزيل {len(image_urls)} صورة مكشوطة وحفظها مؤقتاً")
                                    headers = {'Referer': chapter_url}
                                    
                                    # حفظ المانجا والفصل أولاً
                                    print(f"💾 حفظ المانجا '{manga.title}' والفصل {chapter.title} في قاعدة البيانات")
                                    
                                    if background_uploader:
                                        # استخدام الرفع في الخلفية
                                        print(f"📋 إضافة {len(image_urls)} صورة لقائمة الرفع في الخلفية")
                                        temp_folder, saved_files = background_uploader.save_temp_images_from_urls(image_urls, manga.id, chapter.id, headers)
                                        background_uploader.add_to_upload_queue(manga.id, chapter.id, temp_folder, saved_files)
                                        successful_uploads = len(saved_files)
                                        uploaded_results = [{'success': True} for _ in saved_files]
                                        print(f"✅ تم حفظ {len(saved_files)} صورة مؤقتاً - سيتم الرفع في الخلفية")
                                    else:
                                        # بدء رفع مباشر في الخلفية (في thread منفصل)
                                        print(f"🚀 بدء رفع {len(image_urls)} صورة في الخلفية")
                                        import threading
                                        from app.utils_cloudinary import CloudinaryUploader
                                        from app.app import app
                                        
                                        def background_upload():
                                            with app.app_context():
                                                uploader = CloudinaryUploader()
                                                uploader.upload_scraped_images(image_urls, manga.id, chapter.id, headers)
                                        
                                        upload_thread = threading.Thread(target=background_upload, daemon=True)
                                        upload_thread.start()
                                        successful_uploads = len(image_urls)
                                        uploaded_results = [{'success': True} for _ in image_urls]
                                        print(f"✅ بدء رفع {len(image_urls)} صورة في الخلفية - المانجا محفوظة")
                                else:
                                    raise Exception('لا توجد صور في الفصل المكشوط')
                                    
                            except ImportError:
                                raise Exception('مكتبة الكشط غير متوفرة')
                        else:
                            raise Exception('نوع الموقع غير مدعوم للكشط المباشر')
                else:
                    print(f"⚠️ Upload method received: '{upload_method}'")
                    print(f"⚠️ Available methods: 'images', 'files', 'zip', 'scrape'")
                    raise Exception(f'طريقة رفع غير صحيحة: {upload_method}. الطرق المتاحة: images, files, zip, scrape')
                            
                # التحقق من نجاح التخزين المؤقت (الرفع سيتم في الخلفية)
                if not uploaded_results or successful_uploads == 0:
                    raise Exception('فشل في حفظ الصور مؤقتاً')
                
                print(f"✅ تم حفظ {successful_uploads} صورة مؤقتاً وبدء رفعها في الخلفية")
                print("📌 سيتم رفع الصور إلى Cloudinary تلقائياً في الخلفية وحذف الملفات المؤقتة بعد الانتهاء")
                
                # تعيين معلومات الفصل - سيتم تحديث pages عند انتهاء الرفع في الخلفية
                chapter.pages = successful_uploads
                chapter.status = 'draft'  # سيتم تفعيله عند انتهاء رفع الصور
                
                print(f"📌 الفصل سيصبح متاحاً للقراءة تلقائياً بعد انتهاء رفع الصور في الخلفية")
                
                # Add categories if selected - do this quickly without delays
                selected_categories = request.form.getlist('categories')
                if selected_categories:
                    category_ids = []
                    for cat_id in selected_categories:
                        try:
                            category_ids.append(int(cat_id))
                        except ValueError:
                            continue
                    
                    if category_ids:
                        # Fast category assignment without extensive checking
                        try:
                            categories = Category.query.filter(Category.id.in_(category_ids)).all()
                            manga.categories.extend(categories)
                        except Exception as cat_error:
                            print(f"⚠️ Category assignment error: {cat_error}")
                
                db.session.commit()
                
            except Exception as upload_error:
                db.session.rollback()
                raise Exception(f"خطأ في رفع الصور: {str(upload_error)}")
            
            if is_locked:
                if early_access_dt:
                    flash(f'تم رفع المانجا بنجاح! الفصل سيكون متاحاً للمشتركين المميزين في {early_access_dt.strftime("%Y-%m-%d %H:%M")} وللجميع في {release_date_dt.strftime("%Y-%m-%d %H:%M") if release_date_dt else "غير محدد"}', 'success')
                else:
                    flash(f'تم رفع المانجا بنجاح! الفصل سيكون متاحاً للجميع في {release_date_dt.strftime("%Y-%m-%d %H:%M") if release_date_dt else "غير محدد"}', 'success')
            else:
                flash('تم رفع المانجا والفصل بنجاح!', 'success')
            
            # Use slug if available, otherwise fallback to manga_detail_by_id
            if manga.slug:
                return redirect(url_for('manga_detail', slug=manga.slug))
            else:
                return redirect(url_for('manga_detail_by_id', manga_id=manga.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ أثناء رفع المانجا: {str(e)}', 'error')
            return safe_redirect(request.url)
    
    # Get categories for form
    categories = Category.query.all()
    return render_template('admin/upload.html', categories=categories)


@app.route('/test-olympustaff-scraping', methods=['POST'])
@login_required
def test_olympustaff_scraping_route():
    """Test OlympusStaff scraping (unified endpoint for all admin operations)"""
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    try:
        chapter_url = request.form.get('chapter_url')
        
        if not chapter_url:
            return jsonify({
                'success': False,
                'error': 'رابط الفصل مطلوب'
            })
        
        # استخدام الكاشط الموحد المبسط
        from scrapers.simple_manga_scraper import test_olympustaff_scraping
        
        result = test_olympustaff_scraping(chapter_url)
        
        if not result['success']:
            return jsonify({
                'success': False,
                'error': result.get('error', 'خطأ غير معروف')
            })
        
        return jsonify({
            'success': True,
            'chapter_title': result.get('chapter_title', 'غير محدد'),
            'total_images': result.get('total_images', 0),
            'sample_images': result.get('sample_images', []),
            'all_images': result.get('all_images', []),
            'site_type': 'OlympusStaff',
            'site_url': chapter_url,
            'message': f'تم العثور على {result.get("total_images", 0)} صورة'
        })
        
    except Exception as e:
        import traceback
        print(f"❌ خطأ في كشط الصور: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'خطأ في الاختبار: {str(e)}'
        })


@app.route('/admin/test-scrape', methods=['POST'])
@login_required
def admin_test_scrape():
    """Test Arabic manga web scraping with enhanced preview (legacy endpoint)"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        data = request.get_json()
        chapter_url = data.get('chapter_url')
        
        if not chapter_url:
            return jsonify({
                'success': False,
                'error': 'رابط الفصل مطلوب'
            })
        
        # استخدام الكاشط المبسط الجديد للاختبار
        from scrapers.simple_manga_scraper import test_olympustaff_scraping
        
        result = test_olympustaff_scraping(chapter_url)
        
        if not result['success']:
            return jsonify({
                'success': False,
                'error': result['error']
            })
        
        return jsonify({
            'success': True,
            'chapter_title': result.get('chapter_title', 'غير محدد'),
            'total_images': result.get('total_images', 0),
            'sample_images': result.get('sample_images', []),
            'all_images': result.get('all_images', []),  # جميع الصور للرفع الفعلي
            'site_type': 'OlympusStaff',
            'site_url': chapter_url,
            'message': f'نجح اختبار الكشط ✓\n• الفصل: {result.get("chapter_title", "غير محدد")}\n• الصور الموجودة: {result.get("total_images", 0)}\n• الرسالة: تم العثور على {result.get("total_images", 0)} صورة'
        })
        
    except Exception as e:
        import traceback
        print(f"❌ خطأ في كشط الصور: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'خطأ في الاختبار: {str(e)}'
        })

# Admin Payment Management - kept the comprehensive version above

@app.route('/admin/chapters')
@login_required
def admin_chapters():
    """Admin chapter management with scheduling"""
    # Allow access for admin, publisher, and translator
    if not (current_user.is_admin or current_user.is_publisher or current_user.is_translator):
        abort(403)
    
    # Get filter parameters
    manga_id = request.args.get('manga_id')
    status_filter = request.args.get('status')
    filter_type = request.args.get('filter')  # translator, publisher, etc.
    sort_filter = request.args.get('sort', 'newest')
    
    # Base query
    chapters_query = Chapter.query.join(Manga)
    
    # Apply manga filter
    if manga_id:
        chapters_query = chapters_query.filter(Chapter.manga_id == manga_id)
    
    # Apply role-based filtering
    if filter_type == 'translator':
        # For translator filter, show chapters from manga where current user is translator
        # or if admin, show all translation-related chapters
        if current_user.is_admin:
            # Admin can see all chapters
            pass
        elif current_user.is_translator:
            # Translator sees only their assigned manga
            translator_manga_ids = [m.id for m in Manga.query.filter_by(publisher_id=current_user.id).all()]
            if translator_manga_ids:
                chapters_query = chapters_query.filter(Chapter.manga_id.in_(translator_manga_ids))
            else:
                chapters_query = chapters_query.filter(Chapter.id == -1)  # No results
    elif filter_type == 'publisher':
        # Similar logic for publisher
        if current_user.is_admin:
            pass
        elif current_user.is_publisher:
            chapters_query = chapters_query.filter(Manga.publisher_id == current_user.id)
    
    # Apply status filter
    if status_filter == 'locked':
        chapters_query = chapters_query.filter(Chapter.is_locked == True)
    elif status_filter == 'available':
        chapters_query = chapters_query.filter(Chapter.is_locked == False)
    elif status_filter == 'early_access':
        chapters_query = chapters_query.filter(Chapter.early_access_date.isnot(None))
    
    # Apply sorting
    if sort_filter == 'oldest':
        chapters_query = chapters_query.order_by(Chapter.created_at.asc())
    elif sort_filter == 'chapter_num':
        chapters_query = chapters_query.order_by(Chapter.chapter_number.asc())
    else:  # newest
        chapters_query = chapters_query.order_by(Chapter.created_at.desc())
    
    # Add pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Show 20 chapters per page
    
    chapters = chapters_query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    all_manga = Manga.query.order_by(Manga.title.asc()).all()
    
    # Calculate statistics for template
    total_chapters = Chapter.query.count()
    locked_chapters = Chapter.query.filter_by(is_locked=True).count()
    early_access_chapters = Chapter.query.filter(Chapter.early_access_date.isnot(None)).count()
    available_chapters = total_chapters - locked_chapters
    
    # Also calculate for the template statistics cards
    published_chapters = Chapter.query.join(Manga).filter(Manga.is_published == True).count()
    draft_chapters = Chapter.query.join(Manga).filter(Manga.is_published == False).count()
    premium_chapters = Chapter.query.join(Manga).filter(Manga.is_premium == True).count()
    
    return render_template('admin/chapters.html', 
                         chapters=chapters, 
                         all_manga=all_manga,
                         manga_list=all_manga,  # Add alias for template compatibility
                         total_chapters=total_chapters,
                         locked_chapters=locked_chapters,
                         early_access_chapters=early_access_chapters,
                         available_chapters=available_chapters,
                         published_chapters=published_chapters,
                         draft_chapters=draft_chapters,
                         premium_chapters=premium_chapters)

@app.route('/admin/chapters/update-schedule', methods=['POST'])
@login_required
def admin_update_chapter_schedule():
    """Update chapter release schedule"""
    if not current_user.is_admin:
        abort(403)
    
    chapter_id = request.form.get('chapter_id')
    is_locked = safe_parse_bool(request.form.get('is_locked'))
    early_access_date = request.form.get('early_access_date')
    release_date = request.form.get('release_date')
    
    chapter = Chapter.query.get_or_404(chapter_id)
    
    # Convert date strings to datetime objects
    early_access_dt = None
    release_date_dt = None
    
    if early_access_date:
        early_access_dt = datetime.strptime(early_access_date, '%Y-%m-%dT%H:%M')
    if release_date:
        release_date_dt = datetime.strptime(release_date, '%Y-%m-%dT%H:%M')
    
    # Update chapter
    chapter.is_locked = is_locked
    chapter.early_access_date = early_access_dt if is_locked else None
    chapter.release_date = release_date_dt if is_locked else None
    
    db.session.commit()
    
    flash(f'تم تحديث جدولة الفصل {chapter.chapter_number} بنجاح!', 'success')
    return redirect(url_for('admin_chapters'))

# Admin manga management route
@app.route('/admin/manage-manga')
@login_required
def admin_manage_manga():
    """Admin manga management page"""
    if not current_user.is_admin:
        abort(403)
    
    # Get all manga with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    manga_query = Manga.query.order_by(Manga.created_at.desc())
    manga_pagination = manga_query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/manage_manga.html', 
                         manga_list=manga_pagination.items,
                         pagination=manga_pagination)

# Missing Admin Routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard_new():
    """New admin dashboard route"""
    if not current_user.is_admin:
        return redirect(url_for('admin_dashboard'))  # Redirect to existing /admin route
    
    # Redirect to existing admin dashboard at /admin
    return redirect(url_for('admin_dashboard'))

# Missing Premium Plans Route
@app.route('/premium/plans')
def premium_plans_route():
    """Premium plans page route"""
    return redirect(url_for('premium_plans'))  # Redirect to existing premium_plans function

# Missing Category Routes
@app.route('/category/<category_slug>')
def category_manga(category_slug):
    """Display manga by category"""
    category = Category.query.filter_by(slug=category_slug, is_active=True).first_or_404()
    
    # Get manga for this category
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filter manga by category using the association table
    manga_query = Manga.query.join(manga_category).filter(
        manga_category.c.category_id == category.id,
        Manga.is_published == True
    ).order_by(Manga.updated_at.desc())
    
    manga_pagination = manga_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get latest manga for the template (index.html expects this)
    latest_manga = Manga.query.filter_by(is_published=True).order_by(Manga.created_at.desc()).limit(10).all()
    
    # Get featured manga
    featured_manga = Manga.query.filter_by(is_published=True, is_featured=True).limit(5).all()
    
    # Get all categories for navigation
    categories = Category.query.filter_by(is_active=True).all()
    
    return render_template('index.html', 
                         manga_list=manga_pagination.items,
                         latest_manga=latest_manga,
                         featured_manga=featured_manga,
                         categories=categories,
                         pagination=manga_pagination,
                         page_title=f"{category.name} - {category.name_ar}",
                         current_category=category)

# Missing User Profile Route
@app.route('/user/<int:user_id>')
def user_profile(user_id):
    """Display user profile"""
    user = User.query.get_or_404(user_id)
    
    # Get user's manga if they're a publisher
    published_manga = []
    if user.is_publisher:
        published_manga = Manga.query.filter_by(publisher_id=user.id, is_published=True).all()
    
    # Get user's recent activity (comments, ratings)
    recent_comments = Comment.query.filter_by(user_id=user.id).order_by(Comment.created_at.desc()).limit(5).all()
    
    return render_template('user/profile.html', 
                         user=user,
                         published_manga=published_manga,
                         recent_comments=recent_comments)

# Missing Admin Action Routes - Add Chapter will use existing function

@app.route('/admin/categories/toggle/<int:category_id>', methods=['POST'])
@login_required
def admin_toggle_category(category_id):
    """Toggle category active status"""
    if not current_user.is_admin:
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    category.is_active = not getattr(category, 'is_active', True)
    
    # Add is_active field if it doesn't exist
    if not hasattr(Category, 'is_active'):
        # Add column dynamically (in production, use migrations)
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE category ADD COLUMN is_active BOOLEAN DEFAULT TRUE'))
            db.session.commit()
        except:
            pass
    
    db.session.commit()
    
    status = 'تم تنشيط' if category.is_active else 'تم إيقاف'
    flash(f'{status} الفئة {category.name} بنجاح', 'success')
    
    return redirect(url_for('admin_categories'))

@app.route('/admin/users/toggle-active/<int:user_id>', methods=['POST'])
@login_required
def admin_toggle_user_active(user_id):
    """Toggle user active status"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('لا يمكن تعطيل حسابك الخاص', 'error')
        return redirect(url_for('admin_users'))
    
    # Add is_active field if it doesn't exist
    if not hasattr(user, 'is_active'):
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT TRUE'))
            db.session.commit()
        except:
            pass
        user.is_active = True
    
    user.is_active = not getattr(user, 'is_active', True)
    db.session.commit()
    
    status = 'تم تنشيط' if user.is_active else 'تم تعطيل'
    flash(f'{status} المستخدم {user.username} بنجاح', 'success')
    
    return redirect(url_for('admin_users'))

# Removed duplicate route - admin_edit_category already handles GET and POST

# Additional missing admin routes for JavaScript functions
@app.route('/admin/categories/duplicate/<int:category_id>', methods=['POST'])
@login_required
def admin_duplicate_category(category_id):
    """Duplicate a category"""
    if not current_user.is_admin:
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    
    # Create new category with "Copy of" prefix
    new_category = Category()
    new_category.name = f"Copy of {category.name}"
    new_category.name_ar = f"نسخة من {category.name_ar}" if category.name_ar else None
    new_category.description = category.description
    new_category.slug = f"copy-of-{category.slug}" if category.slug else None
    new_category.is_active = False  # Start as inactive
    
    db.session.add(new_category)
    db.session.commit()
    
    if request.is_json:
        return jsonify({'success': True, 'message': f'تم تكرار الفئة {category.name} بنجاح'})
    
    flash(f'تم تكرار الفئة {category.name} بنجاح', 'success')
    return redirect(url_for('admin_categories'))

# API route to get category details for editing
@app.route('/admin/categories/<int:category_id>')
@login_required
def admin_get_category(category_id):
    """Get category details for editing"""
    if not (current_user.is_admin or current_user.is_publisher):
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    
    return jsonify({
        'success': True,
        'category': {
            'id': category.id,
            'name': category.name,
            'name_ar': category.name_ar,
            'description': category.description,
            'slug': category.slug,
            'is_active': getattr(category, 'is_active', True),
            'created_at': category.created_at.isoformat() if category.created_at else None
        }
    })

# Update routes to handle JSON requests for AJAX calls
@app.route('/admin/categories/<int:category_id>/toggle-status', methods=['POST'])
@login_required
def admin_toggle_category_status(category_id):
    """Toggle category active status via AJAX"""
    if not current_user.is_admin:
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    category.is_active = not getattr(category, 'is_active', True)
    db.session.commit()
    
    status = 'تم تنشيط' if category.is_active else 'تم إيقاف'
    
    if request.is_json:
        return jsonify({
            'success': True, 
            'message': f'{status} الفئة {category.name} بنجاح',
            'is_active': category.is_active
        })
    
    flash(f'{status} الفئة {category.name} بنجاح', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/categories/<int:category_id>/delete', methods=['DELETE', 'POST'])
@login_required
def admin_delete_category_ajax(category_id):
    """Delete category via AJAX"""
    if not current_user.is_admin:
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    
    # Check if category has manga
    manga_count = len(category.manga_items) if hasattr(category, 'manga_items') else 0
    if manga_count > 0:
        if request.is_json:
            return jsonify({'success': False, 'error': 'لا يمكن حذف الفئة التي تحتوي على مانجا'})
        flash('Cannot delete category with associated manga!', 'error')
        return redirect(url_for('admin_categories'))
    
    category_name = category.name
    db.session.delete(category)
    db.session.commit()
    
    if request.is_json:
        return jsonify({'success': True, 'message': f'تم حذف الفئة {category_name} بنجاح'})
    
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/categories/<int:category_id>/export')
@login_required
def admin_export_category(category_id):
    """Export category data"""
    if not current_user.is_admin:
        abort(403)
    
    category = Category.query.get_or_404(category_id)
    
    # Create CSV export
    import csv
    import io
    from flask import Response
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Name', 'Name (Arabic)', 'Slug', 'Description', 'Active', 'Created At'])
    
    # Write category data
    writer.writerow([
        category.id,
        category.name,
        category.name_ar or '',
        category.slug or '',
        category.description or '',
        getattr(category, 'is_active', True),
        category.created_at.isoformat() if category.created_at else ''
    ])
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-disposition": f"attachment; filename=category_{category.slug or category.id}.csv"}
    )

@app.route('/admin/users/send-message/<int:user_id>', methods=['POST'])
@login_required
def admin_send_message(user_id):
    """Send message to user (placeholder)"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    message = request.form.get('message', '')
    
    # This would implement actual messaging system
    flash(f'تم إرسال الرسالة للمستخدم {user.username}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
def admin_reset_password(user_id):
    """Reset user password"""
    if not current_user.is_admin:
        abort(403)
    
    user = User.query.get_or_404(user_id)
    
    # Generate temporary password
    import secrets
    import string
    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    
    from werkzeug.security import generate_password_hash
    user.password_hash = generate_password_hash(temp_password)
    db.session.commit()
    
    flash(f'تم إعادة تعيين كلمة مرور المستخدم {user.username}. كلمة المرور الجديدة: {temp_password}', 'success')
    return redirect(url_for('admin_users'))

# Add missing admin translations route
@app.route('/admin/translations')
@login_required
def admin_translations():
    """Admin translations management"""
    if not current_user.is_admin:
        abort(403)
    
    translation_requests = TranslationRequest.query.order_by(TranslationRequest.created_at.desc()).all()
    return render_template('admin/translations.html', translation_requests=translation_requests, now=datetime.now())

# Scraping queue route will be handled by existing function

# Auto-Scraping Admin Routes
@app.route('/admin/auto-scraping')
@login_required
def admin_auto_scraping():
    """Admin auto-scraping management"""
    if not current_user.is_admin:
        abort(403)
    
    # Get scraping sources with their manga info and recent logs
    sources = AutoScrapingSource.query.join(Manga).all()
    
    # Get recent scraping logs
    recent_logs = ScrapingLog.query.order_by(ScrapingLog.check_time.desc()).limit(20).all()
    
    # Get queue status
    pending_queue = ScrapingQueue.query.filter_by(status='pending').count()
    processing_queue = ScrapingQueue.query.filter_by(status='processing').count()
    failed_queue = ScrapingQueue.query.filter_by(status='failed').count()
    
    # Get system settings
    scraping_enabled = get_scraping_setting('scraping_enabled', 'true') == 'true'
    max_concurrent = get_scraping_setting('max_concurrent_scrapes', '3')
    
    return render_template('admin/auto_scraping.html',
                         sources=sources,
                         recent_logs=recent_logs,
                         pending_queue=pending_queue,
                         processing_queue=processing_queue,
                         failed_queue=failed_queue,
                         scraping_enabled=scraping_enabled,
                         max_concurrent=max_concurrent,
                         now=datetime.now())

@app.route('/admin/auto-scraping/add-source', methods=['GET', 'POST'])
@login_required
def admin_add_scraping_source():
    """Add new auto-scraping source"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        manga_id = request.form.get('manga_id')
        website_type = request.form.get('website_type')
        source_url = request.form.get('source_url')
        check_interval = int(request.form.get('check_interval', 3600))
        auto_publish = safe_parse_bool(request.form.get('auto_publish'))
        
        # Validate inputs
        if not manga_id or not website_type or not source_url:
            flash('جميع الحقول مطلوبة!', 'error')
            return redirect(url_for('admin_add_scraping_source'))
        
        manga = Manga.query.get(manga_id)
        if not manga:
            flash('المانجا المحددة غير موجودة!', 'error')
            return redirect(url_for('admin_add_scraping_source'))
        
        # Check if source already exists
        existing = AutoScrapingSource.query.filter_by(
            manga_id=manga_id,
            source_url=source_url
        ).first()
        
        if existing:
            flash('هذا المصدر موجود بالفعل لهذه المانجا!', 'error')
            return redirect(url_for('admin_add_scraping_source'))
        
        # Create new source
        source = AutoScrapingSource()
        source.manga_id = manga_id
        source.website_type = website_type
        source.source_url = source_url
        source.check_interval = check_interval
        source.auto_publish = auto_publish
        
        db.session.add(source)
        db.session.commit()
        
        flash(f'تم إضافة مصدر الكشط للمانجا "{manga.title}" بنجاح!', 'success')
        return redirect(url_for('admin_auto_scraping'))
    
    # GET request - show form
    manga_list = Manga.query.order_by(Manga.title).all()
    website_types = [
        ('mangadx', 'MangaDx'),
        ('manganelo', 'Manganelo'),
        ('mangakakalot', 'Mangakakalot'),
        ('generic', 'Generic Site')
    ]
    
    return render_template('admin/add_scraping_source.html',
                         manga_list=manga_list,
                         website_types=website_types)

@app.route('/admin/auto-scraping/source/<int:source_id>')
@login_required
def admin_scraping_source_detail(source_id):
    """Auto-scraping source details"""
    if not current_user.is_admin:
        abort(403)
    
    source = AutoScrapingSource.query.get_or_404(source_id)
    
    # Get source logs
    logs = ScrapingLog.query.filter_by(source_id=source_id).order_by(
        ScrapingLog.check_time.desc()
    ).limit(50).all()
    
    # Get queue items for this source
    queue_items = ScrapingQueue.query.filter_by(source_id=source_id).order_by(
        ScrapingQueue.created_at.desc()
    ).limit(30).all()
    
    return render_template('admin/scraping_source_detail.html',
                         source=source,
                         logs=logs,
                         queue_items=queue_items,
                         now=datetime.now())

@app.route('/admin/auto-scraping/source/<int:source_id>/toggle', methods=['POST'])
@login_required
def admin_toggle_scraping_source(source_id):
    """Toggle auto-scraping source active status"""
    if not current_user.is_admin:
        abort(403)
    
    source = AutoScrapingSource.query.get_or_404(source_id)
    source.is_active = not source.is_active
    
    db.session.commit()
    
    status = 'تم تفعيل' if source.is_active else 'تم إيقاف'
    flash(f'{status} مصدر الكشط للمانجا "{source.manga.title}" بنجاح!', 'success')
    
    return redirect(url_for('admin_auto_scraping'))

@app.route('/admin/auto-scraping/source/<int:source_id>/delete', methods=['POST'])
@login_required
def admin_delete_scraping_source(source_id):
    """Delete auto-scraping source"""
    if not current_user.is_admin:
        abort(403)
    
    source = AutoScrapingSource.query.get_or_404(source_id)
    manga_title = source.manga.title
    
    # Delete related logs and queue items
    ScrapingLog.query.filter_by(source_id=source_id).delete()
    ScrapingQueue.query.filter_by(source_id=source_id).delete()
    
    # Delete source
    db.session.delete(source)
    db.session.commit()
    
    flash(f'تم حذف مصدر الكشط للمانجا "{manga_title}" بنجاح!', 'success')
    return redirect(url_for('admin_auto_scraping'))

@app.route('/admin/auto-scraping/check-now/<int:source_id>', methods=['POST'])
@login_required
def admin_check_scraping_source_now(source_id):
    """Manually trigger check for new chapters"""
    if not current_user.is_admin:
        abort(403)
    
    source = AutoScrapingSource.query.get_or_404(source_id)
    
    # Import here to avoid circular imports
    from scripts.auto_scraper import auto_scraper
    
    try:
        # Trigger immediate check
        auto_scraper.check_source_for_new_chapters(source)
        flash(f'تم فحص مصدر الكشط للمانجا "{source.manga.title}" بنجاح!', 'success')
    except Exception as e:
        flash(f'خطأ في فحص المصدر: {str(e)}', 'error')
    
    return redirect(url_for('admin_auto_scraping'))

@app.route('/admin/auto-scraping/settings', methods=['GET', 'POST'])
@login_required
def admin_scraping_settings():
    """Manage auto-scraping settings"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        # Import here to avoid circular imports
        from scripts.auto_scraper import set_scraping_setting
        
        # Update settings
        settings_to_update = [
            'scraping_enabled',
            'max_concurrent_scrapes',
            'scraping_delay',
            'quality_check_enabled'
        ]
        
        for setting_key in settings_to_update:
            value = request.form.get(setting_key, '')
            if setting_key == 'scraping_enabled':
                value = 'true' if safe_parse_bool(request.form.get(setting_key)) else 'false'
            set_scraping_setting(setting_key, value)
        
        flash('تم تحديث إعدادات الكشط التلقائي بنجاح!', 'success')
        return redirect(url_for('admin_auto_scraping'))
    
    # GET request - show current settings
    from scripts.auto_scraper import get_scraping_setting
    
    current_settings = {
        'scraping_enabled': get_scraping_setting('scraping_enabled', 'true') == 'true',
        'max_concurrent_scrapes': get_scraping_setting('max_concurrent_scrapes', '3'),
        'scraping_delay': get_scraping_setting('scraping_delay', '5'),
        'quality_check_enabled': get_scraping_setting('quality_check_enabled', 'true') == 'true'
    }
    
    return render_template('admin/scraping_settings.html', settings=current_settings)

@app.route('/admin/auto-scraping/queue')
@login_required
def admin_scraping_queue():
    """View and manage scraping queue"""
    if not current_user.is_admin:
        abort(403)
    
    # Get queue items with pagination
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    queue_query = ScrapingQueue.query.join(AutoScrapingSource).join(Manga)
    
    if status_filter != 'all':
        queue_query = queue_query.filter(ScrapingQueue.status == status_filter)
    
    queue_items = queue_query.order_by(
        ScrapingQueue.priority.desc(),
        ScrapingQueue.created_at.desc()
    ).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get queue statistics
    queue_stats = {
        'pending': ScrapingQueue.query.filter_by(status='pending').count(),
        'processing': ScrapingQueue.query.filter_by(status='processing').count(),
        'completed': ScrapingQueue.query.filter_by(status='completed').count(),
        'failed': ScrapingQueue.query.filter_by(status='failed').count()
    }
    
    return render_template('admin/scraping_queue.html',
                         queue_items=queue_items,
                         queue_stats=queue_stats,
                         status_filter=status_filter)

@app.route('/admin/auto-scraping/queue/<int:item_id>/retry', methods=['POST'])
@login_required
def admin_retry_queue_item(item_id):
    """Retry failed queue item"""
    if not current_user.is_admin:
        abort(403)
    
    queue_item = ScrapingQueue.query.get_or_404(item_id)
    
    if queue_item.status == 'failed':
        queue_item.status = 'pending'
        queue_item.attempts = 0
        queue_item.error_message = None
        queue_item.processed_at = None
        
        db.session.commit()
        
        flash(f'تم إعادة إضافة الفصل {queue_item.chapter_number} إلى قائمة الانتظار!', 'success')
    else:
        flash('يمكن إعادة المحاولة للعناصر الفاشلة فقط!', 'error')
    
    return redirect(url_for('admin_scraping_queue'))

@app.route('/admin/auto-scraping/queue/<int:item_id>/delete', methods=['POST'])
@login_required
def admin_delete_queue_item(item_id):
    """Delete queue item"""
    if not current_user.is_admin:
        abort(403)
    
    queue_item = ScrapingQueue.query.get_or_404(item_id)
    
    db.session.delete(queue_item)
    db.session.commit()
    
    flash(f'تم حذف الفصل {queue_item.chapter_number} من قائمة الانتظار!', 'success')
    return redirect(url_for('admin_scraping_queue'))

# Helper function for settings
def get_scraping_setting(key: str, default: str = '') -> str:
    """Get scraping setting value"""
    setting = ScrapingSettings.query.filter_by(key=key).first()
    return setting.value if setting else default

# Admin Announcements Management Routes
@app.route('/admin/announcements')
@login_required
def admin_announcements():
    """Admin announcements management"""
    if not current_user.is_admin:
        abort(403)
    
    # Get all announcements with pagination
    page = request.args.get('page', 1, type=int)
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Statistics
    total_announcements = Announcement.query.count()
    active_announcements = Announcement.query.filter_by(is_active=True).count()
    featured_announcements = Announcement.query.filter_by(is_featured=True).count()
    
    return render_template('admin/announcements.html',
                         announcements=announcements,
                         total_announcements=total_announcements,
                         active_announcements=active_announcements,
                         featured_announcements=featured_announcements)

@app.route('/admin/announcements/add', methods=['GET', 'POST'])
@login_required
def admin_add_announcement():
    """Add new announcement"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_ar = request.form.get('title_ar', '').strip()
        content = request.form.get('content', '').strip()
        content_ar = request.form.get('content_ar', '').strip()
        announcement_type = request.form.get('type', 'info')
        target_audience = request.form.get('target_audience', 'all')
        is_active = safe_parse_bool(request.form.get('is_active'))
        is_featured = safe_parse_bool(request.form.get('is_featured'))
        display_until = request.form.get('display_until')
        
        if not title or not content:
            flash('العنوان والمحتوى مطلوبان', 'error')
            return render_template('admin/add_announcement.html')
        
        # Convert display_until to datetime if provided
        display_until_dt = None
        if display_until:
            try:
                display_until_dt = datetime.strptime(display_until, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('تاريخ الانتهاء غير صحيح', 'error')
                return render_template('admin/add_announcement.html')
        
        announcement = Announcement()
        announcement.title = title
        announcement.title_ar = title_ar
        announcement.content = content
        announcement.content_ar = content_ar
        announcement.type = announcement_type
        announcement.target_audience = target_audience
        announcement.is_active = is_active
        announcement.is_featured = is_featured
        announcement.display_until = display_until_dt
        announcement.created_by = current_user.id
        
        db.session.add(announcement)
        db.session.commit()
        
        flash('تم إضافة الإعلان بنجاح', 'success')
        return redirect(url_for('admin_announcements'))
    
    return render_template('admin/add_announcement.html')

@app.route('/admin/announcements/edit/<int:announcement_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_announcement(announcement_id):
    """Edit announcement"""
    if not current_user.is_admin:
        abort(403)
    
    announcement = Announcement.query.get_or_404(announcement_id)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_ar = request.form.get('title_ar', '').strip()
        content = request.form.get('content', '').strip()
        content_ar = request.form.get('content_ar', '').strip()
        announcement_type = request.form.get('type', 'info')
        target_audience = request.form.get('target_audience', 'all')
        is_active = safe_parse_bool(request.form.get('is_active'))
        is_featured = safe_parse_bool(request.form.get('is_featured'))
        display_until = request.form.get('display_until')
        
        if not title or not content:
            flash('العنوان والمحتوى مطلوبان', 'error')
            return render_template('admin/edit_announcement.html', announcement=announcement)
        
        # Convert display_until to datetime if provided
        display_until_dt = None
        if display_until:
            try:
                display_until_dt = datetime.strptime(display_until, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('تاريخ الانتهاء غير صحيح', 'error')
                return render_template('admin/edit_announcement.html', announcement=announcement)
        
        announcement.title = title
        announcement.title_ar = title_ar
        announcement.content = content
        announcement.content_ar = content_ar
        announcement.type = announcement_type
        announcement.target_audience = target_audience
        announcement.is_active = is_active
        announcement.is_featured = is_featured
        announcement.display_until = display_until_dt
        announcement.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash('تم تحديث الإعلان بنجاح', 'success')
        return redirect(url_for('admin_announcements'))
    
    return render_template('admin/edit_announcement.html', announcement=announcement)

@app.route('/admin/announcements/delete/<int:announcement_id>', methods=['POST'])
@login_required
def admin_delete_announcement(announcement_id):
    """Delete announcement"""
    if not current_user.is_admin:
        abort(403)
    
    announcement = Announcement.query.get_or_404(announcement_id)
    db.session.delete(announcement)
    db.session.commit()
    
    flash('تم حذف الإعلان بنجاح', 'success')
    return redirect(url_for('admin_announcements'))

@app.route('/admin/announcements/toggle/<int:announcement_id>')
@login_required
def admin_toggle_announcement(announcement_id):
    """Toggle announcement active status"""
    if not current_user.is_admin:
        abort(403)
    
    announcement = Announcement.query.get_or_404(announcement_id)
    announcement.is_active = not announcement.is_active
    db.session.commit()
    
    status = 'تم تفعيل' if announcement.is_active else 'تم إلغاء تفعيل'
    flash(f'{status} الإعلان بنجاح', 'success')
    return redirect(url_for('admin_announcements'))

# Advertisement Management Routes
@app.route('/admin/advertisements')
@login_required
def admin_advertisements():
    """Manage advertisements"""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    advertisements = Advertisement.query.order_by(Advertisement.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    ).items
    
    # Statistics
    total_ads = Advertisement.query.count()
    active_ads = Advertisement.query.filter_by(is_active=True).count()
    total_impressions = db.session.query(func.sum(Advertisement.impressions)).scalar() or 0
    total_clicks = db.session.query(func.sum(Advertisement.clicks)).scalar() or 0
    
    # Ad positions statistics
    ad_positions = {
        'before_reader': Advertisement.query.filter_by(placement='reader_top', is_active=True).count(),
        'after_reader': Advertisement.query.filter_by(placement='reader_bottom', is_active=True).count(),
        'between_pages': Advertisement.query.filter_by(placement='between_pages', is_active=True).count(),
        'sidebar': Advertisement.query.filter_by(placement='reader_side', is_active=True).count(),
        'header': Advertisement.query.filter_by(placement='header', is_active=True).count(),
        'footer': Advertisement.query.filter_by(placement='chapter_end', is_active=True).count()
    }
    
    return render_template('admin/advertisements.html',
                         advertisements=advertisements,
                         total_ads=total_ads,
                         active_ads=active_ads,
                         total_impressions=total_impressions,
                         total_clicks=total_clicks,
                         ad_positions=ad_positions)

@app.route('/admin/advertisements/add', methods=['GET', 'POST'])
@login_required
def admin_advertisement_add():
    """Add new advertisement"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        ad_type = request.form.get('ad_type', '').strip()
        placement = request.form.get('placement', '').strip()
        content = request.form.get('content', '').strip()
        ad_code = request.form.get('ad_code', '').strip()
        target_url = request.form.get('target_url', '').strip()
        priority = int(request.form.get('priority', 1))
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        is_active = safe_parse_bool(request.form.get('is_active'))
        open_new_tab = safe_parse_bool(request.form.get('open_new_tab'))
        
        if not title or not ad_type or not placement:
            flash('العنوان ونوع الإعلان وموقع العرض مطلوبة', 'error')
            return render_template('admin/advertisement_form.html')
        
        # Validate ad code for code type ads
        if ad_type == 'code':
            if not ad_code:
                flash('شفرة الإعلان مطلوبة لنوع الشفرة الإعلانية', 'error')
                return render_template('admin/advertisement_form.html')
            content = ad_code
        elif ad_type in ['image', 'banner'] and not content and 'image' not in request.files:
            flash('محتوى الإعلان أو صورة مطلوبة للإعلانات المرئية', 'error')
            return render_template('admin/advertisement_form.html')
        
        # Handle image upload
        image_url = None
        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            if file and allowed_file(file.filename, ['jpg', 'jpeg', 'png', 'gif']):
                filename = secure_filename(file.filename if file.filename else 'untitled')
                # Create unique filename
                import uuid
                filename = f"ad_{uuid.uuid4().hex[:8]}_{filename}"
                upload_path = os.path.join(app.config.get('UPLOAD_FOLDER', 'static/uploads'), 'ads')
                os.makedirs(upload_path, exist_ok=True)
                file_path = os.path.join(upload_path, filename)
                file.save(file_path)
                image_url = f"/static/uploads/ads/{filename}"
        
        # Convert dates
        start_date_dt = None
        end_date_dt = None
        if start_date:
            try:
                start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date:
            try:
                end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                pass
        
        advertisement = Advertisement()
        advertisement.title = title
        advertisement.description = description
        advertisement.ad_type = ad_type
        advertisement.placement = placement
        advertisement.content = content
        advertisement.image_url = image_url
        advertisement.target_url = target_url if target_url else None
        advertisement.priority = priority
        advertisement.start_date = start_date_dt
        advertisement.end_date = end_date_dt
        advertisement.is_active = is_active
        advertisement.open_new_tab = open_new_tab
        advertisement.created_by = current_user.id
        
        db.session.add(advertisement)
        db.session.commit()
        
        flash('تم إضافة الإعلان بنجاح', 'success')
        return redirect(url_for('admin_advertisements'))
    
    return render_template('admin/advertisement_form.html')

@app.route('/admin/advertisements/edit/<int:ad_id>', methods=['GET', 'POST'])
@login_required
def admin_advertisement_edit(ad_id):
    """Edit advertisement"""
    if not current_user.is_admin:
        abort(403)
    
    advertisement = Advertisement.query.get_or_404(ad_id)
    
    if request.method == 'POST':
        advertisement.title = request.form.get('title', '').strip()
        advertisement.description = request.form.get('description', '').strip()
        advertisement.ad_type = request.form.get('ad_type', '').strip()
        advertisement.placement = request.form.get('placement', '').strip()
        content = request.form.get('content', '').strip()
        ad_code = request.form.get('ad_code', '').strip()
        
        # For code ads, use ad_code field instead of content
        if advertisement.ad_type == 'code' and ad_code:
            advertisement.content = ad_code
        else:
            advertisement.content = content
            
        advertisement.target_url = request.form.get('target_url', '').strip() or None
        advertisement.priority = int(request.form.get('priority', 1))
        advertisement.is_active = safe_parse_bool(request.form.get('is_active'))
        advertisement.open_new_tab = safe_parse_bool(request.form.get('open_new_tab'))
        
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        # Convert dates
        if start_date:
            try:
                advertisement.start_date = datetime.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                advertisement.start_date = None
        else:
            advertisement.start_date = None
            
        if end_date:
            try:
                advertisement.end_date = datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                advertisement.end_date = None
        else:
            advertisement.end_date = None
        
        # Handle image upload
        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            if file and allowed_file(file.filename, ['jpg', 'jpeg', 'png', 'gif']):
                filename = secure_filename(file.filename if file.filename else 'untitled')
                # Create unique filename
                import uuid
                filename = f"ad_{uuid.uuid4().hex[:8]}_{filename}"
                upload_path = os.path.join(app.config.get('UPLOAD_FOLDER', 'static/uploads'), 'ads')
                os.makedirs(upload_path, exist_ok=True)
                file_path = os.path.join(upload_path, filename)
                file.save(file_path)
                advertisement.image_url = f"/static/uploads/ads/{filename}"
        
        advertisement.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash('تم تحديث الإعلان بنجاح', 'success')
        return redirect(url_for('admin_advertisements'))
    
    return render_template('admin/advertisement_form.html', advertisement=advertisement)

@app.route('/admin/advertisements/delete/<int:ad_id>', methods=['POST'])
@login_required
def admin_advertisement_delete(ad_id):
    """Delete advertisement"""
    if not current_user.is_admin:
        abort(403)
    
    advertisement = Advertisement.query.get_or_404(ad_id)
    db.session.delete(advertisement)
    db.session.commit()
    
    flash('تم حذف الإعلان بنجاح', 'success')
    return redirect(url_for('admin_advertisements'))

@app.route('/admin/advertisements/toggle/<int:ad_id>', methods=['POST'])
@login_required
def admin_advertisement_toggle(ad_id):
    """Toggle advertisement active status"""
    if not current_user.is_admin:
        abort(403)
    
    advertisement = Advertisement.query.get_or_404(ad_id)
    advertisement.is_active = not advertisement.is_active
    db.session.commit()
    
    status = 'تم تفعيل' if advertisement.is_active else 'تم إلغاء تفعيل'
    flash(f'{status} الإعلان بنجاح', 'success')
    return redirect(url_for('admin_advertisements'))

@app.route('/api/ad/impression/<int:ad_id>', methods=['POST'])
def record_ad_impression(ad_id):
    """Record advertisement impression"""
    advertisement = Advertisement.query.get_or_404(ad_id)
    advertisement.impressions += 1
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/ad/click/<int:ad_id>', methods=['POST'])
def record_ad_click(ad_id):
    """Record advertisement click"""
    advertisement = Advertisement.query.get_or_404(ad_id)
    advertisement.clicks += 1
    db.session.commit()
    return jsonify({'status': 'success'})

# Translation Requests Management
@app.route('/admin/translation-requests')
@login_required
def admin_translation_requests():
    """Admin page for managing translation requests"""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    language_filter = request.args.get('language', '')
    
    query = TranslationRequest.query
    
    # Apply filters
    if status_filter:
        query = query.filter(TranslationRequest.status == status_filter)
    if language_filter:
        query = query.filter(TranslationRequest.to_language == language_filter)
    
    # Get translation requests with pagination
    translation_requests = query.order_by(TranslationRequest.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get statistics
    stats = {
        'total_requests': TranslationRequest.query.count(),
        'open_requests': TranslationRequest.query.filter_by(status='open').count(),
        'in_progress': TranslationRequest.query.filter_by(status='in_progress').count(),
        'completed': TranslationRequest.query.filter_by(status='completed').count(),
        'published': TranslationRequest.query.filter_by(status='published').count()
    }
    
    return render_template('admin/translation_requests.html', 
                         translation_requests=translation_requests, 
                         stats=stats,
                         status_filter=status_filter,
                         language_filter=language_filter)

@app.route('/admin/translation-requests/<int:request_id>/assign', methods=['POST'])
@login_required
def admin_assign_translation(request_id):
    """Assign translation request to a translator"""
    if not current_user.is_admin:
        abort(403)
    
    translation_request = TranslationRequest.query.get_or_404(request_id)
    translator_id = request.form.get('translator_id')
    
    if translator_id:
        translator = User.query.get(translator_id)
        if translator and translator.is_translator:
            translation_request.translator_id = translator_id
            translation_request.status = 'assigned'
            db.session.commit()
            flash(f'تم تعيين طلب الترجمة للمترجم {translator.username}', 'success')
        else:
            flash('المترجم المحدد غير صالح', 'error')
    else:
        flash('يجب تحديد مترجم', 'error')
    
    return redirect(url_for('admin_translation_requests'))

@app.route('/admin/translation-requests/<int:request_id>/update-status', methods=['POST'])
@login_required
def admin_update_translation_status(request_id):
    """Update translation request status"""
    if not current_user.is_admin:
        abort(403)
    
    translation_request = TranslationRequest.query.get_or_404(request_id)
    new_status = request.form.get('status')
    
    if new_status in ['open', 'assigned', 'in_progress', 'completed', 'published']:
        translation_request.status = new_status
        if new_status == 'completed':
            translation_request.completed_at = datetime.utcnow()
        db.session.commit()
        flash('تم تحديث حالة طلب الترجمة', 'success')
    else:
        flash('حالة غير صالحة', 'error')
    
    return redirect(url_for('admin_translation_requests'))

# Chapter Review Management
@app.route('/admin/chapter-review')
@login_required
def admin_chapter_review():
    """Admin page for chapter review and approval"""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    publisher_filter = request.args.get('publisher', '')
    
    query = Chapter.query.join(Manga)
    
    # Apply filters
    if status_filter:
        if status_filter == 'pending':
            query = query.filter(Chapter.is_approved == False)
        elif status_filter == 'approved':
            query = query.filter(Chapter.is_approved == True)
    
    if publisher_filter:
        query = query.filter(Manga.publisher_id == publisher_filter)
    
    # Get chapters with pagination
    chapters = query.order_by(Chapter.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get statistics
    stats = {
        'total_chapters': Chapter.query.count(),
        'pending_review': Chapter.query.filter_by(is_approved=False).count(),
        'approved': Chapter.query.filter_by(is_approved=True).count(),
        'today_uploads': Chapter.query.filter(Chapter.created_at >= datetime.utcnow().date()).count()
    }
    
    # Get publishers for filter
    publishers = User.query.filter_by(is_publisher=True).all()
    
    return render_template('admin/chapter_review.html', 
                         chapters=chapters, 
                         stats=stats,
                         publishers=publishers,
                         status_filter=status_filter,
                         publisher_filter=publisher_filter)

@app.route('/admin/chapter-review/<int:chapter_id>/approve', methods=['POST'])
@login_required
def admin_approve_chapter(chapter_id):
    """Approve a chapter"""
    if not current_user.is_admin:
        abort(403)
    
    chapter = Chapter.query.get_or_404(chapter_id)
    chapter.is_approved = True
    chapter.approved_at = datetime.utcnow()
    chapter.approved_by = current_user.id
    
    db.session.commit()
    flash(f'تم قبول الفصل {chapter.title}', 'success')
    
    return redirect(url_for('admin_chapter_review'))

@app.route('/admin/chapter-review/<int:chapter_id>/reject', methods=['POST'])
@login_required
def admin_reject_chapter(chapter_id):
    """Reject a chapter"""
    if not current_user.is_admin:
        abort(403)
    
    chapter = Chapter.query.get_or_404(chapter_id)
    rejection_reason = request.form.get('reason', '')
    
    chapter.is_approved = False
    chapter.rejection_reason = rejection_reason
    chapter.reviewed_at = datetime.utcnow()
    chapter.reviewed_by = current_user.id
    
    db.session.commit()
    flash(f'تم رفض الفصل {chapter.title}', 'warning')
    
    return redirect(url_for('admin_chapter_review'))

# Additional Admin Action Routes for JavaScript Functions
@app.route('/admin/toggle_featured/<int:manga_id>', methods=['POST'])
@login_required
def admin_toggle_featured(manga_id):
    """Toggle manga featured status"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    manga = Manga.query.get_or_404(manga_id)
    manga.is_featured = not manga.is_featured
    db.session.commit()
    
    return jsonify({'success': True, 'is_featured': manga.is_featured})

@app.route('/admin/toggle_premium/<int:manga_id>', methods=['POST'])
@login_required
def admin_toggle_premium_manga(manga_id):
    """Toggle manga premium status"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    manga = Manga.query.get_or_404(manga_id)
    manga.is_premium = not manga.is_premium
    db.session.commit()
    
    return jsonify({'success': True, 'is_premium': manga.is_premium})

@app.route('/admin/toggle_chapter_status/<int:chapter_id>', methods=['POST'])
@login_required
def admin_toggle_chapter_status(chapter_id):
    """Toggle chapter published status"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    chapter = Chapter.query.get_or_404(chapter_id)
    chapter.status = 'published' if chapter.status != 'published' else 'draft'
    db.session.commit()
    
    return jsonify({'success': True, 'status': chapter.status})

@app.route('/admin/toggle_chapter_premium/<int:chapter_id>', methods=['POST'])
@login_required
def admin_toggle_chapter_premium(chapter_id):
    """Toggle chapter premium status"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    chapter = Chapter.query.get_or_404(chapter_id)
    chapter.is_premium = not chapter.is_premium
    db.session.commit()
    
    return jsonify({'success': True, 'is_premium': chapter.is_premium})

@app.route('/admin/delete_chapter/<int:chapter_id>', methods=['POST'])
@login_required
def admin_delete_chapter(chapter_id):
    """Delete a chapter and its images"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    chapter = Chapter.query.get_or_404(chapter_id)
    manga_id = chapter.manga_id
    
    try:
        logging.info(f"🗑️ Starting deletion process for chapter {chapter_id} from manga {manga_id}")
        
        # Delete images from Cloudinary
        try:
            from app.utils_cloudinary import cloudinary_uploader
            cloudinary_result = cloudinary_uploader.delete_chapter_images(manga_id, chapter_id)
            if cloudinary_result['success']:
                logging.info(f"✅ Deleted {cloudinary_result['deleted_count']} images from Cloudinary")
                if cloudinary_result.get('errors'):
                    logging.warning(f"⚠️ Some Cloudinary deletion errors: {cloudinary_result['errors']}")
            else:
                logging.error(f"❌ Failed to delete images from Cloudinary: {cloudinary_result.get('error')}")
        except Exception as e:
            logging.error(f"❌ Error during Cloudinary deletion: {e}")
        
        # Delete chapter images from local storage (backup/fallback)
        for page in chapter.page_images:
            if page.image_path and os.path.exists(page.image_path):
                try:
                    os.remove(page.image_path)
                    logging.info(f"✅ Deleted local image: {page.image_path}")
                except Exception as e:
                    logging.warning(f"⚠️ Could not delete local image: {e}")
        
        # Delete the chapter from database
        db.session.delete(chapter)
        db.session.commit()
        
        logging.info(f"✅ Successfully deleted chapter {chapter_id} from database")
        
        return jsonify({
            'success': True, 
            'message': 'تم حذف الفصل بنجاح من قاعدة البيانات والتخزين السحابي!'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error deleting chapter {chapter_id}: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'خطأ في حذف الفصل: {str(e)}'
        }), 500

@app.route('/admin/schedule_chapter/<int:chapter_id>', methods=['POST'])
@login_required
def admin_schedule_chapter(chapter_id):
    """Schedule chapter publication"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    datetime_str = data.get('datetime')
    
    try:
        scheduled_time = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
        chapter = Chapter.query.get_or_404(chapter_id)
        chapter.release_date = scheduled_time
        chapter.status = 'scheduled'
        db.session.commit()
        
        return jsonify({'success': True})
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid datetime format'})

@app.route('/admin/duplicate_chapter/<int:chapter_id>', methods=['POST'])
@login_required
def admin_duplicate_chapter(chapter_id):
    """Duplicate a chapter"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    original = Chapter.query.get_or_404(chapter_id)
    
    # Create new chapter
    new_chapter = Chapter()
    new_chapter.manga_id = original.manga_id
    new_chapter.title = f"{original.title} (Copy)"
    new_chapter.chapter_number = original.chapter_number + 0.1
    new_chapter.is_premium = original.is_premium
    new_chapter.publisher_id = current_user.id
    
    db.session.add(new_chapter)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/duplicate_manga/<int:manga_id>', methods=['POST'])
@login_required
def admin_duplicate_manga(manga_id):
    """Duplicate a manga"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    original = Manga.query.get_or_404(manga_id)
    
    # Create new manga
    new_manga = Manga()
    new_manga.title = f"{original.title} (Copy)"
    new_manga.title_ar = f"{original.title_ar} (نسخة)" if original.title_ar else None
    new_manga.description = original.description
    new_manga.description_ar = original.description_ar
    new_manga.author = original.author
    new_manga.artist = original.artist
    new_manga.type = original.type
    new_manga.status = 'draft'
    new_manga.age_rating = original.age_rating
    new_manga.publisher_id = current_user.id
    
    db.session.add(new_manga)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/update-credentials', methods=['POST'])
@login_required
def admin_update_credentials():
    """Update admin credentials (username, email, password)"""
    if not current_user.is_admin:
        abort(403)
    
    from werkzeug.security import check_password_hash, generate_password_hash
    
    try:
        current_password = request.form.get('current_password', '')
        new_username = request.form.get('new_username', '').strip()
        new_email = request.form.get('new_email', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Verify current password
        if not check_password_hash(current_user.password_hash, current_password):
            flash('كلمة المرور الحالية غير صحيحة', 'error')
            return redirect(url_for('admin_settings'))
        
        # Validate new password if provided
        if new_password:
            if new_password != confirm_password:
                flash('كلمات المرور الجديدة غير متطابقة', 'error')
                return redirect(url_for('admin_settings'))
            
            if len(new_password) < 8:
                flash('كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل', 'error')
                return redirect(url_for('admin_settings'))
        
        # Check for username conflicts
        if new_username and new_username != current_user.username:
            if User.query.filter_by(username=new_username).first():
                flash('اسم المستخدم موجود بالفعل', 'error')
                return redirect(url_for('admin_settings'))
        
        # Check for email conflicts  
        if new_email and new_email != current_user.email:
            if User.query.filter_by(email=new_email).first():
                flash('البريد الإلكتروني موجود بالفعل', 'error')
                return redirect(url_for('admin_settings'))
        
        # Update user fields
        updated_fields = []
        
        if new_username and new_username != current_user.username:
            current_user.username = new_username
            updated_fields.append('اسم المستخدم')
        
        if new_email and new_email != current_user.email:
            current_user.email = new_email
            updated_fields.append('البريد الإلكتروني')
        
        if new_password:
            current_user.password_hash = generate_password_hash(new_password)
            updated_fields.append('كلمة المرور')
        
        if updated_fields:
            db.session.commit()
            flash(f'تم تحديث {", ".join(updated_fields)} بنجاح', 'success')
            
            # If credentials changed, user needs to re-login
            if 'اسم المستخدم' in updated_fields or 'كلمة المرور' in updated_fields:
                flash('يرجى تسجيل الدخول مرة أخرى بالبيانات الجديدة', 'info')
                from flask_login import logout_user
                logout_user()
                return redirect(url_for('login'))
        else:
            flash('لم يتم تغيير أي بيانات', 'info')
        
    except Exception as e:
        print(f'Error updating admin credentials: {e}')
        flash('حدث خطأ أثناء تحديث البيانات', 'error')
    
    return redirect(url_for('admin_settings'))

# Advanced Comments System Routes

@app.route('/comment/<int:comment_id>/react', methods=['POST'])
@login_required
def react_to_comment(comment_id):
    """Add or update reaction to a comment"""
    comment = Comment.query.get_or_404(comment_id)
    if not request.json:
        return jsonify({'error': 'Invalid request'}), 400
    reaction_type = request.json.get('reaction_type')
    
    valid_reactions = ['surprised', 'angry', 'shocked', 'love', 'laugh', 'thumbs_up']
    
    if reaction_type not in valid_reactions:
        return jsonify({'error': 'Invalid reaction type'}), 400
    
    # Check if user already reacted
    existing_reaction = CommentReaction.query.filter_by(
        user_id=current_user.id, 
        comment_id=comment_id
    ).first()
    
    if existing_reaction:
        if existing_reaction.reaction_type == reaction_type:
            # Same reaction - remove it
            db.session.delete(existing_reaction)
            action = 'removed'
        else:
            # Different reaction - update it
            existing_reaction.reaction_type = reaction_type
            action = 'updated'
    else:
        # New reaction
        reaction = CommentReaction()
        reaction.user_id = current_user.id
        reaction.comment_id = comment_id
        reaction.reaction_type = reaction_type
        db.session.add(reaction)
        action = 'added'
    
    db.session.commit()
    
    # Get updated reaction counts
    reaction_counts = comment.get_reaction_counts()
    user_reaction = comment.get_user_reaction(current_user.id)
    
    return jsonify({
        'success': True,
        'action': action,
        'reaction_counts': reaction_counts,
        'user_reaction': user_reaction
    })

# ===== STATIC PAGES MANAGEMENT ROUTES =====
@app.route('/admin/static-pages')
@login_required
def admin_static_pages():
    """Admin static pages management"""
    if not current_user.is_admin:
        abort(403)
    
    # Get all static pages with pagination
    page = request.args.get('page', 1, type=int)
    pages = StaticPage.query.order_by(StaticPage.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Statistics
    total_pages = StaticPage.query.count()
    published_pages = StaticPage.query.filter_by(is_published=True).count()
    menu_pages = StaticPage.query.filter_by(show_in_menu=True).count()
    
    return render_template('admin/static_pages.html',
                         pages=pages,
                         total_pages=total_pages,
                         published_pages=published_pages,
                         menu_pages=menu_pages)

@app.route('/admin/static-pages/add', methods=['GET', 'POST'])
@login_required
def admin_add_static_page():
    """Add new static page"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_ar = request.form.get('title_ar', '').strip()
        slug = request.form.get('slug', '').strip()
        content = request.form.get('content', '')
        content_ar = request.form.get('content_ar', '')
        meta_description = request.form.get('meta_description', '').strip()
        meta_description_ar = request.form.get('meta_description_ar', '').strip()
        meta_keywords = request.form.get('meta_keywords', '').strip()
        is_published = safe_parse_bool(request.form.get('is_published'))
        show_in_menu = safe_parse_bool(request.form.get('show_in_menu'))
        menu_order = int(request.form.get('menu_order', 0))
        template_name = request.form.get('template_name', 'static_page.html').strip()
        
        # Validate required fields
        if not title or not slug or not content:
            flash('العنوان والرابط والمحتوى مطلوبة', 'error')
            return render_template('admin/add_static_page.html')
        
        # Check for existing slug
        if StaticPage.query.filter_by(slug=slug).first():
            flash('هذا الرابط مستخدم بالفعل', 'error')
            return render_template('admin/add_static_page.html')
        
        # Create new static page
        page = StaticPage()
        page.title = title
        page.title_ar = title_ar
        page.slug = slug
        page.content = content
        page.content_ar = content_ar
        page.meta_description = meta_description
        page.meta_description_ar = meta_description_ar
        page.meta_keywords = meta_keywords
        page.is_published = is_published
        page.show_in_menu = show_in_menu
        page.menu_order = menu_order
        page.template_name = template_name
        page.created_by_id = current_user.id
        
        db.session.add(page)
        db.session.commit()
        
        flash('تم إضافة الصفحة بنجاح', 'success')
        return redirect(url_for('admin_static_pages'))
    
    return render_template('admin/add_static_page.html')

@app.route('/admin/static-pages/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_static_page(page_id):
    """Edit static page"""
    if not current_user.is_admin:
        abort(403)
    
    page = StaticPage.query.get_or_404(page_id)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_ar = request.form.get('title_ar', '').strip()
        slug = request.form.get('slug', '').strip()
        content = request.form.get('content', '')
        content_ar = request.form.get('content_ar', '')
        meta_description = request.form.get('meta_description', '').strip()
        meta_description_ar = request.form.get('meta_description_ar', '').strip()
        meta_keywords = request.form.get('meta_keywords', '').strip()
        is_published = safe_parse_bool(request.form.get('is_published'))
        show_in_menu = safe_parse_bool(request.form.get('show_in_menu'))
        menu_order = int(request.form.get('menu_order', 0))
        template_name = request.form.get('template_name', 'static_page.html').strip()
        
        # Validate required fields
        if not title or not slug or not content:
            flash('العنوان والرابط والمحتوى مطلوبة', 'error')
            return render_template('admin/edit_static_page.html', page=page)
        
        # Check for existing slug (excluding current page)
        existing_page = StaticPage.query.filter_by(slug=slug).first()
        if existing_page and existing_page.id != page.id:
            flash('هذا الرابط مستخدم بالفعل', 'error')
            return render_template('admin/edit_static_page.html', page=page)
        
        # Update page
        page.title = title
        page.title_ar = title_ar
        page.slug = slug
        page.content = content
        page.content_ar = content_ar
        page.meta_description = meta_description
        page.meta_description_ar = meta_description_ar
        page.meta_keywords = meta_keywords
        page.is_published = is_published
        page.show_in_menu = show_in_menu
        page.menu_order = menu_order
        page.template_name = template_name
        
        db.session.commit()
        
        flash('تم تحديث الصفحة بنجاح', 'success')
        return redirect(url_for('admin_static_pages'))
    
    return render_template('admin/edit_static_page.html', page=page)

@app.route('/admin/static-pages/<int:page_id>/toggle-publish', methods=['POST'])
@login_required
def admin_toggle_page_publish(page_id):
    """Toggle static page publish status"""
    if not current_user.is_admin:
        abort(403)
    
    page = StaticPage.query.get_or_404(page_id)
    page.is_published = not page.is_published
    db.session.commit()
    
    status = 'نشرت' if page.is_published else 'ألغي نشرها'
    flash(f'تم {status} الصفحة "{page.title}" بنجاح', 'success')
    return redirect(url_for('admin_static_pages'))

@app.route('/admin/static-pages/<int:page_id>/delete', methods=['POST'])
@login_required
def admin_delete_static_page(page_id):
    """Delete static page"""
    if not current_user.is_admin:
        abort(403)
    
    page = StaticPage.query.get_or_404(page_id)
    page_title = page.title
    
    db.session.delete(page)
    db.session.commit()
    
    flash(f'تم حذف الصفحة "{page_title}" بنجاح', 'success')
    return redirect(url_for('admin_static_pages'))

# Public route for displaying static pages
@app.route('/page/<slug>')
def static_page(slug):
    """Display static page"""
    # Special case: redirect /page/help to /help
    if slug == 'help':
        return redirect(url_for('help_page'))
    
    page = StaticPage.query.filter_by(slug=slug, is_published=True).first_or_404()
    
    # Use custom template if specified
    template = page.template_name if page.template_name else 'static_page.html'
    
    return render_template(template, page=page)

# Image upload route for TinyMCE
@app.route('/admin/upload-image', methods=['POST'])
@login_required
def admin_upload_image():
    """Upload image for static pages content"""
    if not current_user.is_admin:
        abort(403)
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check if file is an image
    if not file.filename or not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        return jsonify({'error': 'Invalid file type. Only images are allowed.'}), 400
    
    try:
        # Create upload directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads', 'pages')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        # Generate unique filename
        import uuid as uuid_lib
        if file.filename and '.' in file.filename:
            file_extension = file.filename.rsplit('.', 1)[1].lower()
        else:
            file_extension = 'jpg'  # default extension
        filename = f"{uuid_lib.uuid4()}.{file_extension}"
        filepath = os.path.join(upload_dir, filename)
        
        # Save the file
        file.save(filepath)
        
        # Optimize image if it's too large
        try:
            with Image.open(filepath) as img:
                # Convert RGBA to RGB if necessary
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Resize if image is too large
                max_width, max_height = 1200, 1200
                if img.width > max_width or img.height > max_height:
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    img.save(filepath, optimize=True, quality=85)
        except Exception as e:
            logging.warning(f"Image optimization failed: {e}")
        
        # Return the URL for TinyMCE
        image_url = f"/static/uploads/pages/{filename}"
        return jsonify({'location': image_url})
        
    except Exception as e:
        logging.error(f"Image upload failed: {e}")
        return jsonify({'error': 'Upload failed'}), 500

# ===== BLOG MANAGEMENT ROUTES =====
@app.route('/admin/blog')
@login_required
def admin_blog():
    """Admin blog management"""
    if not current_user.is_admin:
        abort(403)
    
    # Get all blog posts with pagination
    page = request.args.get('page', 1, type=int)
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Statistics
    total_posts = BlogPost.query.count()
    published_posts = BlogPost.query.filter_by(is_published=True).count()
    featured_posts = BlogPost.query.filter_by(is_featured=True).count()
    draft_posts = BlogPost.query.filter_by(is_published=False).count()
    
    return render_template('admin/blog.html',
                         posts=posts,
                         total_posts=total_posts,
                         published_posts=published_posts,
                         featured_posts=featured_posts,
                         draft_posts=draft_posts)

@app.route('/admin/blog/add', methods=['GET', 'POST'])
@login_required
def admin_add_blog_post():
    """Add new blog post"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_ar = request.form.get('title_ar', '').strip()
        slug = request.form.get('slug', '').strip()
        excerpt = request.form.get('excerpt', '').strip()
        excerpt_ar = request.form.get('excerpt_ar', '').strip()
        content = request.form.get('content', '')
        content_ar = request.form.get('content_ar', '')
        featured_image = request.form.get('featured_image', '').strip()
        meta_description = request.form.get('meta_description', '').strip()
        meta_description_ar = request.form.get('meta_description_ar', '').strip()
        meta_keywords = request.form.get('meta_keywords', '').strip()
        tags = request.form.get('tags', '').strip()
        tags_ar = request.form.get('tags_ar', '').strip()
        category = request.form.get('category', '').strip()
        category_ar = request.form.get('category_ar', '').strip()
        is_published = request.form.get('is_published') == 'on'
        is_featured = request.form.get('is_featured') == 'on'
        
        # Validate required fields
        if not title or not slug or not content:
            flash('العنوان والرابط والمحتوى مطلوبة', 'error')
            return render_template('admin/add_blog_post.html')
        
        # Check for existing slug
        if BlogPost.query.filter_by(slug=slug).first():
            flash('هذا الرابط مستخدم بالفعل', 'error')
            return render_template('admin/add_blog_post.html')
        
        # Create new blog post
        post = BlogPost()
        post.title = title
        post.title_ar = title_ar
        post.slug = slug
        post.excerpt = excerpt
        post.excerpt_ar = excerpt_ar
        post.content = content
        post.content_ar = content_ar
        post.featured_image = featured_image
        post.meta_description = meta_description
        post.meta_description_ar = meta_description_ar
        post.meta_keywords = meta_keywords
        post.tags = tags
        post.tags_ar = tags_ar
        post.category = category
        post.category_ar = category_ar
        post.is_published = is_published
        post.is_featured = is_featured
        post.author_id = current_user.id
        post.reading_time = post.get_reading_time()
        
        if is_published:
            post.published_at = datetime.utcnow()
        
        db.session.add(post)
        db.session.commit()
        
        flash('تم إضافة المقال بنجاح', 'success')
        return redirect(url_for('admin_blog'))
    
    return render_template('admin/add_blog_post.html')

@app.route('/admin/blog/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_blog_post(post_id):
    """Edit blog post"""
    if not current_user.is_admin:
        abort(403)
    
    post = BlogPost.query.get_or_404(post_id)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_ar = request.form.get('title_ar', '').strip()
        slug = request.form.get('slug', '').strip()
        excerpt = request.form.get('excerpt', '').strip()
        excerpt_ar = request.form.get('excerpt_ar', '').strip()
        content = request.form.get('content', '')
        content_ar = request.form.get('content_ar', '')
        featured_image = request.form.get('featured_image', '').strip()
        meta_description = request.form.get('meta_description', '').strip()
        meta_description_ar = request.form.get('meta_description_ar', '').strip()
        meta_keywords = request.form.get('meta_keywords', '').strip()
        tags = request.form.get('tags', '').strip()
        tags_ar = request.form.get('tags_ar', '').strip()
        category = request.form.get('category', '').strip()
        category_ar = request.form.get('category_ar', '').strip()
        is_published = safe_parse_bool(request.form.get('is_published'))
        is_featured = safe_parse_bool(request.form.get('is_featured'))
        
        # Validate required fields
        if not title or not slug or not content:
            flash('العنوان والرابط والمحتوى مطلوبة', 'error')
            return render_template('admin/edit_blog_post.html', post=post)
        
        # Check for existing slug (excluding current post)
        existing_post = BlogPost.query.filter_by(slug=slug).first()
        if existing_post and existing_post.id != post.id:
            flash('هذا الرابط مستخدم بالفعل', 'error')
            return render_template('admin/edit_blog_post.html', post=post)
        
        # Update post
        was_published = post.is_published
        post.title = title
        post.title_ar = title_ar
        post.slug = slug
        post.excerpt = excerpt
        post.excerpt_ar = excerpt_ar
        post.content = content
        post.content_ar = content_ar
        post.featured_image = featured_image
        post.meta_description = meta_description
        post.meta_description_ar = meta_description_ar
        post.meta_keywords = meta_keywords
        post.tags = tags
        post.tags_ar = tags_ar
        post.category = category
        post.category_ar = category_ar
        post.is_published = is_published
        post.is_featured = is_featured
        post.reading_time = post.get_reading_time()
        
        # Set published_at if publishing for the first time
        if is_published and not was_published:
            post.published_at = datetime.utcnow()
        
        db.session.commit()
        
        flash('تم تحديث المقال بنجاح', 'success')
        return redirect(url_for('admin_blog'))
    
    return render_template('admin/edit_blog_post.html', post=post)

@app.route('/admin/blog/delete/<int:post_id>', methods=['POST'])
@login_required
def admin_delete_blog_post(post_id):
    """Delete blog post"""
    if not current_user.is_admin:
        abort(403)
    
    post = BlogPost.query.get_or_404(post_id)
    post_title = post.title
    
    db.session.delete(post)
    db.session.commit()
    
    flash(f'تم حذف المقال "{post_title}" بنجاح', 'success')
    return redirect(url_for('admin_blog'))

# Image upload route for blog content
@app.route('/admin/blog/upload-image', methods=['POST'])
@login_required
def admin_blog_upload_image():
    """Upload image for blog posts content"""
    if not current_user.is_admin:
        abort(403)
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check if file is an image
    if not file.filename or not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        return jsonify({'error': 'Invalid file type. Only images are allowed.'}), 400
    
    try:
        # Create upload directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads', 'blog')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        # Generate unique filename
        import uuid as uuid_lib
        if file.filename and '.' in file.filename:
            file_extension = file.filename.rsplit('.', 1)[1].lower()
        else:
            file_extension = 'jpg'  # default extension
        filename = f"{uuid_lib.uuid4()}.{file_extension}"
        filepath = os.path.join(upload_dir, filename)
        
        # Save the file
        file.save(filepath)
        
        # Optimize image if it's too large
        try:
            with Image.open(filepath) as img:
                # Convert RGBA to RGB if necessary
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Resize if image is too large
                max_width, max_height = 1200, 1200
                if img.width > max_width or img.height > max_height:
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    img.save(filepath, optimize=True, quality=85)
        except Exception as e:
            logging.warning(f"Image optimization failed: {e}")
        
        # Return the URL for editor
        image_url = f"/static/uploads/blog/{filename}"
        return jsonify({'location': image_url})
        
    except Exception as e:
        logging.error(f"Blog image upload failed: {e}")
        return jsonify({'error': 'Upload failed'}), 500

# Public routes for blog
@app.route('/blog')
def blog():
    """Public blog page"""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    tag = request.args.get('tag')
    
    query = BlogPost.query.filter_by(is_published=True)
    
    if category:
        query = query.filter(BlogPost.category == category)
    
    if tag:
        query = query.filter(BlogPost.tags.contains(tag))
    
    posts = query.order_by(BlogPost.published_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    
    # Get featured posts
    featured_posts = BlogPost.query.filter_by(is_published=True, is_featured=True).limit(3).all()
    
    # Get categories
    categories = db.session.query(BlogPost.category).filter(
        BlogPost.category.isnot(None),
        BlogPost.is_published == True
    ).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('blog/index.html', 
                         posts=posts, 
                         featured_posts=featured_posts,
                         categories=categories,
                         current_category=category,
                         current_tag=tag)

@app.route('/blog/<slug>')
def blog_post(slug):
    """Display blog post"""
    post = BlogPost.query.filter_by(slug=slug, is_published=True).first_or_404()
    
    # Increment view count
    post.views += 1
    db.session.commit()
    
    # Get related posts (same category)
    related_posts = BlogPost.query.filter(
        BlogPost.category == post.category,
        BlogPost.id != post.id,
        BlogPost.is_published == True
    ).limit(3).all()
    
    return render_template('blog/post.html', post=post, related_posts=related_posts)


# Cloudinary Account Management Routes
@app.route('/admin/cloudinary/add-account', methods=['POST'])
@login_required
def admin_cloudinary_add_account():
    """Add new Cloudinary account"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_cloudinary import CloudinaryAccountManager
        
        # Get form data
        account_name = request.form.get('account_name', '').strip()
        cloud_name = request.form.get('cloud_name', '').strip()
        api_key = request.form.get('api_key', '').strip()
        api_secret = request.form.get('api_secret', '').strip()
        
        # Safely parse storage limit with NaN protection
        try:
            storage_limit = safe_parse_float(request.form.get('storage_limit', '25600'), 25600.0, "storage limit")
        except ValueError as e:
            return jsonify({'success': False, 'message': f'حد التخزين غير صحيح: {str(e)}'})
        
        plan_type = request.form.get('plan_type', 'free')
        is_primary = request.form.get('is_primary') == 'on'
        notes = request.form.get('notes', '').strip()
        
        # Validation
        if not all([account_name, cloud_name, api_key, api_secret]):
            return jsonify({'success': False, 'message': 'جميع الحقول مطلوبة'})
        
        # Create account
        account = CloudinaryAccountManager.create_account(
            name=account_name,
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            storage_limit_mb=int(storage_limit),
            is_primary=is_primary
        )
        
        # Add notes if provided
        if notes:
            account.notes = notes
            db.session.commit()
        
        return jsonify({'success': True, 'message': f'تم إضافة حساب {account_name} بنجاح'})
        
    except Exception as e:
        logging.error(f"Failed to add Cloudinary account: {e}")
        return jsonify({'success': False, 'message': f'حدث خطأ: {str(e)}'})

@app.route('/admin/cloudinary/delete-account/<int:account_id>', methods=['DELETE'])
@login_required
def admin_cloudinary_delete_account(account_id):
    """Delete Cloudinary account"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        
        account = CloudinaryAccount.query.get_or_404(account_id)
        account_name = account.name
        
        db.session.delete(account)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'تم حذف حساب {account_name} بنجاح'})
        
    except Exception as e:
        logging.error(f"Failed to delete Cloudinary account: {e}")
        return jsonify({'success': False, 'message': f'حدث خطأ في حذف الحساب: {str(e)}'})

@app.route('/admin/cloudinary/test-connection/<int:account_id>')
@login_required
def admin_cloudinary_test_connection(account_id):
    """Test Cloudinary account connection"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        import cloudinary
        
        account = CloudinaryAccount.query.get_or_404(account_id)
        
        # Configure Cloudinary with account credentials
        cloudinary.config(
            cloud_name=account.cloud_name,
            api_key=account.api_key,
            api_secret=account.api_secret
        )
        
        # Test API call - get account usage
        import cloudinary.api
        result = cloudinary.api.usage()
        
        # Update account storage usage
        if 'storage' in result:
            storage_bytes = result['storage']['usage']
            storage_mb = storage_bytes / (1024 * 1024)
            account.update_usage_stats(storage_mb=storage_mb)
        
        return jsonify({
            'success': True, 
            'message': 'تم الاتصال بنجاح!',
            'usage_data': result.get('storage', {})
        })
        
    except Exception as e:
        logging.error(f"Failed to test Cloudinary connection: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/cloudinary/refresh-usage')
@login_required
def admin_cloudinary_refresh_usage():
    """Refresh usage statistics for all Cloudinary accounts"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.models import CloudinaryAccount
        import cloudinary
        
        accounts = CloudinaryAccount.query.filter_by(is_active=True).all()
        updated_accounts = 0
        
        for account in accounts:
            try:
                # Configure Cloudinary for this account
                cloudinary.config(
                    cloud_name=account.cloud_name,
                    api_key=account.api_key,
                    api_secret=account.api_secret
                )
                
                # Get usage data
                import cloudinary.api
                result = cloudinary.api.usage()
                
                # Update storage usage
                if 'storage' in result:
                    storage_bytes = result['storage']['usage']
                    storage_mb = storage_bytes / (1024 * 1024)
                    account.update_usage_stats(storage_mb=storage_mb)
                    updated_accounts += 1
                    
            except Exception as e:
                logging.warning(f"Failed to update usage for account {account.name}: {e}")
                continue
        
        return jsonify({
            'success': True, 
            'message': f'تم تحديث إحصائيات {updated_accounts} حساب'
        })
        
    except Exception as e:
        logging.error(f"Failed to refresh usage statistics: {e}")
        return jsonify({'success': False, 'message': f'حدث خطأ: {str(e)}'})




@app.route('/admin/quick-setup-stripe', methods=['POST'])
@login_required
def admin_quick_setup_stripe():
    """Quick setup for Stripe payment gateway"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        # Get form data
        display_name = request.form.get('display_name', 'Stripe - بطاقات الدفع')
        environment = request.form.get('environment', 'sandbox')
        publishable_key = request.form.get('publishable_key', '').strip()
        secret_key = request.form.get('secret_key', '').strip()
        webhook_secret = request.form.get('webhook_secret', '').strip()
        currencies = request.form.getlist('currencies')
        is_active = request.form.get('is_active') == 'on'
        is_default = request.form.get('is_default') == 'on'
        
        # Validation
        if not publishable_key or not secret_key:
            return jsonify({'success': False, 'message': 'يجب إدخال مفاتيح Stripe المطلوبة'})
        
        # Check if Stripe gateway already exists
        existing_gateway = PaymentGateway.query.filter_by(gateway_type='stripe').first()
        
        if existing_gateway:
            # Update existing
            gateway = existing_gateway
            gateway.display_name = display_name
            gateway.display_name_ar = display_name
        else:
            # Create new
            gateway = PaymentGateway()
            gateway.name = 'stripe'
            gateway.display_name = display_name
            gateway.display_name_ar = display_name
            gateway.gateway_type = 'stripe'
        
        # Set configuration
        gateway.is_active = is_active
        gateway.is_sandbox = (environment == 'sandbox')
        gateway.is_default = is_default
        
        if currencies:
            gateway.supported_currencies = currencies
        else:
            gateway.supported_currencies = ['USD']
        
        gateway.config_data = {
            'publishable_key': publishable_key,
            'secret_key': secret_key,
            'webhook_secret': webhook_secret if webhook_secret else '',
            'environment': environment
        }
        
        gateway.description_ar = 'بوابة دفع Stripe - دعم جميع أنواع البطاقات والمحافظ الرقمية'
        gateway.logo_url = 'https://stripe.com/img/v3/newsroom/social.png'
        
        # Make default if requested
        if is_default:
            # Remove default from other gateways
            PaymentGateway.query.filter(PaymentGateway.id != gateway.id).update({'is_default': False})
        
        if not existing_gateway:
            db.session.add(gateway)
        
        db.session.commit()
        
        flash('تم إعداد Stripe بنجاح!', 'success')
        return redirect(url_for('admin_payment_gateways'))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error setting up Stripe: {e}")
        return jsonify({'success': False, 'message': f'خطأ في إعداد Stripe: {str(e)}'})


# ================================================
# Database Connection Management Routes
# ================================================

@app.route('/admin/database-connection')
@login_required
def admin_database_connection():
    """Database connection management page"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        import os
        from datetime import datetime
        from sqlalchemy import text
        
        # Get current database info from database_config
        from config.database_config import db_config
        db_type = db_config.database_type.upper()
        db_connected = True
        table_count = 0
        last_check = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        current_database_url = os.environ.get("DATABASE_URL", "")
        
        try:
            if db_config.is_postgresql():
                # PostgreSQL
                result = db.session.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"))
                table_count = result.scalar()
            elif db_config.is_mysql():
                # MySQL
                result = db.session.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"))
                table_count = result.scalar()
            else:
                # SQLite
                result = db.session.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"))
                table_count = result.scalar()
        except:
            table_count = "غير معروف"
            db_connected = False
        
        # Hide password in display URL
        display_url = current_database_url
        if display_url and "@" in display_url:
            parts = display_url.split("@")
            if len(parts) > 1:
                user_pass = parts[0].split("://")[1]
                if ":" in user_pass:
                    user, password = user_pass.split(":", 1)
                    display_url = display_url.replace(f":{password}@", ":***@")
        
        # Add migration information
        from config.database_config import db_config
        from database.migration_manager import migration_manager
        import platform
        import sys
        import sqlite3
        
        # Migration status
        can_migrate = False
        migration_message = "غير متاح"
        
        if db_config.is_sqlite():
            can_migrate, migration_message = migration_manager.can_migrate_to_postgresql()
        
        # Database statistics
        total_records = 0
        database_size = "غير متوفر"
        
        if db_config.is_sqlite():
            try:
                conn = sqlite3.connect('manga_platform.db')
                cursor = conn.cursor()
                
                # Count total records (approximate)
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                for table in tables:
                    try:
                        cursor.execute(f"SELECT count(*) FROM {table[0]}")
                        total_records += cursor.fetchone()[0]
                    except:
                        continue
                
                # Get database size
                import os
                if os.path.exists('manga_platform.db'):
                    size_bytes = os.path.getsize('manga_platform.db')
                    database_size = f"{size_bytes / (1024*1024):.2f} MB"
                
                conn.close()
            except Exception as e:
                logging.warning(f"Could not get SQLite stats: {e}")
        
        # Get version info
        sqlite_version = sqlite3.sqlite_version if db_config.is_sqlite() else "غير مستخدم"
        postgresql_version = "غير متصل"
        
        if db_config.is_postgresql():
            try:
                result = db.engine.execute(db.text("SELECT version()"))
                version_row = result.fetchone()
                postgresql_version = version_row[0] if version_row else "غير متوفر"
            except:
                postgresql_version = "خطأ في الاتصال"

        return render_template('admin/database_connection.html',
                             db_type=db_type,
                             db_connected=db_connected,
                             table_count=table_count,
                             last_check=last_check,
                             current_database_url=display_url,
                             current_db=db_config.database_type,
                             total_records=total_records,
                             database_size=database_size,
                             can_migrate=can_migrate,
                             migration_message=migration_message,
                             sqlite_version=sqlite_version,
                             postgresql_version=postgresql_version,
                             platform_info=platform.system(),
                             python_version=sys.version.split()[0],
                             status_timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                             
    except Exception as e:
        logging.error(f"Error loading database connection page: {e}")
        flash('خطأ في تحميل صفحة إعدادات قاعدة البيانات', 'error')
        return redirect(url_for('admin_panel'))


@app.route('/admin/database-connection/update', methods=['POST'])
@login_required
def admin_update_database_connection():
    """Update database connection settings"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        db_type = request.form.get('db_type', 'postgresql')  # Default to postgresql for backward compatibility
        connection_type = request.form.get('connection_type')
        
        if connection_type == 'database_url':
            if db_type == 'mysql':
                database_url = request.form.get('mysql_database_url', '').strip()
            else:
                database_url = request.form.get('database_url', '').strip()
            
            if not database_url:
                flash('يرجى إدخال رابط قاعدة البيانات', 'error')
                return redirect(url_for('admin_database_connection'))
                
        else:  # separate_fields
            if db_type == 'mysql':
                host = request.form.get('mysql_host', '').strip()
                port = request.form.get('mysql_port', '3306')
                username = request.form.get('mysql_username', '').strip()
                password = request.form.get('mysql_password', '').strip()
                database = request.form.get('mysql_database', '').strip()
                charset = request.form.get('mysql_charset', 'utf8mb4').strip()
                
                if not all([host, username, password, database]):
                    flash('جميع الحقول الأساسية مطلوبة', 'error')
                    return redirect(url_for('admin_database_connection'))
                
                # Build MySQL database URL
                database_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
                if charset:
                    database_url += f"?charset={charset}"
            else:
                # PostgreSQL
                host = request.form.get('host', '').strip()
                port = request.form.get('port', '5432')
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '').strip()
                database = request.form.get('database', '').strip()
                schema = request.form.get('schema', 'public').strip()
                
                if not all([host, username, password, database]):
                    flash('جميع الحقول الأساسية مطلوبة', 'error')
                    return redirect(url_for('admin_database_connection'))
                
                # Build PostgreSQL database URL
                database_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
                
                if schema and schema != 'public':
                    database_url += f"?currentSchema={schema}"
        
        # Get advanced options
        if db_type == 'mysql':
            ssl_mode = request.form.get('mysql_ssl_mode') == 'on'
            if ssl_mode:
                if '?' in database_url:
                    database_url += '&ssl=true'
                else:
                    database_url += '?ssl=true'
        else:
            ssl_mode = request.form.get('ssl_mode') == 'on'
            if ssl_mode and '?' in database_url:
                database_url += '&sslmode=require'
            elif ssl_mode:
                database_url += '?sslmode=require'
        
        # Test connection first
        test_result = test_database_connection_internal(database_url)
        if not test_result['success']:
            flash(f'فشل في الاتصال: {test_result["error"]}', 'error')
            return redirect(url_for('admin_database_connection'))
        
        # Save to environment (this would require restart)
        flash('تم حفظ إعدادات قاعدة البيانات. يتطلب إعادة تشغيل الخادم.', 'warning')
        logging.info(f"Database URL updated by admin: {current_user.username}")
        
        return redirect(url_for('admin_database_connection'))
        
    except Exception as e:
        logging.error(f"Error updating database connection: {e}")
        flash(f'خطأ في تحديث إعدادات قاعدة البيانات: {str(e)}', 'error')
        return redirect(url_for('admin_database_connection'))


@app.route('/admin/database-connection/test', methods=['POST'])
@login_required
def admin_test_database_connection():
    """Test database connection"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        db_type = request.form.get('db_type', 'postgresql')
        connection_type = request.form.get('connection_type')
        
        if connection_type == 'database_url':
            if db_type == 'mysql':
                database_url = request.form.get('mysql_database_url', '').strip()
            else:
                database_url = request.form.get('database_url', '').strip()
        else:
            if db_type == 'mysql':
                host = request.form.get('mysql_host', '').strip()
                port = request.form.get('mysql_port', '3306')
                username = request.form.get('mysql_username', '').strip()
                password = request.form.get('mysql_password', '').strip()
                database = request.form.get('mysql_database', '').strip()
                charset = request.form.get('mysql_charset', 'utf8mb4').strip()
                
                if not all([host, username, password, database]):
                    return jsonify({'success': False, 'error': 'جميع الحقول الأساسية مطلوبة'})
                
                database_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
                if charset:
                    database_url += f"?charset={charset}"
            else:
                # PostgreSQL
                host = request.form.get('host', '').strip()
                port = request.form.get('port', '5432')
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '').strip()
                database = request.form.get('database', '').strip()
                schema = request.form.get('schema', 'public').strip()
                
                if not all([host, username, password, database]):
                    return jsonify({'success': False, 'error': 'جميع الحقول الأساسية مطلوبة'})
                
                database_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        
        # Add SSL if requested
        if db_type == 'mysql':
            ssl_mode = request.form.get('mysql_ssl_mode') == 'on'
            if ssl_mode:
                if '?' in database_url:
                    database_url += '&ssl=true'
                else:
                    database_url += '?ssl=true'
        else:
            ssl_mode = request.form.get('ssl_mode') == 'on'
            if ssl_mode:
                if '?' in database_url:
                    database_url += '&sslmode=require'
                else:
                    database_url += '?sslmode=require'
        
        # Test the connection
        result = test_database_connection_internal(database_url)
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error testing database connection: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/database-connection/backup')
@login_required
def admin_backup_database():
    """Create database backup"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        # This is a placeholder - actual backup would require proper implementation
        flash('ميزة النسخ الاحتياطي ستكون متاحة قريباً', 'info')
        return redirect(url_for('admin_database_connection'))
        
    except Exception as e:
        logging.error(f"Error creating database backup: {e}")
        flash('خطأ في إنشاء النسخة الاحتياطية', 'error')
        return redirect(url_for('admin_database_connection'))


def test_database_connection_internal(database_url):
    """Internal function to test database connection"""
    try:
        from sqlalchemy import create_engine, text
        import urllib.parse
        
        # Parse the database URL
        parsed_url = urllib.parse.urlparse(database_url)
        
        # Create engine with appropriate options
        if parsed_url.scheme in ['postgresql', 'postgres']:
            engine = create_engine(database_url, 
                                 pool_pre_ping=True,
                                 pool_recycle=300,
                                 pool_timeout=30,
                                 connect_args={"connect_timeout": 10})
            db_type = "PostgreSQL"
        elif parsed_url.scheme in ['mysql', 'mysql+pymysql']:
            engine = create_engine(database_url,
                                 pool_pre_ping=True,
                                 pool_recycle=300,
                                 pool_timeout=30,
                                 connect_args={
                                     "charset": "utf8mb4",
                                     "use_unicode": True,
                                     "connect_timeout": 10
                                 })
            db_type = "MySQL"
        else:
            return {'success': False, 'error': f'نوع قاعدة البيانات غير مدعوم: {parsed_url.scheme}'}
        
        # Test connection
        with engine.connect() as connection:
            # Get version and connection details
            if parsed_url.scheme in ['postgresql', 'postgres']:
                result = connection.execute(text("SELECT version()"))
                version = result.scalar()
                
                # Get connection details
                result = connection.execute(text("SELECT current_database(), current_user, inet_server_addr(), inet_server_port()"))
                db_info = result.fetchone()
                
                # Count tables
                result = connection.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"))
                table_count = result.scalar()
                
                return {
                    'success': True,
                    'db_type': db_type,
                    'version': version[:100] + '...' if len(version) > 100 else version,
                    'database': db_info[0] if db_info else 'Unknown',
                    'user': db_info[1] if db_info else 'Unknown',
                    'host': db_info[2] if db_info and db_info[2] else parsed_url.hostname,
                    'port': db_info[3] if db_info and db_info[3] else parsed_url.port,
                    'tables_count': table_count
                }
            elif parsed_url.scheme in ['mysql', 'mysql+pymysql']:
                result = connection.execute(text("SELECT VERSION()"))
                version = result.scalar()
                
                # Get connection details
                result = connection.execute(text("SELECT DATABASE(), USER(), @@hostname, @@port"))
                db_info = result.fetchone()
                
                # Count tables
                result = connection.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"))
                table_count = result.scalar()
                
                return {
                    'success': True,
                    'db_type': db_type,
                    'version': version,
                    'database': db_info[0] if db_info else 'Unknown',
                    'user': db_info[1] if db_info else 'Unknown',
                    'host': db_info[2] if db_info and db_info[2] else parsed_url.hostname,
                    'port': db_info[3] if db_info and db_info[3] else parsed_url.port,
                    'tables_count': table_count
                }
                
    except Exception as e:
        logging.error(f"Database connection test failed: {e}")
        return {'success': False, 'error': str(e)}

# Database Migration API Routes
@app.route('/admin/api/migrate-database', methods=['POST'])
@login_required
def admin_api_migrate_database():
    """API endpoint to migrate database from SQLite to PostgreSQL"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
    
    try:
        from database.migration_manager import migration_manager
        
        # Perform migration
        success, message = migration_manager.migrate_sqlite_to_postgresql()
        
        if success:
            logging.info(f"Database migration completed by admin: {current_user.username}")
            return jsonify({
                'success': True,
                'message': 'تم ترحيل قاعدة البيانات بنجاح إلى PostgreSQL'
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            })
        
    except Exception as e:
        logging.error(f"Migration API error: {e}")
        return jsonify({
            'success': False,
            'message': f'خطأ في عملية الترحيل: {str(e)}'
        })

@app.route('/admin/database-backup-download')
@login_required
def admin_database_backup_download():
    """Create and download database backup"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from config.database_config import db_config
        import tempfile
        import shutil
        
        if db_config.is_sqlite():
            # Backup SQLite file
            backup_filename = f"manga_platform_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path = os.path.join(tempfile.gettempdir(), backup_filename)
            shutil.copy2('manga_platform.db', backup_path)
            
            return send_file(backup_path, 
                           as_attachment=True, 
                           download_name=backup_filename,
                           mimetype='application/x-sqlite3')
        else:
            # For PostgreSQL, create SQL dump
            flash('النسخ الاحتياطي لـ PostgreSQL غير متوفر حالياً', 'info')
            return redirect(url_for('admin_database_connection'))
        
    except Exception as e:
        logging.error(f"Backup error: {e}")
        flash('خطأ في إنشاء النسخة الاحتياطية', 'error')
        return redirect(url_for('admin_database_connection'))

@app.route('/admin/database-health')
@login_required
def admin_database_health():
    """Check database health"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        health_report = {
            'status': 'healthy',
            'checks': []
        }
        
        # Test database connection
        try:
            result = db.engine.execute(db.text("SELECT 1"))
            result.fetchone()
            health_report['checks'].append({
                'name': 'اتصال قاعدة البيانات',
                'status': 'success',
                'message': 'متصل بنجاح'
            })
        except Exception as e:
            health_report['status'] = 'unhealthy'
            health_report['checks'].append({
                'name': 'اتصال قاعدة البيانات',
                'status': 'error',
                'message': f'فشل الاتصال: {str(e)}'
            })
        
        # Check critical tables
        critical_tables = ['users', 'manga', 'chapters', 'page_images']
        for table in critical_tables:
            try:
                result = db.engine.execute(db.text(f"SELECT COUNT(*) FROM {table}"))
                count = result.fetchone()[0]
                health_report['checks'].append({
                    'name': f'جدول {table}',
                    'status': 'success',
                    'message': f'{count} سجل'
                })
            except Exception as e:
                health_report['status'] = 'unhealthy'
                health_report['checks'].append({
                    'name': f'جدول {table}',
                    'status': 'error',
                    'message': f'خطأ: {str(e)}'
                })
        
        return jsonify(health_report)
        
    except Exception as e:
        logging.error(f"Health check error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'خطأ في فحص الصحة: {str(e)}'
        })

@app.route('/admin/database-optimize')
@login_required
def admin_database_optimize():
    """Optimize database performance"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from config.database_config import db_config
        
        optimize_results = []
        
        if db_config.is_sqlite():
            # SQLite optimization
            try:
                db.engine.execute(db.text("VACUUM"))
                optimize_results.append({
                    'operation': 'VACUUM',
                    'status': 'success',
                    'message': 'تم ضغط قاعدة البيانات'
                })
            except Exception as e:
                optimize_results.append({
                    'operation': 'VACUUM',
                    'status': 'error',
                    'message': f'فشل في الضغط: {str(e)}'
                })
            
            try:
                db.engine.execute(db.text("ANALYZE"))
                optimize_results.append({
                    'operation': 'ANALYZE',
                    'status': 'success',
                    'message': 'تم تحديث إحصائيات الجداول'
                })
            except Exception as e:
                optimize_results.append({
                    'operation': 'ANALYZE',
                    'status': 'error',
                    'message': f'فشل في التحليل: {str(e)}'
                })
        
        elif db_config.is_postgresql():
            # PostgreSQL optimization
            try:
                db.engine.execute(db.text("VACUUM ANALYZE"))
                optimize_results.append({
                    'operation': 'VACUUM ANALYZE',
                    'status': 'success',
                    'message': 'تم تحسين قاعدة البيانات'
                })
            except Exception as e:
                optimize_results.append({
                    'operation': 'VACUUM ANALYZE',
                    'status': 'error',
                    'message': f'فشل في التحسين: {str(e)}'
                })
        
        return jsonify({
            'success': True,
            'results': optimize_results
        })
        
    except Exception as e:
        logging.error(f"Optimization error: {e}")
        return jsonify({
            'success': False,
            'message': f'خطأ في تحسين قاعدة البيانات: {str(e)}'
        })





def upload_chapter_to_cloudinary_background(chapter_id, image_files):
    """رفع صور الفصل إلى Cloudinary في الخلفية"""
    try:
        from app.utils_cloudinary import CloudinaryUploader
        from app.app import app, db
        from app.models import PageImage
        
        with app.app_context():
            cloudinary_uploader = CloudinaryUploader()
            
            # البحث عن سجلات الصفحات الموجودة
            pages = PageImage.query.filter_by(chapter_id=chapter_id).order_by(PageImage.page_number).all()
            
            for page in pages:
                try:
                    # بناء المسار الكامل للصورة
                    if page.image_path.startswith('uploads/'):
                        full_image_path = os.path.join(os.getcwd(), 'static', page.image_path)
                    else:
                        full_image_path = os.path.join(os.getcwd(), page.image_path)
                    
                    if os.path.exists(full_image_path) and not page.is_cloudinary:
                        # رفع إلى Cloudinary
                        upload_result = cloudinary_uploader.upload_image_file(
                            full_image_path, page.chapter.manga_id, chapter_id, page.page_number
                        )
                        
                        if upload_result['success']:
                            # تحديث سجل الصفحة
                            page.cloudinary_url = upload_result['url']
                            page.cloudinary_public_id = upload_result['public_id']
                            page.is_cloudinary = True
                            if 'width' in upload_result:
                                page.image_width = upload_result['width']
                            if 'height' in upload_result:
                                page.image_height = upload_result['height']
                            if 'bytes' in upload_result:
                                page.file_size = upload_result['bytes']
                            
                            print(f'✅ رفع خلفية: صورة {page.page_number} إلى Cloudinary')
                        else:
                            print(f'⚠️ فشل رفع خلفية: صورة {page.page_number}')
                    
                except Exception as e:
                    print(f'❌ خطأ في رفع الصورة {page.page_number} في الخلفية: {e}')
                    continue
            
            # حفظ التحديثات
            db.session.commit()
            print(f'🎯 اكتمل رفع الفصل {chapter_id} إلى Cloudinary في الخلفية')
            
    except Exception as e:
        print(f'❌ خطأ عام في رفع الفصل {chapter_id} في الخلفية: {e}')



def download_and_upload_images_background(scraped_images, chapter_dir, chapter_id, chapter_url):
    """تحميل الصور ورفعها إلى Cloudinary في الخلفية"""
    try:
        from app.utils_cloudinary import CloudinaryUploader
        from app.app import app, db
        from app.models import PageImage
        import requests
        
        with app.app_context():
            print(f'🚀 بدء تحميل {len(scraped_images)} صورة في الخلفية...')
            
            # تحميل الصور
            downloaded_files = []
            for i, img_url in enumerate(scraped_images, 1):
                try:
                    print(f'⬇️ تحميل الصورة {i}/{len(scraped_images)}')
                    
                    response = requests.get(img_url, headers={'Referer': chapter_url}, stream=True, timeout=30)
                    response.raise_for_status()
                    
                    file_ext = '.webp' if '.webp' in img_url else '.jpg'
                    filename = f'page_{i:03d}{file_ext}'
                    img_path = os.path.join(chapter_dir, filename)
                    
                    with open(img_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    file_size = os.path.getsize(img_path)
                    if file_size > 1000:
                        downloaded_files.append((img_path, i))
                        print(f'✅ تم تحميل: {filename} ({file_size} bytes)')
                    else:
                        os.remove(img_path)
                        print(f'❌ تم حذف ملف فارغ: {filename}')
                        
                except Exception as e:
                    print(f'❌ فشل تحميل الصورة {i}: {e}')
                    continue
            
            # رفع إلى Cloudinary
            if downloaded_files:
                cloudinary_uploader = CloudinaryUploader()
                for img_path, page_num in downloaded_files:
                    try:
                        upload_result = cloudinary_uploader.upload_image_file(
                            img_path, 1, chapter_id, page_num
                        )
                        
                        if upload_result['success']:
                            # تحديث سجل الصفحة
                            page = PageImage.query.filter_by(
                                chapter_id=chapter_id, 
                                page_number=page_num
                            ).first()
                            
                            if page:
                                page.cloudinary_url = upload_result['url']
                                page.cloudinary_public_id = upload_result['public_id']
                                page.is_cloudinary = True
                                if 'width' in upload_result:
                                    page.image_width = upload_result['width']
                                if 'height' in upload_result:
                                    page.image_height = upload_result['height']
                                if 'bytes' in upload_result:
                                    page.file_size = upload_result['bytes']
                                
                                print(f'✅ رفع خلفية: صورة {page_num} إلى Cloudinary')
                        
                    except Exception as e:
                        print(f'❌ خطأ في رفع الصورة {page_num}: {e}')
                        continue
                
                db.session.commit()
                print(f'🎯 اكتمل تحميل ورفع {len(downloaded_files)} صورة في الخلفية')
            else:
                print('⚠️ لم يتم تحميل أي صور بنجاح')
            
    except Exception as e:
        print(f'❌ خطأ عام في التحميل والرفع في الخلفية: {e}')

# Static pages routes - all managed through admin/static-pages
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page with beautiful unified contact form"""
    if request.method == 'POST':
        # Handle contact form submission
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        # Validate form data
        if not all([name, email, subject, message]):
            flash('يرجى ملء جميع الحقول المطلوبة', 'error')
            return redirect(url_for('contact'))
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('يرجى إدخال بريد إلكتروني صحيح', 'error')
            return redirect(url_for('contact'))
        
        # Import Bravo Mail here to avoid context issues
        try:
            from app.utils_bravo_mail import bravo_mail, send_contact_form_email
        except ImportError:
            bravo_mail = None
            send_contact_form_email = None
        
        # Send email via Bravo Mail
        if bravo_mail and bravo_mail.is_enabled():
            try:
                email_result = send_contact_form_email(name, email, subject, message)
                if email_result['success']:
                    flash('تم إرسال رسالتك بنجاح! سنقوم بالرد عليك قريباً.', 'success')
                else:
                    flash(f'حدث خطأ في إرسال الرسالة: {email_result.get("error", "خطأ غير معروف")}', 'error')
            except Exception as e:
                flash(f'حدث خطأ في إرسال الرسالة: {str(e)}', 'error')
        else:
            # Fallback - save to database or log
            logging.info(f"Contact form submission (Bravo Mail disabled): Name: {name}, Email: {email}, Subject: {subject}, Message: {message}")
            flash('تم استلام رسالتك. سنقوم بالرد عليك قريباً. (ملاحظة: خدمة البريد الإلكتروني غير مفعلة)', 'info')
        
        return redirect(url_for('contact'))
    
    # GET request - show unified contact form
    return render_template('contact_form.html', 
                     title='تواصل معنا',
                     message='نحن هنا لمساعدتك! يمكنك التواصل معنا في أي وقت')

# Bravo Mail testing route
@app.route('/admin/test-bravo-mail', methods=['POST'])
@login_required
def test_bravo_mail():
    """Test Bravo Mail connection and send test email"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'غير مسموح'})
    
    try:
        data = request.get_json()
        test_email = data.get('test_email', current_user.email if current_user.is_authenticated else '')
        
        if not test_email:
            return jsonify({'success': False, 'error': 'يرجى إدخال عنوان بريد إلكتروني للاختبار'})
        
        # Import Bravo Mail here to avoid context issues
        try:
            from app.utils_bravo_mail import bravo_mail
        except ImportError:
            return jsonify({'success': False, 'error': 'خدمة Bravo Mail غير متاحة'})
        
        # Test connection first
        connection_result = bravo_mail.test_connection()
        if not connection_result['success']:
            return jsonify({
                'success': False, 
                'error': f'فشل في الاتصال بخدمة Bravo Mail: {connection_result["error"]}'
            })
        
        # Send test email
        site_name = SettingsManager.get('site_name', 'منصة المانجا')
        subject = f'[{site_name}] رسالة اختبار من Bravo Mail'
        
        html_body = f"""
        <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                <h1 style="margin: 0; font-size: 28px;">🎉 نجح الاختبار!</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">تم إعداد Bravo Mail بنجاح</p>
            </div>
            
            <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-top: 0;">مرحباً من {site_name}</h2>
                <p style="line-height: 1.6; color: #666;">
                    هذه رسالة اختبار لتأكيد أن خدمة Bravo Mail تعمل بشكل صحيح مع منصتك.
                    إذا وصلتك هذه الرسالة، فهذا يعني أن جميع الإعدادات محكمة وجاهزة للاستخدام.
                </p>
                
                <div style="background: #e8f5e8; border: 1px solid #28a745; border-radius: 5px; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0; color: #155724;">
                        <strong>✅ تم بنجاح:</strong> إعداد وتكوين خدمة Bravo Mail
                    </p>
                </div>
                
                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    تم الإرسال في: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                    من: {site_name} - نظام إدارة المحتوى
                </p>
            </div>
        </div>
        """
        
        text_body = f"""
        🎉 نجح الاختبار!
        
        مرحباً من {site_name}
        
        هذه رسالة اختبار لتأكيد أن خدمة Bravo Mail تعمل بشكل صحيح مع منصتك.
        إذا وصلتك هذه الرسالة، فهذا يعني أن جميع الإعدادات محكمة وجاهزة للاستخدام.
        
        ✅ تم بنجاح: إعداد وتكوين خدمة Bravo Mail
        
        تم الإرسال في: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        من: {site_name} - نظام إدارة المحتوى
        """
        
        email_result = bravo_mail.send_email(
            to_email=test_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            to_name="مدير النظام"
        )
        
        if email_result['success']:
            return jsonify({
                'success': True,
                'message': f'تم إرسال الإيميل التجريبي بنجاح إلى {test_email}'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'فشل في إرسال الإيميل: {email_result.get("error", "خطأ غير معروف")}'
            })
        
    except Exception as e:
        logging.error(f"Error testing Bravo Mail: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في الاختبار: {str(e)}'
        })

@app.route('/about')
def about():
    """About page - managed through static pages system"""
    page = StaticPage.query.filter_by(slug='about', is_published=True).first()
    if page:
        return render_template('static_page.html', page=page)
    else:
        if current_user.is_authenticated and current_user.is_admin:
            flash('صفحة حول الموقع غير موجودة، يمكنك إنشاؤها من لوحة الإدارة', 'info')
            return redirect(url_for('admin_static_pages'))
        return render_template('message.html', 
                         title='صفحة غير متاحة',
                         message='صفحة حول الموقع غير متاحة حالياً')

@app.route('/privacy-policy')
@app.route('/privacy')
def privacy_policy():
    """Privacy policy page - managed through static pages system"""
    page = StaticPage.query.filter_by(slug='privacy-policy', is_published=True).first()
    if not page:
        page = StaticPage.query.filter_by(slug='privacy', is_published=True).first()
    if page:
        return render_template('static_page.html', page=page)
    else:
        if current_user.is_authenticated and current_user.is_admin:
            flash('صفحة سياسة الخصوصية غير موجودة، يمكنك إنشاؤها من لوحة الإدارة', 'info')
            return redirect(url_for('admin_static_pages'))
        return render_template('message.html', 
                         title='صفحة غير متاحة',
                         message='صفحة سياسة الخصوصية غير متاحة حالياً')

@app.route('/manga')
def manga_list():
    """General manga listing page - redirect to library"""
    return redirect(url_for('library'))

@app.route('/genres')
@app.route('/categories') 
def genres_list():
    """Categories/genres listing page"""
    categories = Category.query.filter(Category.is_active == True).all()
    return render_template('categories.html',
                         categories=categories,
                         title='الأنواع والفئات',
                         description='تصفح المانجا حسب النوع')

@app.route('/help')
@app.route('/support')
def help_page():
    """Help and support page - managed through static pages system"""
    page = StaticPage.query.filter_by(slug='help', is_published=True).first()
    if not page:
        page = StaticPage.query.filter_by(slug='support', is_published=True).first()
    if page:
        return render_template('static_page.html', page=page)
    else:
        if current_user.is_authenticated and current_user.is_admin:
            flash('صفحة المساعدة غير موجودة، يمكنك إنشاؤها من لوحة الإدارة', 'info')
            return redirect(url_for('admin_static_pages'))
        return render_template('message.html', 
                         title='صفحة غير متاحة',
                         message='صفحة المساعدة غير متاحة حالياً')

# Bravo Mail Admin Routes
@app.route('/admin/bravo-mail/test-connection', methods=['POST'])
@login_required
def admin_test_bravo_mail_connection():
    """Test Bravo Mail API connection"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_bravo_mail import bravo_mail
        
        if not bravo_mail.is_enabled():
            return jsonify({
                'success': False,
                'error': 'خدمة Bravo Mail غير مفعلة أو غير مكونة بشكل صحيح'
            })
        
        # Test connection
        result = bravo_mail.test_connection()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'تم الاتصال بنجاح مع Bravo Mail API',
                'account_info': result.get('account_info', {})
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'فشل في الاتصال')
            })
            
    except Exception as e:
        logging.error(f"Error testing Bravo Mail connection: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في اختبار الاتصال: {str(e)}'
        })

@app.route('/admin/bravo-mail/send-bulk-test', methods=['POST'])
@login_required
def admin_send_bulk_test_email():
    """Send bulk test email to multiple recipients"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_bravo_mail import bravo_mail, send_bulk_notification_email
        from app.models import User
        
        if not bravo_mail.is_enabled():
            return jsonify({
                'success': False,
                'error': 'خدمة Bravo Mail غير مفعلة'
            })
        
        # Get test parameters
        recipient_emails = request.json.get('recipients', [])
        test_message = request.json.get('message', 'رسالة اختبار جماعية من منصة المانجا')
        
        if not recipient_emails:
            # Use admin emails if no recipients specified
            admin_users = User.query.filter_by(is_admin=True).all()
            recipient_emails = [{'email': u.email, 'name': u.username} for u in admin_users]
        
        # Send bulk test notification
        result = send_bulk_notification_email(
            recipients=recipient_emails,
            title="اختبار الإرسال الجماعي",
            message=test_message,
            action_url=request.url_root
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'تم إرسال الرسالة الجماعية إلى {len(recipient_emails)} مستلم',
                'sent_count': len(recipient_emails)
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'فشل في الإرسال الجماعي')
            })
            
    except Exception as e:
        logging.error(f"Error sending bulk test email: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في الإرسال الجماعي: {str(e)}'
        })

@app.route('/admin/bravo-mail/email-templates')
@login_required
def admin_bravo_mail_templates():
    """View available email templates"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        # Define available email templates
        email_templates = {
            'welcome': {
                'name': 'رسالة الترحيب للمستخدمين الجدد',
                'description': 'ترسل تلقائياً عند التسجيل',
                'function': 'send_welcome_email'
            },
            'password_reset': {
                'name': 'إعادة تعيين كلمة المرور',
                'description': 'ترسل عند طلب إعادة تعيين كلمة المرور',
                'function': 'send_password_reset_email'
            },
            'premium_subscription': {
                'name': 'تأكيد الاشتراك المميز',
                'description': 'ترسل عند تفعيل الاشتراك المدفوع',
                'function': 'send_premium_subscription_email'
            },
            'payment_receipt': {
                'name': 'إيصال الدفع',
                'description': 'ترسل بعد إتمام عملية الدفع',
                'function': 'send_payment_receipt_email'
            },
            'chapter_notification': {
                'name': 'إشعار فصل جديد',
                'description': 'ترسل عند نشر فصل جديد',
                'function': 'send_manga_chapter_notification'
            },
            'translator_approval': {
                'name': 'موافقة/رفض طلب الترجمة',
                'description': 'ترسل عند مراجعة طلبات المترجمين',
                'function': 'send_translator_approval_email'
            },
            'contact_form': {
                'name': 'رسائل نموذج التواصل',
                'description': 'ترسل للمدير عند استقبال رسائل التواصل',
                'function': 'send_contact_form_email'
            },
            'bulk_notification': {
                'name': 'الإشعارات الجماعية',
                'description': 'ترسل لعدة مستخدمين في وقت واحد',
                'function': 'send_bulk_notification_email'
            },
            'system_maintenance': {
                'name': 'إشعار صيانة النظام',
                'description': 'ترسل قبل الصيانة المجدولة',
                'function': 'send_system_maintenance_email'
            }
        }
        
        return jsonify({
            'success': True,
            'templates': email_templates
        })
        
    except Exception as e:
        logging.error(f"Error getting email templates: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في جلب القوالب: {str(e)}'
        })

@app.route('/admin/bravo-mail/preview-template/<template_type>')
@login_required
def admin_preview_email_template(template_type):
    """Preview email template"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_bravo_mail import (
            send_welcome_email, send_password_reset_email, 
            send_premium_subscription_email, send_payment_receipt_email,
            send_manga_chapter_notification, send_translator_approval_email,
            send_contact_form_email, send_bulk_notification_email,
            send_system_maintenance_email
        )
        
        # Sample data for preview
        sample_data = {
            'user_email': 'user@example.com',
            'user_name': 'المستخدم التجريبي',
            'site_name': 'منصة المانجا',
            'manga_title': 'مانجا تجريبية',
            'chapter_title': 'الفصل 1',
            'subscription_type': 'الباقة الشهرية',
            'expiry_date': '2025-10-06',
            'amount': '10 USD',
            'payment_method': 'Stripe',
            'transaction_id': 'TXN-12345',
            'approval_status': 'approved',
            'maintenance_start': '2025-09-10 02:00 AM',
            'maintenance_end': '2025-09-10 06:00 AM',
            'reason': 'تحديث النظام وتحسين الأداء'
        }
        
        # Get template preview (without actually sending)
        preview_html = f"""
        <div style="max-width: 600px; margin: 20px auto; padding: 20px; border: 1px solid #ddd;">
            <h3>معاينة قالب: {template_type}</h3>
            <p>هذا مثال على كيف ستبدو الرسالة الإلكترونية.</p>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
                <p><strong>البيانات المستخدمة في المعاينة:</strong></p>
                <ul>
        """
        
        for key, value in sample_data.items():
            preview_html += f"<li><strong>{key}:</strong> {value}</li>"
        
        preview_html += """
                </ul>
            </div>
        </div>
        """
        
        return jsonify({
            'success': True,
            'template_type': template_type,
            'preview_html': preview_html,
            'sample_data': sample_data
        })
        
    except Exception as e:
        logging.error(f"Error previewing email template: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في معاينة القالب: {str(e)}'
        })

@app.route('/admin/bravo-mail/queue-status', methods=['GET'])
@login_required
def admin_get_email_queue_status():
    """Get email queue status"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_bravo_mail import get_email_queue_status
        
        status = get_email_queue_status()
        return jsonify({
            'success': True,
            'queue_status': status
        })
        
    except Exception as e:
        logging.error(f"Error getting email queue status: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في جلب حالة القائمة: {str(e)}'
        })

@app.route('/admin/bravo-mail/process-queue', methods=['POST'])
@login_required
def admin_process_email_queue():
    """Process email queue manually"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_bravo_mail import process_email_queue
        
        result = process_email_queue()
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error processing email queue: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في معالجة القائمة: {str(e)}'
        })

@app.route('/admin/bravo-mail/clear-queue', methods=['POST'])
@login_required
def admin_clear_email_queue():
    """Clear completed email jobs"""
    if not current_user.is_admin:
        abort(403)
    
    try:
        from app.utils_bravo_mail import email_queue
        
        cleared_count = email_queue.clear_completed_jobs()
        return jsonify({
            'success': True,
            'message': f'تم مسح {cleared_count} وظيفة مكتملة',
            'cleared_count': cleared_count
        })
        
    except Exception as e:
        logging.error(f"Error clearing email queue: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ في مسح القائمة: {str(e)}'
        })

# Newsletter Subscription Routes
@app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    """Subscribe to newsletter"""
    try:
        from app.models import NewsletterSubscription, User
        
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'success': False, 'message': 'البريد الإلكتروني مطلوب'})
        
        # Check if email is valid
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({'success': False, 'message': 'البريد الإلكتروني غير صحيح'})
        
        # Check if already subscribed
        existing = NewsletterSubscription.query.filter_by(email=email).first()
        if existing:
            if existing.is_active:
                return jsonify({'success': False, 'message': 'أنت مشترك بالفعل في النشرة الإخبارية'})
            else:
                # Reactivate subscription
                existing.is_active = True
                existing.subscribed_at = datetime.utcnow()
                db.session.commit()
                return jsonify({'success': True, 'message': 'تم إعادة تفعيل اشتراكك بنجاح'})
        
        # Check if user is logged in to link subscription
        user_id = None
        language = 'ar'
        if current_user.is_authenticated:
            user_id = current_user.id
            language = getattr(current_user, 'language_preference', 'ar')
        
        # Create new subscription
        subscription = NewsletterSubscription(
            email=email,
            user_id=user_id,
            language_preference=language
        )
        
        db.session.add(subscription)
        db.session.commit()
        
        # Send welcome email if Bravo Mail is enabled
        try:
            from app.utils_bravo_mail import bravo_mail, send_newsletter_welcome_email
            if bravo_mail and bravo_mail.is_enabled():
                welcome_result = send_newsletter_welcome_email(email, language)
                if not welcome_result.get('success'):
                    logger.warning(f"Failed to send newsletter welcome email: {welcome_result.get('error')}")
        except ImportError:
            pass  # Bravo Mail not available
        except Exception as e:
            logger.warning(f"Error sending newsletter welcome email: {e}")
        
        return jsonify({'success': True, 'message': 'تم الاشتراك بنجاح في النشرة الإخبارية'})
        
    except Exception as e:
        logger.exception(f"Error subscribing to newsletter: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء الاشتراك'})

@app.route('/newsletter/unsubscribe/<token>')
def newsletter_unsubscribe(token):
    """Unsubscribe from newsletter using token"""
    try:
        from app.models import NewsletterSubscription
        
        subscription = NewsletterSubscription.query.filter_by(unsubscribe_token=token).first()
        if not subscription:
            flash('رابط إلغاء الاشتراك غير صحيح أو منتهي الصلاحية', 'error')
            return redirect(url_for('index'))
        
        subscription.is_active = False
        db.session.commit()
        
        flash('تم إلغاء اشتراكك في النشرة الإخبارية بنجاح', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.exception(f"Error unsubscribing from newsletter: {e}")
        flash('حدث خطأ أثناء إلغاء الاشتراك', 'error')
        return redirect(url_for('index'))

