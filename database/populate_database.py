#!/usr/bin/env python3
"""
Script to populate the database with comprehensive sample data
"""

import os
from datetime import datetime, timedelta
from app import app, db
from app.models import (
    User, Category, Manga, Chapter, PageImage, Bookmark, ReadingProgress,
    Comment, Rating, PublisherRequest, TranslationRequest, Notification,
    Announcement, Advertisement, Subscription, MangaAnalytics, Translation,
    Report, PaymentPlan, PaymentGateway, Payment, UserSubscription,
    AutoScrapingSource, ScrapingLog, ScrapingQueue, ScrapingSettings,
    manga_category
)
from werkzeug.security import generate_password_hash
import random

def populate_categories():
    """Add manga categories"""
    categories_data = [
        # English categories with Arabic translations
        ('Action', 'أكشن', 'High-energy manga with combat and adventure', 'action'),
        ('Romance', 'رومانسية', 'Love stories and relationships', 'romance'),
        ('Comedy', 'كوميدي', 'Funny and humorous manga', 'comedy'),
        ('Drama', 'دراما', 'Emotional and character-driven stories', 'drama'),
        ('Fantasy', 'خيال', 'Magical worlds and supernatural elements', 'fantasy'),
        ('Horror', 'رعب', 'Scary and suspenseful manga', 'horror'),
        ('Mystery', 'غموض', 'Puzzles and detective stories', 'mystery'),
        ('Sci-Fi', 'خيال علمي', 'Science fiction and futuristic themes', 'sci-fi'),
        ('Slice of Life', 'شريحة من الحياة', 'Everyday life and realistic situations', 'slice-of-life'),
        ('Sports', 'رياضة', 'Athletic competitions and team dynamics', 'sports'),
        ('Thriller', 'إثارة', 'Suspenseful and intense storylines', 'thriller'),
        ('Historical', 'تاريخي', 'Set in historical periods', 'historical'),
        ('Psychological', 'نفسي', 'Mind games and psychological themes', 'psychological'),
        ('School', 'مدرسة', 'School life and student adventures', 'school'),
        ('Supernatural', 'خارق للطبيعة', 'Ghosts, demons, and otherworldly beings', 'supernatural'),
    ]
    
    for name, name_ar, desc, slug in categories_data:
        if not Category.query.filter_by(slug=slug).first():
            category = Category(
                name=name,
                name_ar=name_ar,
                description=desc,
                slug=slug,
                is_active=True
            )
            db.session.add(category)
    
    db.session.commit()
    print("Categories added successfully")

def populate_users():
    """Add sample users"""
    users_data = [
        ('publisher1', 'publisher1@manga.com', 'Publisher One', False, True, False),
        ('translator1', 'translator1@manga.com', 'Translator One', False, False, True),
        ('reader1', 'reader1@manga.com', 'Reader One', False, False, False),
        ('reader2', 'reader2@manga.com', 'Reader Two', False, False, False),
        ('premium_user', 'premium@manga.com', 'Premium Reader', False, False, False),
    ]
    
    for username, email, full_name, is_admin, is_publisher, is_translator in users_data:
        if not User.query.filter_by(username=username).first():
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash('password123'),
                is_admin=is_admin,
                is_publisher=is_publisher,
                is_translator=is_translator,
                bio=f"This is {full_name}'s profile bio.",
                bio_ar=f"هذه السيرة الذاتية لـ {full_name}.",
                country="US",
                language_preference="en"
            )
            
            # Make premium user actually premium for 1 year
            if username == 'premium_user':
                user.premium_until = datetime.utcnow() + timedelta(days=365)
            
            db.session.add(user)
    
    db.session.commit()
    print("Users added successfully")

