import os
import zipfile
from werkzeug.utils import secure_filename
from PIL import Image
from . import app, db
from .models import Manga, Chapter, PageImage, Category

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_ARCHIVE_EXTENSIONS = {'zip', 'cbz', 'rar', 'cbr'}

def allowed_file(filename, allowed_extensions=None):
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in set(allowed_extensions)

def allowed_archive(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_ARCHIVE_EXTENSIONS

def optimize_image(image_path, max_width=1200, quality=85):
    """Optimize image for web viewing"""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if too large
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # Save optimized image
            img.save(image_path, 'JPEG', quality=quality, optimize=True)
            
            return img.width, img.height
    except Exception as e:
        print(f"Error optimizing image {image_path}: {e}")
        return None, None

# Removed process_manga_upload - functionality moved to unified upload routes

def process_chapter_upload(manga_id, chapter_file, chapter_number):
    """Process individual chapter upload"""
    from .models import Chapter, PageImage
    
    # Create chapter directory
    chapter_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'manga', str(manga_id), f'chapter_{chapter_number}')
    os.makedirs(chapter_dir, exist_ok=True)
    
    # Save archive file
    filename = secure_filename(chapter_file.filename)
    archive_path = os.path.join(chapter_dir, filename)
    chapter_file.save(archive_path)
    
    # Extract archive
    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(chapter_dir)
        else:
            # Handle other archive types (rar, etc.) if needed
            pass
        
        # Remove the archive file after extraction
        os.remove(archive_path)
        
        # Create chapter record
        chapter = Chapter()
        chapter.manga_id = manga_id
        chapter.chapter_number = chapter_number
        chapter.title = f'Chapter {chapter_number}'
        chapter.pages = 0  # Will be updated after processing images
        db.session.add(chapter)
        db.session.flush()  # Get chapter ID
        
        # Process extracted images
        image_files = []
        for root, dirs, files in os.walk(chapter_dir):
            for file in files:
                if allowed_file(file):
                    image_files.append(os.path.join(root, file))
        
        # Sort images naturally
        image_files.sort()
        
        # Create page records
        for i, image_path in enumerate(image_files):
            # Optimize image
            width, height = optimize_image(image_path)
            
            # Create relative path for storage
            rel_path = os.path.relpath(image_path, app.config['UPLOAD_FOLDER'])
            
            page = PageImage()
            page.chapter_id = chapter.id
            page.page_number = i + 1
            page.image_path = os.path.join(app.config['UPLOAD_FOLDER'], rel_path)
            page.width = width or 0
            page.height = height or 0
            db.session.add(page)
        
        # Update chapter page count
        chapter.pages = len(image_files)
        db.session.commit()
        
        return chapter.id
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(archive_path):
            os.remove(archive_path)
        print(f"Error processing chapter upload: {e}")
        raise e

def get_category_choices():
    """Get category choices for forms"""
    from models import Category
    return [(str(cat.id), cat.name) for cat in Category.query.all()]

# Cleaned up old duplicate functions

def create_default_categories():
    """Create default manga categories"""
    default_categories = [
        ('Action', 'أكشن', 'High energy battles and fight scenes'),
        ('Adventure', 'مغامرة', 'Journey and exploration stories'),
        ('Comedy', 'كوميديا', 'Humorous and funny content'),
        ('Drama', 'دراما', 'Serious and emotional storylines'),
        ('Fantasy', 'خيال', 'Magical and mythical elements'),
        ('Horror', 'رعب', 'Scary and suspenseful content'),
        ('Mystery', 'غموض', 'Puzzle-solving and detective stories'),
        ('Romance', 'رومانسية', 'Love stories and relationships'),
        ('Sci-Fi', 'خيال علمي', 'Science fiction and futuristic themes'),
        ('Slice of Life', 'شريحة من الحياة', 'Everyday life situations'),
        ('Sports', 'رياضة', 'Athletic competitions and training'),
        ('Supernatural', 'خارق للطبيعة', 'Paranormal and otherworldly events'),
        ('Thriller', 'إثارة', 'Intense and suspenseful plots'),
        ('Historical', 'تاريخي', 'Set in historical time periods'),
        ('School', 'مدرسي', 'Educational institution settings'),
        ('Psychological', 'نفسي', 'Mental and emotional complexity'),
        ('Martial Arts', 'فنون قتالية', 'Fighting techniques and training'),
        ('Isekai', 'عالم آخر', 'Transported to another world'),
        ('Yaoi/BL', 'رومانسية ذكورية', 'Boys Love romance'),
        ('Yuri/GL', 'رومانسية أنثوية', 'Girls Love romance')
    ]
    
    for name, name_ar, description in default_categories:
        if not Category.query.filter_by(name=name).first():
            category = Category()
            category.name = name
            category.name_ar = name_ar
            category.description = description
            db.session.add(category)
    
    db.session.commit()

# Create default categories on app startup
with app.app_context():
    create_default_categories()
