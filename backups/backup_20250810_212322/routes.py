import os
import zipfile
import tempfile
import shutil
import logging
import time
import requests
import json
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, abort, session
from sqlalchemy import func
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from app import app, db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
from models import (User, Manga, Chapter, PageImage, Category, Bookmark, ReadingProgress, 
                    Comment, CommentReaction, MangaReaction, Rating, manga_category, PublisherRequest, TranslationRequest, 
                    Notification, Announcement, Advertisement, Subscription, MangaAnalytics, Translation, Report, PaymentPlan,
                    AutoScrapingSource, ScrapingLog, ScrapingQueue, ScrapingSettings,
                    PaymentGateway, Payment, UserSubscription)
from utils import optimize_image, allowed_file

# دالة لحفظ الصورة الشخصية
def save_profile_picture(file):
    """Save profile picture and return the URL"""
    if file and allowed_file(file.filename):
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
from utils_payment import (convert_currency, get_currency_symbols, format_currency, 
                          validate_payment_amount, get_processing_fee, get_estimated_processing_time)
from scraper_utils import extract_zip_chapter
# Import sitemap functionality
import sitemap
# استيراد المرافق الضرورية
try:
    from simple_manga_scraper import scrape_olympustaff_simple
    from utils_settings import SettingsManager
    from utils_seo import generate_meta_tags, generate_canonical_url, generate_breadcrumbs