def populate_payment_gateways():
    """Add various payment gateways"""
    gateways_data = [
        {
            'name': 'PayPal',
            'display_name': 'PayPal',
            'display_name_ar': 'باي بال',
            'gateway_type': 'paypal',
            'icon_class': 'fab fa-paypal',
            'description': 'Pay securely with PayPal',
            'description_ar': 'ادفع بأمان مع باي بال',
            'supported_currencies': ['USD', 'EUR', 'GBP', 'CAD', 'AUD'],
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
            'supported_currencies': ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY'],
            'processing_fee': 2.9,
            'processing_time': 'Instant',
            'processing_time_ar': 'فوري',
            'supports_recurring': True
        },
        {
            'name': 'PayTabs',
            'display_name': 'PayTabs',
            'display_name_ar': 'بي تابز',
            'gateway_type': 'paytabs',
            'icon_class': 'fas fa-credit-card',
            'description': 'Middle East payment solution',
            'description_ar': 'حل الدفع للشرق الأوسط',
            'supported_currencies': ['SAR', 'AED', 'KWD', 'BHD', 'QAR', 'USD'],
            'processing_fee': 3.5,
            'processing_time': 'Instant',
            'processing_time_ar': 'فوري',
            'supports_recurring': True,
            'supported_countries': ['SA', 'AE', 'KW', 'BH', 'QA', 'OM', 'JO', 'LB', 'EG']
        },
        {
            'name': 'Apple Pay',
            'display_name': 'Apple Pay',
            'display_name_ar': 'أبل باي',
            'gateway_type': 'apple_pay',
            'icon_class': 'fab fa-apple-pay',
            'description': 'Quick and secure payments with Apple Pay',
            'description_ar': 'مدفوعات سريعة وآمنة مع أبل باي',
            'supported_currencies': ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'SAR'],
            'processing_fee': 2.9,
            'processing_time': 'Instant',
            'processing_time_ar': 'فوري'
        }
    ]
    
    for gateway_data in gateways_data:
        if not PaymentGateway.query.filter_by(name=gateway_data['name']).first():
            gateway = PaymentGateway(**gateway_data)
            db.session.add(gateway)
    
    db.session.commit()
    print("Payment gateways added successfully")

def populate_payment_plans():
    """Add subscription plans"""
    plans_data = [
        {
            'name': 'Monthly Premium',
            'name_ar': 'الاشتراك الشهري المميز',
            'price': 9.99,
            'duration_months': 1,
            'features': [
                'Ad-free reading experience',
                'Early access to new chapters',
                'High-quality image downloads',
                'Unlimited bookmarks',
                'Priority customer support'
            ]
        },
        {
            'name': 'Annual Premium',
            'name_ar': 'الاشتراك السنوي المميز',
            'price': 99.99,
            'duration_months': 12,
            'features': [
                'Ad-free reading experience',
                'Early access to new chapters',
                'High-quality image downloads',
                'Unlimited bookmarks',
                'Priority customer support',
                '2 months free (Best Value!)',
                'Exclusive premium content'
            ]
        },
        {
            'name': 'Quarterly Premium',
            'name_ar': 'الاشتراك الربع سنوي المميز',
            'price': 24.99,
            'duration_months': 3,
            'features': [
                'Ad-free reading experience',
                'Early access to new chapters',
                'High-quality image downloads',
                'Unlimited bookmarks',
                'Priority customer support'
            ]
        }
    ]
    
    for plan_data in plans_data:
        if not PaymentPlan.query.filter_by(name=plan_data['name']).first():
            plan = PaymentPlan(**plan_data)
            db.session.add(plan)
    
    db.session.commit()
    print("Payment plans added successfully")

