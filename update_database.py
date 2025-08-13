#!/usr/bin/env python3
"""
Script to update and complete the database with missing data
"""

import os
from datetime import datetime, timedelta
from app import app, db
from models import *
from werkzeug.security import generate_password_hash
import random

def update_categories():
    """Update existing categories with missing data"""
    
    # Categories with Arabic names and slugs
    category_updates = {
        'Action': ('أكشن', 'action'),
        'Adventure': ('مغامرة', 'adventure'), 
        'Comedy': ('كوميدي', 'comedy'),
        'Drama': ('دراما', 'drama'),
        'Fantasy': ('خيال', 'fantasy'),
        'Horror': ('رعب', 'horror'),
        'Mystery': ('غموض', 'mystery'),
        'Romance': ('رومانسية', 'romance'),
        'Sci-Fi': ('خيال علمي', 'sci-fi'),
        'Slice of Life': ('شريحة من الحياة', 'slice-of-life'),
        'Sports': ('رياضة', 'sports'),
        'Supernatural': ('خارق للطبيعة', 'supernatural'),
        'Thriller': ('إثارة', 'thriller'),
        'Historical': ('تاريخي', 'historical'),
        'School': ('مدرسة', 'school'),
        'Psychological': ('نفسي', 'psychological'),
        'Martial Arts': ('فنون القتال', 'martial-arts'),
        'Isekai': ('عالم آخر', 'isekai'),
        'Yaoi/BL': ('ياوي/BL', 'yaoi-bl'),
        'Yuri/GL': ('يوري/GL', 'yuri-gl')
    }
    
    for category in Category.query.all():
        if category.name in category_updates:
            category.name_ar, category.slug = category_updates[category.name]
            category.description = f"Manga in the {category.name} genre"
            category.is_active = True
    
    db.session.commit()
    print("Categories updated with Arabic names and slugs")