except ImportError:
    # Define fallback functions if imports fail
    def scrape_olympustaff_simple(chapter_url, output_folder):
        return {'success': False, 'error': 'مكتبة simple_manga_scraper غير متوفرة', 'downloaded_files': []}
    
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
        _default_settings = {}
    
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
    # Get latest manga
    latest_manga = Manga.query.order_by(Manga.created_at.desc()).limit(12).all()
    
    # Get popular manga (by views)
    popular_manga = Manga.query.order_by(Manga.views.desc()).limit(12).all()
    
    # Get categories
    categories = Category.query.all()
    
    # Generate SEO meta tags for homepage
    try:
        from utils_seo import generate_meta_tags
        meta_tags = generate_meta_tags()
    except ImportError:
        meta_tags = {}
    
    return render_template('index.html', 
                         latest_manga=latest_manga, 
                         popular_manga=popular_manga,
                         categories=categories,
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
    
    # Generate SEO meta tags for manga page
    try:
        from utils_seo import generate_meta_tags
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
        from utils_seo import generate_meta_tags, generate_breadcrumbs
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
        flash('هذا الفصل لا يحتوي على صفحات متاحة.', 'warning')
        if manga.slug:
            return redirect(url_for('manga_detail', slug=manga.slug))
        else:
            return redirect(url_for('manga_detail_by_id', manga_id=manga.id))
    
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
        return redirect(request.referrer or url_for('index'))
    
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
    return redirect(request.referrer or url_for('index'))

@app.route('/manga/<int:manga_id>/comment', methods=['POST'])
@login_required
def add_manga_comment_form(manga_id):
    """Add comment to manga via form submission"""
    manga = Manga.query.get_or_404(manga_id)
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('المحتوى مطلوب', 'error')
        return redirect(request.referrer or url_for('manga_detail', manga_slug=manga.slug))
    
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
        import logging
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
    
    # Delete associated files
    if manga.cover_image and os.path.exists(manga.cover_image):
        os.remove(manga.cover_image)
    
    # Delete chapter images
    for chapter in manga.chapters:
        for page in chapter.page_images:
            if os.path.exists(page.image_path):
                os.remove(page.image_path)
    
    db.session.delete(manga)
    db.session.commit()
    
    flash('Manga deleted successfully!', 'success')
    return redirect(url_for('admin_manage'))

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
            return redirect(request.url)

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
        chapter_number = float(request.form.get('chapter_number', 1))
        is_locked = bool(request.form.get('is_locked'))
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
                return redirect(request.url)
        elif upload_method == 'zip':
            zip_file = request.files.get('chapter_zip')
            if not title or not zip_file:
                flash('العنوان وملف ZIP مطلوبان', 'error')
                return redirect(request.url)
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
                return redirect(request.url)
            
            # التحقق من وجود بيانات الكشط المختبرة
            scraping_tested = request.form.get('scraping_tested', 'false')
            scraped_images_json = request.form.get('scraped_images', '')
            has_tested_data = scraping_tested == 'true' and scraped_images_json
            
            if not has_scraped_images and not has_tested_data and (not source_website or not chapter_url):
                flash('الموقع المصدر ورابط الفصل مطلوبان أو يجب كشط الصور أولاً', 'error')
                return redirect(request.url)
        
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
            from utils_manga_category import set_manga_categories
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
                            return redirect(request.url)
                        
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
                        return redirect(request.url)
                
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
                
                # Categories were already handled during manga creation
                
                flash('تم رفع المانجا بنجاح!', 'success')
                return redirect(url_for('manga_detail', manga_id=manga.id))
                
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
    publisher = User.query.filter_by(id=publisher_id, is_publisher=True, is_active=True).first_or_404()
    
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

# API Routes
@app.route('/api/manga')
def api_manga_list():
    """API endpoint for manga list"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    
    manga_query = Manga.query.filter_by(is_published=True)
    manga_pagination = manga_query.paginate(page=page, per_page=per_page, error_out=False)
    
    manga_list = []
    for manga in manga_pagination.items:
        manga_list.append({
            'id': manga.id,
            'title': manga.title,
            'title_ar': manga.title_ar,
            'author': manga.author,
            'cover_image': manga.cover_image,
            'status': manga.status,
            'type': manga.type,
            'language': manga.language,
            'views': manga.views,
            'average_rating': manga.average_rating,
            'total_chapters': manga.total_chapters
        })
    
    return jsonify({
        'manga': manga_list,
        'pagination': {
            'page': manga_pagination.page,
            'pages': manga_pagination.pages,
            'total': manga_pagination.total
        }
    })

@app.route('/api/manga/<int:manga_id>')
def api_manga_detail(manga_id):
    """API endpoint for manga details"""
    manga = Manga.query.get_or_404(manga_id)
    
    chapters = []
    for chapter in manga.chapters.all():
        chapters.append({
            'id': chapter.id,
            'chapter_number': chapter.chapter_number,
            'title': chapter.title,
            'pages': chapter.pages
        })
    
    return jsonify({
        'id': manga.id,
        'title': manga.title,
        'description': manga.description,
        'author': manga.author,
        'cover_image': manga.cover_image,
        'status': manga.status,
        'type': manga.type,
        'views': manga.views,
        'average_rating': manga.average_rating,
        'chapters': chapters
    })

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
        if request.is_json and data:
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
    
    user.is_translator = not user.is_translator
    db.session.commit()
    
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
        
        # In production, send this via email instead of flash message
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
        user.is_admin = bool(request.form.get('is_admin'))
        user.is_publisher = bool(request.form.get('is_publisher'))
        user.is_translator = bool(request.form.get('is_translator'))
        user.language_preference = request.form.get('language_preference', 'ar')
        user.bio = request.form.get('bio', '').strip()
        user.country = request.form.get('country', '').strip()
        user.avatar_url = avatar_url or '/static/img/default-avatar.svg'
        user.created_at = datetime.utcnow()
        user.last_seen = datetime.utcnow()
        
        db.session.add(user)
        db.session.commit()
        
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
    
    from utils_settings import SettingsManager
    
    # Initialize default settings if not exists
    SettingsManager.initialize_defaults()
    
    if request.method == 'POST':
        try:
            # Handle different form actions
            action = request.form.get('action', 'save_settings')
            
            if action == 'save_settings':
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
                
                flash(f'تم تحديث {settings_updated} إعداد بنجاح', 'success')
                
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
            import logging
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
    from models import User, Manga, Chapter, Comment, Rating
    db_stats = {
        'total_users': User.query.count(),
        'total_manga': Manga.query.count(),
        'total_chapters': Chapter.query.count(),
        'total_comments': Comment.query.count(),
        'total_ratings': Rating.query.count(),
        'publishers': User.query.filter_by(is_publisher=True).count(),
        'admins': User.query.filter_by(is_admin=True).count(),
    }
    
    return render_template('admin/settings.html', 
                         settings=current_settings,
                         all_settings=all_settings,
                         system_info=system_info,
                         db_stats=db_stats,
                         default_settings=SettingsManager._default_settings)

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
        is_active = bool(request.form.get('is_active'))
        is_sandbox = bool(request.form.get('is_sandbox'))
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
        gateway.is_active = bool(request.form.get('is_active'))
        gateway.is_sandbox = bool(request.form.get('is_sandbox'))
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
    
    return redirect(url_for('admin_payment_gateways'))

@app.route('/admin/payment-plans')
@login_required
def admin_payment_plans():
    """Manage payment plans"""
    if not current_user.is_admin:
        abort(403)
    
    plans = PaymentPlan.query.order_by(PaymentPlan.price.asc()).all()
    return render_template('admin/payment_plans.html', plans=plans)

@app.route('/admin/payment-plans/add', methods=['GET', 'POST'])
@login_required
def admin_add_payment_plan():
    """Add new payment plan"""
    if not current_user.is_admin:
        abort(403)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_ar = request.form.get('name_ar', '').strip()
        price = float(request.form.get('price', 0))
        duration_months = int(request.form.get('duration_months', 1))
        is_active = bool(request.form.get('is_active'))
        
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
        plan.price = float(request.form.get('price', 0))
        plan.duration_months = int(request.form.get('duration_months', 1))
        plan.is_active = bool(request.form.get('is_active'))
        
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
            if 'payment_record' in locals() and payment_record:
                payment_record.status = 'failed'
                db.session.commit()
        except:
            pass
        flash('حدث خطأ في إنشاء الدفع، يرجى المحاولة مرة أخرى', 'error')
        print(f"Stripe error: {e}")
        return redirect(url_for('premium_plans'))

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
    """Handle PayMob payment integration"""
    try:
        # PayMob integration would go here
        # For now, redirect to external payment page simulation
        payment_record.status = 'pending'
        payment_record.gateway_payment_id = f"PM-{payment_record.id}-{int(time.time())}"
        db.session.commit()
        
        # In real implementation, create PayMob payment intent and redirect
        external_url = f"https://accept.paymob.com/payment?amount={payment_record.amount}&reference={payment_record.gateway_payment_id}"
        return redirect(external_url)
        
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
    """Create PayMob payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'USD'
    payment_record.status = 'pending'
    payment_record.gateway_payment_id = f"PM-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    
    return render_template('premium/paymob_checkout.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway)

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
    """Create Fawry payment integration"""
    payment_record = Payment()
    payment_record.user_id = current_user.id
    payment_record.plan_id = plan.id
    payment_record.gateway_id = gateway.id
    payment_record.amount = plan.price
    payment_record.currency = 'EGP'  # Fawry uses EGP
    payment_record.status = 'pending_payment'
    payment_record.gateway_payment_id = f"FW-{current_user.id}-{int(time.time())}"
    
    db.session.add(payment_record)
    db.session.commit()
    
    session['payment_record_id'] = payment_record.id
    fawry_code = f"FW{payment_record.id:06d}"
    
    return render_template('premium/fawry_instructions.html', 
                         payment=payment_record, 
                         plan=plan,
                         gateway=gateway,
                         fawry_code=fawry_code)

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
        chapter_number = float(request.form.get('chapter_number', 1))
        is_locked = bool(request.form.get('is_locked'))
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
                        return redirect(request.url)
                    
                    for i, image_file in enumerate(chapter_files, 1):
                        if image_file and image_file.filename:
                            from werkzeug.utils import secure_filename
                            filename = secure_filename(f"page_{i:03d}_{image_file.filename}")
                            image_path = os.path.join(chapter_dir, filename)
                            image_file.save(image_path)
                            image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")

                elif upload_method == 'zip':
                    # ZIP file upload
                    zip_file = request.files.get('chapter_zip')
                    if not zip_file or not zip_file.filename:
                        flash('ملف ZIP مطلوب', 'error')
                        db.session.rollback()
                        return redirect(request.url)
                    
                    # التحقق من نوع الملف
                    allowed_extensions = ['zip', 'cbz', 'rar']
                    file_extension = zip_file.filename.lower().split('.')[-1]
                    if file_extension not in allowed_extensions:
                        flash('نوع الملف غير مدعوم. يُرجى استخدام ZIP, CBZ, أو RAR', 'error')
                        db.session.rollback()
                        return redirect(request.url)
                    
                    # حفظ الملف المضغوط مؤقتاً
                    import tempfile
                    import zipfile
                    from PIL import Image
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_file:
                        zip_file.save(temp_file.name)
                        
                        try:
                            # فتح الملف المضغوط
                            if file_extension in ['zip', 'cbz']:
                                archive = zipfile.ZipFile(temp_file.name, 'r')
                            else:
                                flash('ملفات RAR غير مدعومة حالياً', 'error')
                                os.unlink(temp_file.name)
                                db.session.rollback()
                                return redirect(request.url)
                            
                            # الحصول على قائمة الملفات وترتيبها
                            file_list = archive.namelist()
                            image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
                            
                            # فلترة الملفات للحصول على الصور فقط
                            image_files_in_archive = []
                            for file_name in file_list:
                                if any(file_name.lower().endswith(ext) for ext in image_extensions):
                                    image_files_in_archive.append(file_name)
                            
                            if not image_files_in_archive:
                                flash('لم يتم العثور على صور في الملف المضغوط', 'error')
                                archive.close()
                                os.unlink(temp_file.name)
                                db.session.rollback()
                                return redirect(request.url)
                            
                            # ترتيب الصور حسب الاسم
                            image_files_in_archive.sort()
                            
                            # استخراج وحفظ الصور
                            for i, image_name in enumerate(image_files_in_archive, 1):
                                try:
                                    # استخراج الصورة
                                    image_data = archive.read(image_name)
                                    
                                    # تحديد امتداد الملف
                                    original_ext = os.path.splitext(image_name)[1].lower()
                                    if not original_ext:
                                        original_ext = '.jpg'
                                    
                                    # إنشاء اسم ملف جديد
                                    new_filename = f"page_{i:03d}{original_ext}"
                                    image_path = os.path.join(chapter_dir, new_filename)
                                    
                                    # حفظ الصورة
                                    with open(image_path, 'wb') as img_file:
                                        img_file.write(image_data)
                                    
                                    # التحقق من أن الملف صورة صالحة وتحسينها
                                    try:
                                        with Image.open(image_path) as img:
                                            # تحويل إلى RGB إذا كان ضرورياً
                                            if img.mode in ['RGBA', 'P']:
                                                img = img.convert('RGB')
                                            
                                            # ضغط الصورة إذا كانت كبيرة
                                            max_width = 1200
                                            if img.width > max_width:
                                                ratio = max_width / img.width
                                                new_height = int(img.height * ratio)
                                                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                                            
                                            # حفظ الصورة المحسنة
                                            img.save(image_path, 'JPEG', quality=85, optimize=True)
                                    except Exception as img_error:
                                        print(f"خطأ في معالجة الصورة {image_name}: {img_error}")
                                        # الاحتفاظ بالصورة الأصلية إذا فشل التحسين
                                    
                                    image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{new_filename}")
                                    
                                except Exception as extract_error:
                                    print(f"خطأ في استخراج الصورة {image_name}: {extract_error}")
                                    continue
                            
                            archive.close()
                            
                            if not image_files:
                                flash('فشل في استخراج الصور من الملف المضغوط', 'error')
                                os.unlink(temp_file.name)
                                db.session.rollback()
                                return redirect(request.url)
                            
                            print(f"✅ تم استخراج {len(image_files)} صورة من الملف المضغوط")
                            
                        except Exception as archive_error:
                            flash(f'خطأ في قراءة الملف المضغوط: {str(archive_error)}', 'error')
                            os.unlink(temp_file.name)
                            db.session.rollback()
                            return redirect(request.url)
                        finally:
                            # حذف الملف المؤقت
                            try:
                                os.unlink(temp_file.name)
                            except:
                                pass

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
                        return redirect(request.url)
                    
                    # استخدام النظام الموحد للكشط - نفس الطريقة المستخدمة في الرفع
                    if has_tested_data:
                        # استخدام البيانات المختبرة (النظام الموحد الجديد)
                        try:
                            import json
                            scraped_images = json.loads(scraped_images_json)
                            print(f"📥 استخدام نتائج الكشط المختبرة: {len(scraped_images)} صورة")
                            
                            # تحميل الصور من القائمة المختبرة
                            for i, img_url in enumerate(scraped_images, 1):
                                try:
                                    print(f"⬇️ تحميل الصورة {i}/{len(scraped_images)}: {img_url}")
                                    
                                    # تحميل الصورة
                                    import requests
                                    response = requests.get(img_url, headers={'Referer': chapter_url}, stream=True, timeout=30)
                                    response.raise_for_status()
                                    
                                    # تحديد امتداد الملف
                                    file_ext = '.webp' if '.webp' in img_url else '.jpg'
                                    filename = f"page_{i:03d}{file_ext}"
                                    img_path = os.path.join(chapter_dir, filename)
                                    
                                    # حفظ الصورة
                                    with open(img_path, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                    
                                    # التحقق من حجم الملف
                                    file_size = os.path.getsize(img_path)
                                    if file_size > 1000:  # أكبر من 1KB
                                        image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                        print(f"✅ تم تحميل: {filename} ({file_size} bytes)")
                                    else:
                                        os.remove(img_path)  # حذف الملفات الفارغة
                                        print(f"❌ تم حذف ملف فارغ: {filename}")
                                        
                                except Exception as e:
                                    print(f"❌ فشل تحميل الصورة {i}: {e}")
                                    continue
                            
                            if not image_files:
                                flash('فشل في تحميل صور الفصل', 'error')
                                db.session.rollback()
                                return redirect(request.url)
                            
                            print(f"✅ تم تحميل {len(image_files)} صورة بنجاح من البيانات المختبرة")
                            
                        except (json.JSONDecodeError, ValueError) as json_err:
                            flash('خطأ في بيانات الكشط المختبرة', 'error')
                            db.session.rollback()
                            return redirect(request.url)
                            
                    elif chapter_url and 'olympustaff.com' in chapter_url:
                        # كشط مباشر للحالات القديمة
                        from simple_manga_scraper import scrape_olympustaff_chapter
                        
                        print(f"🧪 كشط مباشر من: {chapter_url}")
                        result = scrape_olympustaff_chapter(chapter_url)
                        
                        if not result['success']:
                            flash(f'فشل في كشط الصور: {result.get("error", "خطأ غير معروف")}', 'error')
                            db.session.rollback()
                            return redirect(request.url)
                        
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
                        from scraper_utils import scrape_chapter_images
                        import requests
                        
                        try:
                            scrape_result = scrape_chapter_images(source_website, chapter_url)
                            
                            if not scrape_result['success']:
                                flash(f'فشل في كشط الصور: {scrape_result["error"]}', 'error')
                                db.session.rollback()
                                return redirect(request.url)
                            
                            image_urls = scrape_result['images']
                            
                            if not image_urls:
                                flash('لم يتم العثور على صور في الرابط المحدد', 'error')
                                db.session.rollback()
                                return redirect(request.url)
                            
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
                                return redirect(request.url)
                                
                        except Exception as e:
                            flash(f'خطأ في كشط الصور: {str(e)}', 'error')
                            db.session.rollback()
                            return redirect(request.url)
                
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
                
                flash(f'تم إضافة الفصل {chapter_number} بنجاح!', 'success')
                return redirect(url_for('manga_detail', manga_id=manga.id))
                
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

@app.route('/admin/upload-new', methods=['GET', 'POST'])
@login_required  
def admin_upload_new():
    """Admin manga upload page with chapter scheduling"""
    # Allow access for admin and publisher only
    if not (current_user.is_admin or current_user.is_publisher):
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
        chapter_number = float(request.form.get('chapter_number', 1))
        is_locked = bool(request.form.get('is_locked'))
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
                return redirect(request.url)
        elif upload_method == 'zip':
            zip_file = request.files.get('chapter_zip')
            if not title or not zip_file:
                flash('العنوان وملف ZIP مطلوبان', 'error')
                return redirect(request.url)
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
                return redirect(request.url)
            
            # التحقق من وجود بيانات الكشط المختبرة
            scraping_tested = request.form.get('scraping_tested', 'false')
            scraped_images_json = request.form.get('scraped_images', '')
            has_tested_data = scraping_tested == 'true' and scraped_images_json
            
            if not has_scraped_images and not has_tested_data and (not source_website or not chapter_url):
                flash('الموقع المصدر ورابط الفصل مطلوبان أو يجب كشط الصور أولاً', 'error')
                return redirect(request.url)
        
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
            
            # Handle cover image
            if cover_file and cover_file.filename:
                cover_filename = secure_filename(cover_file.filename)
                cover_dir = 'static/uploads/covers'
                os.makedirs(cover_dir, exist_ok=True)
                cover_path = os.path.join(cover_dir, cover_filename)
                cover_file.save(cover_path)
                manga.cover_image = f"uploads/covers/{cover_filename}"
            
            db.session.add(manga)
            db.session.commit()
            
            # Handle multiple categories
            selected_categories = request.form.getlist('categories')
            if selected_categories:
                for category_id in selected_categories:
                    category = Category.query.get(category_id)
                    if category:
                        manga.categories.append(category)
                db.session.commit()
            
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
            
            # Handle chapter images based on upload method
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
                    # ZIP file extraction
                    zip_file = request.files.get('chapter_zip')
                    if zip_file:
                        temp_dir = tempfile.mkdtemp()
                        zip_path = os.path.join(temp_dir, 'chapter.zip')
                        zip_file.save(zip_path)
                        
                        # Extract images from ZIP
                        extracted_images = extract_zip_chapter(zip_path, temp_dir)
                        
                        if not extracted_images:
                            raise Exception('لم يتم العثور على صور صالحة في ملف ZIP')
                        
                        # Move extracted images to chapter directory
                        for i, temp_image_path in enumerate(extracted_images, 1):
                            filename = f"page_{i:03d}.jpg"
                            final_path = os.path.join(chapter_dir, filename)
                            shutil.move(temp_image_path, final_path)
                            image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                
                elif upload_method == 'scrape':
                    # Web scraping - استخدام الطريقة المبسطة الموحدة
                    chapter_url = request.form.get('chapter_url', '')
                    scraping_tested = request.form.get('scraping_tested', 'false')
                    scraped_images_json = request.form.get('scraped_images', '')
                    
                    if not chapter_url:
                        raise Exception('رابط الفصل مطلوب للكشط')
                    
                    # التحقق من وجود بيانات الكشط المختبرة
                    if scraping_tested == 'true' and scraped_images_json:
                        try:
                            import json
                            scraped_images = json.loads(scraped_images_json)
                            print(f"📥 استخدام نتائج الكشط المختبرة: {len(scraped_images)} صورة")
                            
                            # تحميل الصور من القائمة المختبرة
                            downloaded_files = []
                            for i, img_url in enumerate(scraped_images, 1):
                                try:
                                    print(f"⬇️ تحميل الصورة {i}/{len(scraped_images)}: {img_url}")
                                    
                                    # تحميل الصورة
                                    response = requests.get(img_url, headers={'Referer': chapter_url}, stream=True, timeout=30)
                                    response.raise_for_status()
                                    
                                    # تحديد امتداد الملف
                                    file_ext = '.webp' if '.webp' in img_url else '.jpg'
                                    filename = f"page_{i:03d}{file_ext}"
                                    img_path = os.path.join(chapter_dir, filename)
                                    
                                    # حفظ الصورة
                                    with open(img_path, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                    
                                    # التحقق من حجم الملف
                                    file_size = os.path.getsize(img_path)
                                    if file_size > 1000:  # أكبر من 1KB
                                        downloaded_files.append(img_path)
                                        image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                                        print(f"✅ تم تحميل: {filename} ({file_size} bytes)")
                                    else:
                                        print(f"⚠️ ملف صغير، سيتم حذفه: {filename}")
                                        os.remove(img_path)
                                    
                                    # تأخير قصير لتجنب الحظر
                                    time.sleep(0.5)
                                    
                                except Exception as img_error:
                                    print(f"❌ فشل تحميل الصورة {i}: {img_error}")
                                    continue
                            
                            if not downloaded_files:
                                raise Exception('فشل في تحميل جميع الصور')
                            
                            print(f"✅ تم تحميل {len(downloaded_files)} صورة بنجاح من البيانات المختبرة")
                            
                        except (json.JSONDecodeError, ValueError) as json_err:
                            raise Exception('خطأ في قراءة بيانات الصور المختبرة')
                    else:
                        # إذا لم يتم الاختبار، قم بالكشط العادي
                        print(f"📥 بدء الكشط والتحميل المباشر من: {chapter_url}")
                        
                        scrape_result = scrape_olympustaff_simple(chapter_url, chapter_dir)
                        
                        if not scrape_result['success']:
                            raise Exception(f'فشل في كشط الصور: {scrape_result.get("error", "خطأ غير محدد")}')
                        
                        if not scrape_result['downloaded_files']:
                            raise Exception('لم يتم تحميل أي صور من الفصل')
                        
                        print(f"✅ تم كشط وتحميل {len(scrape_result['downloaded_files'])} صورة بنجاح")
                        
                        # إنشاء قائمة بمسارات الصور المحملة
                        for i, file_path in enumerate(scrape_result['downloaded_files'], 1):
                            filename = os.path.basename(file_path)
                            image_files.append(f"uploads/manga/{manga.id}/{chapter.id}/{filename}")
                            print(f"📄 الصورة {i}: {filename}")
                    
                    print(f"🎯 تم معالجة {len(image_files)} صورة بالترتيب الصحيح")
                
                # Create page records
                for i, image_path in enumerate(image_files, 1):
                    page = PageImage()
                    page.chapter_id = chapter.id
                    page.page_number = i
                    page.image_path = image_path
                    db.session.add(page)
                
                # Update chapter pages count
                chapter.pages = len(image_files)
                db.session.commit()
                
            finally:
                # Clean up temporary directory
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            
            # Add categories if selected
            selected_categories = request.form.getlist('categories')
            for cat_id in selected_categories:
                try:
                    category = Category.query.get(int(cat_id))
                    if category:
                        manga.categories.append(category)
                except ValueError:
                    continue
            
            db.session.commit()
            
            if is_locked:
                if early_access_dt:
                    flash(f'تم رفع المانجا بنجاح! الفصل سيكون متاحاً للمشتركين المميزين في {early_access_dt.strftime("%Y-%m-%d %H:%M")} وللجميع في {release_date_dt.strftime("%Y-%m-%d %H:%M") if release_date_dt else "غير محدد"}', 'success')
                else:
                    flash(f'تم رفع المانجا بنجاح! الفصل سيكون متاحاً للجميع في {release_date_dt.strftime("%Y-%m-%d %H:%M") if release_date_dt else "غير محدد"}', 'success')
            else:
                flash('تم رفع المانجا والفصل بنجاح!', 'success')
            
            return redirect(url_for('manga_detail', manga_id=manga.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ أثناء رفع المانجا: {str(e)}', 'error')
            return redirect(request.url)
    
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
        from simple_manga_scraper import test_olympustaff_scraping
        
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
        from simple_manga_scraper import test_olympustaff_scraping
        
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
    is_locked = bool(request.form.get('is_locked'))
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
        auto_publish = bool(request.form.get('auto_publish'))
        
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
    from auto_scraper import auto_scraper
    
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
        from auto_scraper import set_scraping_setting
        
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
                value = 'true' if bool(request.form.get(setting_key)) else 'false'
            set_scraping_setting(setting_key, value)
        
        flash('تم تحديث إعدادات الكشط التلقائي بنجاح!', 'success')
        return redirect(url_for('admin_auto_scraping'))
    
    # GET request - show current settings
    from auto_scraper import get_scraping_setting
    
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
        is_active = bool(request.form.get('is_active'))
        is_featured = bool(request.form.get('is_featured'))
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
        is_active = bool(request.form.get('is_active'))
        is_featured = bool(request.form.get('is_featured'))
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
        is_active = bool(request.form.get('is_active'))
        open_new_tab = bool(request.form.get('open_new_tab'))
        
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
            if file and allowed_file(file.filename):
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
        advertisement.is_active = bool(request.form.get('is_active'))
        advertisement.open_new_tab = bool(request.form.get('open_new_tab'))
        
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
            if file and allowed_file(file.filename):
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
    
    # Delete chapter images
    for page in chapter.page_images:
        if os.path.exists(page.image_path):
            os.remove(page.image_path)
    
    db.session.delete(chapter)
    db.session.commit()
    
    return jsonify({'success': True})

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