def populate_manga_and_chapters():
    """Add sample manga with chapters"""
    # Get categories and users
    action_cat = Category.query.filter_by(slug='action').first()
    romance_cat = Category.query.filter_by(slug='romance').first()
    fantasy_cat = Category.query.filter_by(slug='fantasy').first()
    publisher = User.query.filter_by(username='publisher1').first()
    
    manga_data = [
        {
            'title': 'Shadow Warrior Chronicles',
            'title_ar': 'سجلات محارب الظلال',
            'description': 'Follow the epic journey of a young warrior who discovers ancient shadow magic and must save his kingdom from an approaching darkness. Filled with intense battles, mystical creatures, and unexpected alliances.',
            'description_ar': 'تابع الرحلة الملحمية لمحارب شاب يكتشف سحر الظلال القديم ويجب أن يُنقذ مملكته من ظلام يقترب. مليء بالمعارك الشديدة والمخلوقات الصوفية والتحالفات غير المتوقعة.',
            'author': 'Yuki Tanaka',
            'artist': 'Hiroshi Sato',
            'status': 'ongoing',
            'type': 'manga',
            'categories': [action_cat, fantasy_cat],
            'chapters': [
                {'number': 1, 'title': 'The Awakening', 'title_ar': 'الصحوة'},
                {'number': 2, 'title': 'First Shadow', 'title_ar': 'الظل الأول'},
                {'number': 3, 'title': 'The Ancient Temple', 'title_ar': 'المعبد القديم'},
                {'number': 4, 'title': 'Master of Shadows', 'title_ar': 'سيد الظلال'},
                {'number': 5, 'title': 'The Dark Alliance', 'title_ar': 'التحالف المظلم'},
            ]
        },
        {
            'title': 'Hearts in Bloom',
            'title_ar': 'قلوب متفتحة',
            'description': 'A heartwarming romance about two college students who meet at a cherry blossom festival. Their love story unfolds through seasons of joy, challenges, and personal growth.',
            'description_ar': 'قصة حب دافئة عن طالبين جامعيين يلتقيان في مهرجان أزهار الكرز. تتكشف قصة حبهما عبر فصول من الفرح والتحديات والنمو الشخصي.',
            'author': 'Sakura Yamamoto',
            'artist': 'Mei Nakamura',
            'status': 'completed',
            'type': 'manga',
            'categories': [romance_cat],
            'chapters': [
                {'number': 1, 'title': 'Cherry Blossom Meeting', 'title_ar': 'لقاء أزهار الكرز'},
                {'number': 2, 'title': 'Study Partners', 'title_ar': 'شركاء الدراسة'},
                {'number': 3, 'title': 'First Date', 'title_ar': 'الموعد الأول'},
                {'number': 4, 'title': 'Summer Festival', 'title_ar': 'مهرجان الصيف'},
                {'number': 5, 'title': 'Autumn Confessions', 'title_ar': 'اعترافات الخريف'},
                {'number': 6, 'title': 'Winter Promise', 'title_ar': 'وعد الشتاء'},
                {'number': 7, 'title': 'Spring Wedding', 'title_ar': 'زفاف الربيع'},
            ]
        },
        {
            'title': 'Digital Legends',
            'title_ar': 'أساطير رقمية',
            'description': 'In a futuristic world where reality and virtual worlds merge, young hackers fight for freedom against a corrupt mega-corporation controlling society.',
            'description_ar': 'في عالم مستقبلي حيث تندمج الحقيقة والعوالم الافتراضية، يقاتل هاكرز شباب من أجل الحرية ضد شركة ضخمة فاسدة تسيطر على المجتمع.',
            'author': 'Kenji Matsumoto',
            'artist': 'Ryo Kimura',
            'status': 'ongoing',
            'type': 'manhwa',
            'categories': [action_cat, fantasy_cat],
            'chapters': [
                {'number': 1, 'title': 'Virtual Reality', 'title_ar': 'الواقع الافتراضي'},
                {'number': 2, 'title': 'The Resistance', 'title_ar': 'المقاومة'},
                {'number': 3, 'title': 'Code Breakers', 'title_ar': 'كاسروا الشفرة'},
            ]
        }
    ]
    
    for manga_info in manga_data:
        if not Manga.query.filter_by(title=manga_info['title']).first():
            # Create manga
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
                views=random.randint(1000, 50000),
                is_featured=random.choice([True, False]),
                tags=['popular', 'trending', 'recommended']
            )
            
            db.session.add(manga)
            db.session.flush()  # Get the manga ID
            
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
                    pages=random.randint(15, 30)
                )
                db.session.add(chapter)
    
    db.session.commit()
    print("Manga and chapters added successfully")

def populate_announcements():
    """Add system announcements"""
    admin = User.query.filter_by(is_admin=True).first()
    
    announcements_data = [
        {
            'title': 'Welcome to Our Manga Platform!',
            'title_ar': 'مرحباً بكم في منصة المانجا لدينا!',
            'content': 'We are excited to launch our new manga reading platform. Enjoy thousands of manga, manhwa, and manhua titles with our advanced reading features.',
            'content_ar': 'نحن متحمسون لإطلاق منصة قراءة المانجا الجديدة. استمتع بآلاف من عناوين المانجا والمانهوا والمانهوا مع ميزات القراءة المتقدمة لدينا.',
            'type': 'success',
            'is_featured': True,
            'target_audience': 'all'
        },
        {
            'title': 'New Premium Features Available',
            'title_ar': 'ميزات مميزة جديدة متاحة',
            'content': 'Check out our new premium subscription plans with ad-free reading, early access to chapters, and exclusive content!',
            'content_ar': 'اكتشف خطط الاشتراك المميزة الجديدة مع قراءة بدون إعلانات ووصول مبكر للفصول ومحتوى حصري!',
            'type': 'info',
            'is_featured': False,
            'target_audience': 'all'
        }
    ]
    
    for ann_data in announcements_data:
        if not Announcement.query.filter_by(title=ann_data['title']).first():
            announcement = Announcement(
                created_by=admin.id,
                **ann_data
            )
            db.session.add(announcement)
    
    db.session.commit()
    print("Announcements added successfully")

def populate_advertisements():
    """Add sample advertisements"""
    admin = User.query.filter_by(is_admin=True).first()
    
    ads_data = [
        {
            'title': 'Premium Subscription Banner',
            'description': 'Promote premium subscriptions',
            'ad_type': 'banner',
            'placement': 'reader_top',
            'content': '<div class="alert alert-info text-center"><strong>Upgrade to Premium!</strong> Enjoy ad-free reading and exclusive content. <a href="/premium/plans" class="btn btn-primary btn-sm">Subscribe Now</a></div>',
            'priority': 5
        },
        {
            'title': 'Chapter End Promotion',
            'description': 'End of chapter promotional content',
            'ad_type': 'text',
            'placement': 'chapter_end',
            'content': '<div class="text-center p-4 bg-light border rounded"><h5>Enjoying this manga?</h5><p>Rate it and leave a comment to support the creator!</p><a href="#" class="btn btn-success">Rate Now</a></div>',
            'priority': 3
        }
    ]
    
    for ad_data in ads_data:
        if not Advertisement.query.filter_by(title=ad_data['title']).first():
            ad = Advertisement(
                created_by=admin.id,
                **ad_data
            )
            db.session.add(ad)
    
    db.session.commit()
    print("Advertisements added successfully")

