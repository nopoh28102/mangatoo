import re

# قراءة الملف
with open('models.py', 'r') as f:
    content = f.read()

# قاموس لأسماء الجداول
tablenames = {
    'class User(': 'users',
    'class Category(': 'categories', 
    'class Manga(': 'manga',
    'class Chapter(': 'chapters',
    'class PageImage(': 'page_images',
    'class Bookmark(': 'bookmarks',
    'class ReadingProgress(': 'reading_progress',
    'class Comment(': 'comments',
    'class CommentReaction(': 'comment_reactions',
    'class MangaReaction(': 'manga_reactions',
    'class Rating(': 'ratings',
    'class PublisherRequest(': 'publisher_requests',
    'class TranslationRequest(': 'translation_requests',
    'class Notification(': 'notifications',
    'class Announcement(': 'announcements',
    'class Advertisement(': 'advertisements',
    'class Subscription(': 'subscriptions',
    'class MangaAnalytics(': 'manga_analytics',
    'class Translation(': 'translations',
    'class Report(': 'reports',
    'class PaymentPlan(': 'payment_plans',
    'class PaymentGateway(': 'payment_gateways',
    'class Payment(': 'payments',
    'class SiteSetting(': 'site_settings',
    'class UserSubscription(': 'user_subscriptions',
    'class AutoScrapingSource(': 'auto_scraping_sources',
    'class ScrapingLog(': 'scraping_logs',
    'class ScrapingQueue(': 'scraping_queue',
    'class ScrapingSettings(': 'scraping_settings',
    'class StaticPage(': 'static_pages',
    'class BlogPost(': 'blog_posts',
    'class CloudinaryAccount(': 'cloudinary_accounts',
    'class CloudinaryUsageLog(': 'cloudinary_usage_logs'
}

# إضافة __tablename__ لكل كلاس
for class_def, table_name in tablenames.items():
    # البحث عن الكلاس وإضافة __tablename__ بعده إذا لم يكن موجوداً
    pattern = f'({re.escape(class_def)}[^:]*:)\n(\s*)(.*?)'
    def replacement(match):
        class_line = match.group(1)
        indent = match.group(2)
        next_line = match.group(3)
        
        # التحقق من وجود __tablename__ بالفعل
        if '__tablename__' not in next_line:
            return f"{class_line}\n{indent}__tablename__ = '{table_name}'\n{indent}{next_line}"
        else:
            return match.group(0)
    
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

# حفظ الملف المحدث
with open('models.py', 'w') as f:
    f.write(content)

print("تم إضافة __tablename__ بنجاح!")