def add_missing_data():
    """Add all missing essential data"""
    
    # Add users
    users_data = [
        ('publisher1', 'publisher1@manga.com', False, True, False),
        ('translator1', 'translator1@manga.com', False, False, True),
        ('reader1', 'reader1@manga.com', False, False, False),
        ('reader2', 'reader2@manga.com', False, False, False),
        ('premium_user', 'premium@manga.com', False, False, False),
    ]
    
    for username, email, is_admin, is_publisher, is_translator in users_data:
        if not User.query.filter_by(username=username).first():
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash('password123'),
                is_admin=is_admin,
                is_publisher=is_publisher,
                is_translator=is_translator,
                bio=f"Bio for {username}",
                bio_ar=f"السيرة الذاتية لـ {username}",
                country="US",
                language_preference="en"
            )
            
            if username == 'premium_user':
                user.premium_until = datetime.utcnow() + timedelta(days=365)
                
            db.session.add(user)
    
    # Add payment gateways
    if PaymentGateway.query.count() == 0:
        gateways = [
            {
                'name': 'PayPal',
                'display_name': 'PayPal',
                'display_name_ar': 'باي بال',
                'gateway_type': 'paypal',
                'icon_class': 'fab fa-paypal',
                'description': 'Pay securely with PayPal',
                'description_ar': 'ادفع بأمان مع باي بال',
                'supported_currencies': ['USD', 'EUR', 'GBP'],
                'processing_fee': 2.9,
                'processing_time': 'Instant',
                'processing_time_ar': 'فوري',
                'supports_recurring': True
            },
            {
                'name': 'Stripe',
                'display_name': 'Credit/Debit Card',
                'display_name_ar': 'بطاقة ائتمانية/خصم',
                'gateway_type': 'stripe',
                'icon_class': 'far fa-credit-card',
                'description': 'Pay with Visa, MasterCard, or American Express',
                'description_ar': 'ادفع بفيزا أو ماستركارد أو أمريكان إكسبريس',
                'supported_currencies': ['USD', 'EUR', 'SAR'],
                'processing_fee': 2.9,
                'processing_time': 'Instant',
                'processing_time_ar': 'فوري',
                'supports_recurring': True
            }
        ]
        
        for gateway_data in gateways:
            gateway = PaymentGateway(**gateway_data)
            db.session.add(gateway)
    
    # Add payment plans
    if PaymentPlan.query.count() == 0:
        plans = [
            {
                'name': 'Monthly Premium',
                'name_ar': 'الاشتراك الشهري المميز',
                'price': 9.99,
                'duration_months': 1,
                'features': ['Ad-free reading', 'Early access', 'HD downloads']
            },
            {
                'name': 'Annual Premium',
                'name_ar': 'الاشتراك السنوي المميز',
                'price': 99.99,
                'duration_months': 12,
                'features': ['Ad-free reading', 'Early access', 'HD downloads', '2 months free']
            }
        ]
        
        for plan_data in plans:
            plan = PaymentPlan(**plan_data)
            db.session.add(plan)
    
    db.session.commit()
    
    # Add sample manga
    if Manga.query.count() == 0:
        action_cat = Category.query.filter_by(slug='action').first()
        romance_cat = Category.query.filter_by(slug='romance').first()
        fantasy_cat = Category.query.filter_by(slug='fantasy').first()
        publisher = User.query.filter_by(is_publisher=True).first()
        
        if action_cat and publisher:
            manga_data = [
                {
                    'title': 'Shadow Warrior Chronicles',
                    'title_ar': 'سجلات محارب الظلال',
                    'description': 'Epic adventure of a young warrior discovering ancient shadow magic to save his kingdom.',
                    'description_ar': 'مغامرة ملحمية لمحارب شاب يكتشف سحر الظلال القديم لإنقاذ مملكته.',
                    'author': 'Yuki Tanaka',
                    'artist': 'Hiroshi Sato',
                    'status': 'ongoing',
                    'type': 'manga',
                    'categories': [action_cat, fantasy_cat] if fantasy_cat else [action_cat],
                    'chapters': [
                        {'number': 1, 'title': 'The Awakening', 'title_ar': 'الصحوة'},
                        {'number': 2, 'title': 'First Shadow', 'title_ar': 'الظل الأول'},
                        {'number': 3, 'title': 'Ancient Temple', 'title_ar': 'المعبد القديم'},
                    ]
                },
                {
                    'title': 'Hearts in Bloom',
                    'title_ar': 'قلوب متفتحة',
                    'description': 'A heartwarming romance between two college students meeting at a cherry blossom festival.',
                    'description_ar': 'قصة حب دافئة بين طالبين جامعيين يلتقيان في مهرجان أزهار الكرز.',
                    'author': 'Sakura Yamamoto',
                    'artist': 'Mei Nakamura',
                    'status': 'completed',
                    'type': 'manga',
                    'categories': [romance_cat] if romance_cat else [action_cat],
                    'chapters': [
                        {'number': 1, 'title': 'Cherry Blossom Meeting', 'title_ar': 'لقاء أزهار الكرز'},
                        {'number': 2, 'title': 'Study Partners', 'title_ar': 'شركاء الدراسة'},
                        {'number': 3, 'title': 'First Date', 'title_ar': 'الموعد الأول'},
                    ]
                }
            ]
            
            for manga_info in manga_data:
                manga = Manga(
                    title=manga_info['title'],
                    title_ar=manga_info['title_ar'],
                    description=manga_info['description'],
                    description_ar=manga_info['description_ar'],
                    author=manga_info['author'],
                    artist=manga_info['artist'],
                    status=manga_info['status'],
                    type=manga_info['type'],
                    publisher_id=publisher.id,
                    views=random.randint(1000, 10000),
                    is_featured=random.choice([True, False]),
                    tags=['popular', 'trending']
                )
                
                db.session.add(manga)
                db.session.flush()
                
                # Add categories
                for category in manga_info['categories']:
                    manga.categories.append(category)
                
                # Add chapters
                for chapter_info in manga_info['chapters']:
                    chapter = Chapter(
                        manga_id=manga.id,
                        chapter_number=chapter_info['number'],
                        title=chapter_info['title'],
                        title_ar=chapter_info['title_ar'],
                        pages=random.randint(15, 25)
                    )
                    db.session.add(chapter)
                    db.session.flush()
                    
                    # Add some sample page images
                    for page_num in range(1, min(6, chapter.pages + 1)):  # Add first 5 pages
                        page_image = PageImage(
                            chapter_id=chapter.id,
                            page_number=page_num,
                            image_path=f'/static/sample_pages/page_{page_num}.jpg',
                            image_width=800,
                            image_height=1200
                        )
                        db.session.add(page_image)
    
    # Add announcements
    admin = User.query.filter_by(is_admin=True).first()
    if admin and Announcement.query.count() == 0:
        announcements = [
            {
                'title': 'Welcome to Manga Platform!',
                'title_ar': 'مرحباً بكم في منصة المانجا!',
                'content': 'Enjoy reading thousands of manga titles with advanced features.',
                'content_ar': 'استمتع بقراءة آلاف عناوين المانجا مع ميزات متقدمة.',
                'type': 'success',
                'is_featured': True,
                'target_audience': 'all',
                'created_by': admin.id
            },
            {
                'title': 'Premium Features Available',
                'title_ar': 'ميزات مميزة متاحة',
                'content': 'Check out premium plans for ad-free reading and exclusive content!',
                'content_ar': 'اكتشف الخطط المميزة للقراءة بدون إعلانات والمحتوى الحصري!',
                'type': 'info',
                'is_featured': False,
                'target_audience': 'all',
                'created_by': admin.id
            }
        ]
        
        for ann_data in announcements:
            announcement = Announcement(**ann_data)
            db.session.add(announcement)
    
    # Add scraping settings
    if ScrapingSettings.query.count() == 0:
        settings = [
            ('max_concurrent_scraping', '3', 'Maximum concurrent scraping processes'),
            ('scraping_delay_seconds', '2', 'Delay between scraping requests'),
            ('enable_auto_scraping', 'true', 'Enable automatic scraping'),
            ('default_check_interval', '3600', 'Default check interval in seconds')
        ]
        
        for key, value, desc in settings:
            setting = ScrapingSettings(key=key, value=value, description=desc)
            db.session.add(setting)
    
    db.session.commit()
    print("All missing data added successfully")