def populate_scraping_settings():
    """Add scraping configuration settings"""
    settings_data = [
        ('max_concurrent_scraping', '3', 'Maximum number of concurrent scraping processes'),
        ('scraping_delay_seconds', '2', 'Delay between scraping requests in seconds'),
        ('max_retry_attempts', '3', 'Maximum retry attempts for failed scraping'),
        ('enable_auto_scraping', 'true', 'Enable automatic scraping feature'),
        ('scraping_user_agent', 'Mozilla/5.0 (compatible; MangaPlatformBot/1.0)', 'User agent for scraping requests'),
        ('default_check_interval', '3600', 'Default check interval in seconds (1 hour)'),
        ('quality_check_enabled', 'true', 'Enable quality checks on scraped content'),
        ('auto_publish_enabled', 'false', 'Automatically publish scraped chapters (not recommended)')
    ]
    
    for key, value, desc in settings_data:
        if not ScrapingSettings.query.filter_by(key=key).first():
            setting = ScrapingSettings(
                key=key,
                value=value,
                description=desc
            )
            db.session.add(setting)
    
    db.session.commit()
    print("Scraping settings added successfully")

def populate_sample_interactions():
    """Add sample user interactions like bookmarks, ratings, comments"""
    # Get sample data
    users = User.query.filter(User.is_admin == False).all()
    manga_list = Manga.query.all()
    chapters = Chapter.query.all()
    
    if not users or not manga_list:
        print("No users or manga found, skipping interactions")
        return
    
    # Add bookmarks
    for user in users[:3]:  # First 3 non-admin users
        for manga in random.sample(manga_list, min(2, len(manga_list))):
            if not Bookmark.query.filter_by(user_id=user.id, manga_id=manga.id).first():
                bookmark = Bookmark(user_id=user.id, manga_id=manga.id)
                db.session.add(bookmark)
    
    # Add ratings
    for user in users:
        for manga in random.sample(manga_list, min(2, len(manga_list))):
            if not Rating.query.filter_by(user_id=user.id, manga_id=manga.id).first():
                rating = Rating(
                    user_id=user.id,
                    manga_id=manga.id,
                    rating=random.randint(3, 5),
                    review=f"Great manga! I really enjoyed reading {manga.title}. The story is engaging and the artwork is beautiful."
                )
                db.session.add(rating)
    
    # Add comments
    for chapter in random.sample(chapters, min(10, len(chapters))):
        for user in random.sample(users, min(2, len(users))):
            comment = Comment(
                user_id=user.id,
                chapter_id=chapter.id,
                content=f"Awesome chapter! Can't wait for the next one. The story keeps getting better and better!"
            )
            db.session.add(comment)
    
    db.session.commit()
    print("Sample interactions added successfully")

def main():
    """Main function to populate database"""
    with app.app_context():
        print("Starting database population...")
        
        try:
            populate_categories()
            populate_users()
            populate_payment_gateways()
            populate_payment_plans()
            populate_manga_and_chapters()
            populate_announcements()
            populate_advertisements()
            populate_scraping_settings()
            populate_sample_interactions()
            
            print("\n" + "="*50)
            print("DATABASE POPULATION COMPLETED SUCCESSFULLY!")
            print("="*50)
            print("\nSummary:")
            print(f"- Categories: {Category.query.count()}")
            print(f"- Users: {User.query.count()}")
            print(f"- Payment Gateways: {PaymentGateway.query.count()}")
            print(f"- Payment Plans: {PaymentPlan.query.count()}")
            print(f"- Manga: {Manga.query.count()}")
            print(f"- Chapters: {Chapter.query.count()}")
            print(f"- Bookmarks: {Bookmark.query.count()}")
            print(f"- Ratings: {Rating.query.count()}")
            print(f"- Comments: {Comment.query.count()}")
            print(f"- Announcements: {Announcement.query.count()}")
            print(f"- Advertisements: {Advertisement.query.count()}")
            
            print("\nLogin credentials:")
            print("- Admin: admin/admin123")
            print("- Publisher: publisher1/password123")
            print("- Translator: translator1/password123")
            print("- Reader: reader1/password123")
            print("- Premium User: premium_user/password123")
            
        except Exception as e:
            print(f"Error during population: {e}")
            db.session.rollback()
            raise

if __name__ == "__main__":
    main()