def add_sample_interactions():
    """Add sample bookmarks, ratings, and comments"""
    users = User.query.filter(User.is_admin == False).all()
    manga_list = Manga.query.all()
    chapters = Chapter.query.all()
    
    if users and manga_list:
        # Add bookmarks
        for user in users[:2]:
            for manga in manga_list:
                if not Bookmark.query.filter_by(user_id=user.id, manga_id=manga.id).first():
                    bookmark = Bookmark(user_id=user.id, manga_id=manga.id)
                    db.session.add(bookmark)
        
        # Add ratings
        for user in users:
            for manga in manga_list:
                if not Rating.query.filter_by(user_id=user.id, manga_id=manga.id).first():
                    rating = Rating(
                        user_id=user.id,
                        manga_id=manga.id,
                        rating=random.randint(4, 5),
                        review=f"Great manga! Really enjoyed {manga.title}."
                    )
                    db.session.add(rating)
        
        # Add comments
        for chapter in chapters[:5]:  # First 5 chapters
            for user in users[:2]:  # First 2 users
                comment = Comment(
                    user_id=user.id,
                    chapter_id=chapter.id,
                    content=f"Awesome chapter! Can't wait for the next one."
                )
                db.session.add(comment)
        
        db.session.commit()
        print("Sample interactions added")

def main():
    """Main update function"""
    with app.app_context():
        try:
            print("Updating database with complete data...")
            
            update_categories()
            add_missing_data() 
            add_sample_interactions()
            
            print("\n" + "="*50)
            print("DATABASE UPDATE COMPLETED SUCCESSFULLY!")
            print("="*50)
            print(f"Categories: {Category.query.count()}")
            print(f"Users: {User.query.count()}")
            print(f"Manga: {Manga.query.count()}")
            print(f"Chapters: {Chapter.query.count()}")
            print(f"Payment Plans: {PaymentPlan.query.count()}")
            print(f"Payment Gateways: {PaymentGateway.query.count()}")
            print(f"Bookmarks: {Bookmark.query.count()}")
            print(f"Ratings: {Rating.query.count()}")
            print(f"Comments: {Comment.query.count()}")
            print(f"Announcements: {Announcement.query.count()}")
            
            print("\nLogin Credentials:")
            print("Admin: admin/admin123")
            print("Publisher: publisher1/password123")
            print("Reader: reader1/password123")
            print("Premium: premium_user/password123")
            
        except Exception as e:
            print(f"Error: {e}")
            db.session.rollback()
            raise

if __name__ == "__main__":
    main()