"""
Settings management utilities for the manga platform
"""

from .app import db
from .models import SiteSetting
import json
import logging

class SettingsManager:
    """Manage site settings with caching and type conversion"""
    
    _cache = {}
    _default_settings = {
        # General Site Settings
        'site_name': {'value': 'منصة المانجا', 'type': 'string', 'category': 'general', 
                     'description': 'Site name displayed in header and title', 
                     'description_ar': 'اسم الموقع المعروض في الرأس والعنوان'},
        'site_tagline': {'value': 'منصة قراءة المانجا المفضلة لديك', 'type': 'string', 'category': 'general',
                        'description': 'Site tagline/subtitle',
                        'description_ar': 'شعار/عنوان فرعي للموقع'},
        'site_description': {'value': 'اقرأ المانجا والمانهوا المفضلة لديك عبر الإنترنت مجاناً', 'type': 'string', 'category': 'general',
                            'description': 'Meta description for SEO',
                            'description_ar': 'وصف تعريفي للموقع لمحركات البحث'},
        'admin_email': {'value': 'admin@mangaplatform.com', 'type': 'string', 'category': 'general',
                       'description': 'Administrator email address',
                       'description_ar': 'عنوان بريد المدير الإلكتروني'},
        'contact_email': {'value': 'contact@mangaplatform.com', 'type': 'string', 'category': 'general',
                         'description': 'Contact email for users',
                         'description_ar': 'بريد التواصل للمستخدمين'},
        
        # Bravo Mail Settings
        'bravo_mail_enabled': {'value': 'false', 'type': 'boolean', 'category': 'bravo_mail',
                              'description': 'Enable Bravo Mail service',
                              'description_ar': 'تفعيل خدمة Bravo Mail'},
        'bravo_mail_api_key': {'value': '', 'type': 'string', 'category': 'bravo_mail',
                              'description': 'Bravo Mail API Key',
                              'description_ar': 'مفتاح API لخدمة Bravo Mail'},
        'bravo_mail_api_url': {'value': 'https://api.bravo-mail.com/v1/', 'type': 'string', 'category': 'bravo_mail',
                              'description': 'Bravo Mail API Base URL',
                              'description_ar': 'رابط API الأساسي لخدمة Bravo Mail'},
        'bravo_mail_sender_name': {'value': 'منصة المانجا', 'type': 'string', 'category': 'bravo_mail',
                                  'description': 'Default sender name',
                                  'description_ar': 'اسم المرسل الافتراضي'},
        'bravo_mail_sender_email': {'value': 'noreply@mangaplatform.com', 'type': 'string', 'category': 'bravo_mail',
                                   'description': 'Default sender email',
                                   'description_ar': 'بريد المرسل الافتراضي'},
        'bravo_mail_reply_to': {'value': 'support@mangaplatform.com', 'type': 'string', 'category': 'bravo_mail',
                               'description': 'Reply-to email address',
                               'description_ar': 'عنوان البريد للرد'},
        'bravo_mail_timeout': {'value': '30', 'type': 'number', 'category': 'bravo_mail',
                              'description': 'API timeout in seconds',
                              'description_ar': 'مهلة انتظار API بالثواني'},
        'bravo_mail_max_retries': {'value': '3', 'type': 'number', 'category': 'bravo_mail',
                                  'description': 'Maximum retry attempts',
                                  'description_ar': 'عدد محاولات الإرسال القصوى'},
        'timezone': {'value': 'Asia/Riyadh', 'type': 'string', 'category': 'general',
                    'description': 'Site default timezone',
                    'description_ar': 'المنطقة الزمنية الافتراضية للموقع'},
        'default_language': {'value': 'ar', 'type': 'string', 'category': 'general',
                            'description': 'Default site language',
                            'description_ar': 'لغة الموقع الافتراضية'},
        'site_enabled': {'value': 'true', 'type': 'boolean', 'category': 'general',
                        'description': 'Enable/disable site access',
                        'description_ar': 'تفعيل/إلغاء تفعيل الوصول للموقع'},
        'maintenance_mode': {'value': 'false', 'type': 'boolean', 'category': 'general',
                           'description': 'Enable maintenance mode',
                           'description_ar': 'تفعيل وضع الصيانة'},
        'maintenance_message': {'value': 'الموقع تحت الصيانة. سنعود قريباً!', 'type': 'string', 'category': 'general',
                              'description': 'Maintenance mode message',
                              'description_ar': 'رسالة وضع الصيانة'},
        
        # SEO Settings
        'seo_site_title': {'value': 'منصة المانجا - اقرأ المانجا والمانهوا مجاناً', 'type': 'string', 'category': 'seo',
                          'description': 'Default site title for SEO',
                          'description_ar': 'عنوان الموقع الافتراضي لمحركات البحث'},
        'seo_meta_description': {'value': 'منصة شاملة لقراءة المانجا والمانهوا باللغة العربية مجاناً. آلاف القصص المصورة عالية الجودة في مكان واحد', 'type': 'text', 'category': 'seo',
                                'description': 'Default meta description for homepage',
                                'description_ar': 'الوصف التعريفي الافتراضي للصفحة الرئيسية'},
        'seo_meta_keywords': {'value': 'مانجا, مانهوا, قراءة مانجا, مانجا عربية, manhwa, manga online', 'type': 'string', 'category': 'seo',
                             'description': 'Default meta keywords (comma separated)',
                             'description_ar': 'الكلمات المفتاحية الافتراضية (مفصولة بفواصل)'},
        'seo_robots_meta': {'value': 'index, follow', 'type': 'select', 'category': 'seo',
                           'options': ['index, follow', 'index, nofollow', 'noindex, follow', 'noindex, nofollow'],
                           'description': 'Default robots meta tag',
                           'description_ar': 'إعداد robots الافتراضي'},
        'seo_canonical_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                                 'description': 'Enable canonical URLs',
                                 'description_ar': 'تفعيل الروابط المعيارية'},
        'seo_og_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                          'description': 'Enable Open Graph meta tags',
                          'description_ar': 'تفعيل علامات Open Graph'},
        'seo_twitter_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                               'description': 'Enable Twitter Card meta tags',
                               'description_ar': 'تفعيل علامات Twitter Card'},
        'seo_schema_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                              'description': 'Enable JSON-LD structured data',
                              'description_ar': 'تفعيل البيانات المنظمة JSON-LD'},
        'seo_sitemap_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                               'description': 'Enable XML sitemap generation',
                               'description_ar': 'تفعيل إنشاء خريطة الموقع XML'},
        'seo_google_analytics': {'value': '', 'type': 'string', 'category': 'seo',
                               'description': 'Google Analytics tracking ID (GA-XXXXX or G-XXXXX)',
                               'description_ar': 'معرف تتبع Google Analytics'},
        'seo_google_tag_manager': {'value': '', 'type': 'string', 'category': 'seo',
                                 'description': 'Google Tag Manager container ID (GTM-XXXXX)',
                                 'description_ar': 'معرف حاوية Google Tag Manager'},
        'seo_facebook_app_id': {'value': '', 'type': 'string', 'category': 'seo',
                              'description': 'Facebook App ID for Open Graph',
                              'description_ar': 'معرف تطبيق فيسبوك لـ Open Graph'},
        'seo_twitter_username': {'value': '', 'type': 'string', 'category': 'seo',
                               'description': 'Twitter username (@username)',
                               'description_ar': 'اسم المستخدم في تويتر'},
        'seo_default_image': {'value': '/static/images/og-default.jpg', 'type': 'string', 'category': 'seo',
                            'description': 'Default Open Graph image URL',
                            'description_ar': 'رابط الصورة الافتراضية لـ Open Graph'},
        'seo_title_separator': {'value': ' | ', 'type': 'string', 'category': 'seo',
                              'description': 'Title separator (e.g., " | ", " - ", " :: ")',
                              'description_ar': 'فاصل العنوان'},
        'seo_breadcrumb_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                                 'description': 'Enable breadcrumb navigation',
                                 'description_ar': 'تفعيل مسار التنقل'},
        'seo_hreflang_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                               'description': 'Enable hreflang tags for multilingual content',
                               'description_ar': 'تفعيل علامات hreflang للمحتوى متعدد اللغات'},
        
        # Homepage Content Settings
        'homepage_hero_title_ar': {'value': 'اكتشف اللامحدود من المانجا والمانهوا', 'type': 'string', 'category': 'homepage',
                                  'description': 'Main hero title in Arabic',
                                  'description_ar': 'العنوان الرئيسي باللغة العربية'},
        'homepage_hero_title_en': {'value': 'Discover Unlimited Manga & Manhwa', 'type': 'string', 'category': 'homepage',
                                  'description': 'Main hero title in English',
                                  'description_ar': 'العنوان الرئيسي باللغة الإنجليزية'},
        'homepage_hero_subtitle_ar': {'value': 'أكبر منصة للمانجا والمانهوا في العالم', 'type': 'string', 'category': 'homepage',
                                     'description': 'Hero subtitle/badge in Arabic',
                                     'description_ar': 'العنوان الفرعي باللغة العربية'},
        'homepage_hero_subtitle_en': {'value': "World's Largest Manga & Manhwa Platform", 'type': 'string', 'category': 'homepage',
                                     'description': 'Hero subtitle/badge in English',
                                     'description_ar': 'العنوان الفرعي باللغة الإنجليزية'},
        'homepage_hero_description_ar': {'value': 'اقرأ آلاف المانجا والمانهوا والمانهوا عالية الجودة. تتبع تقدمك، احفظ المفضلة، واستمتع بتجربة مميزة خالية من الإعلانات.', 'type': 'text', 'category': 'homepage',
                                        'description': 'Hero description text in Arabic',
                                        'description_ar': 'النص الوصفي باللغة العربية'},
        'homepage_hero_description_en': {'value': 'Read thousands of high-quality manga, manhwa, and manhua series. Track your progress, bookmark favorites, and enjoy an ad-free premium experience.', 'type': 'text', 'category': 'homepage',
                                        'description': 'Hero description text in English',
                                        'description_ar': 'النص الوصفي باللغة الإنجليزية'},
        'homepage_cta_primary_ar': {'value': 'ابدأ القراءة', 'type': 'string', 'category': 'homepage',
                                   'description': 'Primary call-to-action button text in Arabic',
                                   'description_ar': 'نص زر الدعوة للعمل الرئيسي باللغة العربية'},
        'homepage_cta_primary_en': {'value': 'Start Reading', 'type': 'string', 'category': 'homepage',
                                   'description': 'Primary call-to-action button text in English',
                                   'description_ar': 'نص زر الدعوة للعمل الرئيسي باللغة الإنجليزية'},
        'homepage_cta_secondary_ar': {'value': 'انضم مجاناً', 'type': 'string', 'category': 'homepage',
                                     'description': 'Secondary call-to-action button text in Arabic',
                                     'description_ar': 'نص زر الدعوة للعمل الثانوي باللغة العربية'},
        'homepage_cta_secondary_en': {'value': 'Join Free', 'type': 'string', 'category': 'homepage',
                                     'description': 'Secondary call-to-action button text in English',
                                     'description_ar': 'نص زر الدعوة للعمل الثانوي باللغة الإنجليزية'},
        'homepage_stats_manga_count': {'value': '10K+', 'type': 'string', 'category': 'homepage',
                                      'description': 'Manga series count display',
                                      'description_ar': 'عدد سلاسل المانجا المعروض'},
        'homepage_stats_manga_label_ar': {'value': 'سلسلة مانجا', 'type': 'string', 'category': 'homepage',
                                         'description': 'Manga series label in Arabic',
                                         'description_ar': 'تسمية سلاسل المانجا باللغة العربية'},
        'homepage_stats_manga_label_en': {'value': 'Manga Series', 'type': 'string', 'category': 'homepage',
                                         'description': 'Manga series label in English',
                                         'description_ar': 'تسمية سلاسل المانجا باللغة الإنجليزية'},
        'homepage_stats_readers_count': {'value': '1M+', 'type': 'string', 'category': 'homepage',
                                        'description': 'Monthly readers count display',
                                        'description_ar': 'عدد القراء الشهري المعروض'},
        'homepage_stats_readers_label_ar': {'value': 'قارئ شهرياً', 'type': 'string', 'category': 'homepage',
                                           'description': 'Monthly readers label in Arabic',
                                           'description_ar': 'تسمية القراء الشهريين باللغة العربية'},
        'homepage_stats_readers_label_en': {'value': 'Monthly Readers', 'type': 'string', 'category': 'homepage',
                                           'description': 'Monthly readers label in English',
                                           'description_ar': 'تسمية القراء الشهريين باللغة الإنجليزية'},
        'homepage_stats_languages_count': {'value': '50+', 'type': 'string', 'category': 'homepage',
                                          'description': 'Languages count display',
                                          'description_ar': 'عدد اللغات المعروض'},
        'homepage_stats_languages_label_ar': {'value': 'لغة', 'type': 'string', 'category': 'homepage',
                                             'description': 'Languages label in Arabic',
                                             'description_ar': 'تسمية اللغات باللغة العربية'},
        'homepage_stats_languages_label_en': {'value': 'Languages', 'type': 'string', 'category': 'homepage',
                                             'description': 'Languages label in English',
                                             'description_ar': 'تسمية اللغات باللغة الإنجليزية'},
        'seo_page_speed_enabled': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                                 'description': 'Enable page speed optimizations',
                                 'description_ar': 'تفعيل تحسينات سرعة الصفحة'},
        'seo_lazy_loading': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                           'description': 'Enable lazy loading for images',
                           'description_ar': 'تفعيل التحميل التدريجي للصور'},
        'seo_preconnect_domains': {'value': 'fonts.googleapis.com, fonts.gstatic.com', 'type': 'string', 'category': 'seo',
                                 'description': 'Domains to preconnect (comma separated)',
                                 'description_ar': 'النطاقات للاتصال المسبق (مفصولة بفواصل)'},
        'seo_robots_txt': {'value': '''User-agent: *
Allow: /
Disallow: /admin/
Disallow: /user/
Disallow: /api/private/
Sitemap: /sitemap.xml''', 'type': 'textarea', 'category': 'seo',
                         'description': 'Robots.txt content',
                         'description_ar': 'محتوى ملف robots.txt'},
        'seo_custom_head': {'value': '', 'type': 'textarea', 'category': 'seo',
                          'description': 'Custom HTML to inject in <head>',
                          'description_ar': 'كود HTML مخصص لإدراجه في <head>'},
        'seo_custom_body_start': {'value': '', 'type': 'textarea', 'category': 'seo',
                                'description': 'Custom HTML to inject at start of <body>',
                                'description_ar': 'كود HTML مخصص لإدراجه في بداية <body>'},
        'seo_custom_body_end': {'value': '', 'type': 'textarea', 'category': 'seo',
                              'description': 'Custom HTML to inject at end of <body>',
                              'description_ar': 'كود HTML مخصص لإدراجه في نهاية <body>'},
        
        # Additional SEO Settings for Social Media
        'seo_og_title': {'value': '', 'type': 'string', 'category': 'seo',
                        'description': 'Custom Open Graph title (Facebook)',
                        'description_ar': 'عنوان فيسبوك المخصص'},
        'seo_og_description': {'value': '', 'type': 'textarea', 'category': 'seo',
                              'description': 'Custom Open Graph description (Facebook)',
                              'description_ar': 'وصف فيسبوك المخصص'},
        'seo_og_image': {'value': '', 'type': 'string', 'category': 'seo',
                        'description': 'Custom Open Graph image URL (Facebook)',
                        'description_ar': 'رابط صورة فيسبوك المخصصة'},
        'seo_twitter_card': {'value': 'summary_large_image', 'type': 'select', 'category': 'seo',
                            'options': ['summary', 'summary_large_image'],
                            'description': 'Twitter Card type',
                            'description_ar': 'نوع بطاقة تويتر'},
        'seo_twitter_site': {'value': '', 'type': 'string', 'category': 'seo',
                            'description': 'Twitter site account (@username)',
                            'description_ar': 'حساب الموقع في تويتر'},
        'seo_twitter_creator': {'value': '', 'type': 'string', 'category': 'seo',
                               'description': 'Twitter creator account (@username)',
                               'description_ar': 'حساب المؤلف في تويتر'},
        
        # Analytics and Verification Settings
        'seo_google_site_verification': {'value': '', 'type': 'string', 'category': 'seo',
                                        'description': 'Google Search Console verification code',
                                        'description_ar': 'رمز التحقق من Google Search Console'},
        'seo_bing_verification': {'value': '', 'type': 'string', 'category': 'seo',
                                 'description': 'Bing Webmaster Tools verification code',
                                 'description_ar': 'رمز التحقق من Bing Webmaster Tools'},
        'seo_yandex_verification': {'value': '', 'type': 'string', 'category': 'seo',
                                   'description': 'Yandex Webmaster verification code',
                                   'description_ar': 'رمز التحقق من Yandex Webmaster'},
        'seo_analytics_anonymize': {'value': 'false', 'type': 'boolean', 'category': 'seo',
                                   'description': 'Anonymize IP addresses in analytics',
                                   'description_ar': 'إخفاء هوية عناوين IP في التحليلات'},
        
        # Performance Optimization Settings
        'seo_dns_prefetch_domains': {'value': '//fonts.gstatic.com, //www.google-analytics.com', 'type': 'textarea', 'category': 'seo',
                                    'description': 'DNS prefetch domains (one per line)',
                                    'description_ar': 'نطاقات DNS prefetch (واحد في كل سطر)'},
        'seo_preload_critical_resources': {'value': 'true', 'type': 'boolean', 'category': 'seo',
                                          'description': 'Preload critical resources',
                                          'description_ar': 'تحميل الموارد المهمة مسبقاً'},
        'seo_minify_html': {'value': 'false', 'type': 'boolean', 'category': 'seo',
                           'description': 'Minify HTML output',
                           'description_ar': 'ضغط مخرجات HTML'},
        
        # Sitemap Settings
        'seo_sitemap_priority_home': {'value': '1.0', 'type': 'select', 'category': 'seo',
                                     'options': ['1.0', '0.9', '0.8', '0.7', '0.5'],
                                     'description': 'Homepage priority in sitemap',
                                     'description_ar': 'أولوية الصفحة الرئيسية في خريطة الموقع'},
        'seo_sitemap_changefreq': {'value': 'daily', 'type': 'select', 'category': 'seo',
                                  'options': ['always', 'hourly', 'daily', 'weekly', 'monthly', 'yearly', 'never'],
                                  'description': 'Default change frequency for sitemap',
                                  'description_ar': 'تكرار التحديث الافتراضي لخريطة الموقع'},
        
        # Appearance Settings
        'theme_color': {'value': '#007bff', 'type': 'string', 'category': 'appearance',
                       'description': 'Primary theme color',
                       'description_ar': 'اللون الأساسي للموقع'},
        'secondary_color': {'value': '#6c757d', 'type': 'string', 'category': 'appearance',
                           'description': 'Secondary theme color',
                           'description_ar': 'اللون الثانوي للموقع'},
        'logo_url': {'value': '', 'type': 'file', 'category': 'general',
                    'description': 'Site logo URL',
                    'description_ar': 'رابط شعار الموقع'},
        'favicon_url': {'value': '', 'type': 'string', 'category': 'appearance',
                       'description': 'Site favicon URL',
                       'description_ar': 'رابط أيقونة الموقع'},
        'hero_background': {'value': '', 'type': 'string', 'category': 'appearance',
                           'description': 'Hero section background image',
                           'description_ar': 'صورة خلفية القسم الرئيسي'},
        'show_view_counts': {'value': 'true', 'type': 'boolean', 'category': 'appearance',
                           'description': 'Display view counts on manga',
                           'description_ar': 'عرض عدد المشاهدات على المانجا'},
        'show_ratings': {'value': 'true', 'type': 'boolean', 'category': 'appearance',
                        'description': 'Display ratings on manga',
                        'description_ar': 'عرض التقييمات على المانجا'},
        'items_per_page': {'value': '20', 'type': 'integer', 'category': 'appearance',
                          'description': 'Number of items per page',
                          'description_ar': 'عدد العناصر في كل صفحة'},
        'enable_dark_mode': {'value': 'true', 'type': 'boolean', 'category': 'appearance',
                           'description': 'Enable dark mode toggle',
                           'description_ar': 'تفعيل تبديل الوضع المظلم'},
        
        # Footer Settings
        'footer_enabled': {'value': 'true', 'type': 'boolean', 'category': 'footer',
                          'description': 'Enable/disable footer display',
                          'description_ar': 'تفعيل/إلغاء تفعيل عرض الفوتر'},
        'footer_show_social_links': {'value': 'true', 'type': 'boolean', 'category': 'footer',
                                   'description': 'Show social media links in footer',
                                   'description_ar': 'عرض روابط وسائل التواصل في الفوتر'},
        'footer_show_quick_links': {'value': 'true', 'type': 'boolean', 'category': 'footer',
                                  'description': 'Show quick navigation links in footer',
                                  'description_ar': 'عرض روابط التنقل السريع في الفوتر'},
        'footer_copyright_text': {'value': '© 2024 منصة المانجا. جميع الحقوق محفوظة.', 'type': 'string', 'category': 'footer',
                                 'description': 'Copyright text (English)',
                                 'description_ar': 'نص حقوق النشر (بالإنجليزية)'},
        'footer_copyright_text_ar': {'value': '© 2024 منصة المانجا. جميع الحقوق محفوظة.', 'type': 'string', 'category': 'footer',
                                    'description': 'Copyright text (Arabic)',
                                    'description_ar': 'نص حقوق النشر (بالعربية)'},
        'footer_facebook_url': {'value': '', 'type': 'string', 'category': 'footer',
                               'description': 'Facebook page URL',
                               'description_ar': 'رابط صفحة فيسبوك'},
        'footer_twitter_url': {'value': '', 'type': 'string', 'category': 'footer',
                              'description': 'Twitter/X page URL',
                              'description_ar': 'رابط صفحة تويتر/إكس'},
        'footer_instagram_url': {'value': '', 'type': 'string', 'category': 'footer',
                                'description': 'Instagram page URL',
                                'description_ar': 'رابط صفحة إنستاغرام'},
        'footer_youtube_url': {'value': '', 'type': 'string', 'category': 'footer',
                              'description': 'YouTube channel URL',
                              'description_ar': 'رابط قناة يوتيوب'},
        'footer_discord_url': {'value': '', 'type': 'string', 'category': 'footer',
                              'description': 'Discord server URL',
                              'description_ar': 'رابط خادم ديسكورد'},
        'footer_telegram_url': {'value': '', 'type': 'string', 'category': 'footer',
                               'description': 'Telegram channel URL',
                               'description_ar': 'رابط قناة تلغرام'},
        'footer_about_page_url': {'value': '/about', 'type': 'string', 'category': 'footer',
                                 'description': 'About page URL',
                                 'description_ar': 'رابط صفحة حول الموقع'},
        'footer_privacy_policy_url': {'value': '/privacy-policy', 'type': 'string', 'category': 'footer',
                                     'description': 'Privacy policy page URL',
                                     'description_ar': 'رابط صفحة سياسة الخصوصية'},
        'footer_terms_of_service_url': {'value': '/terms-of-service', 'type': 'string', 'category': 'footer',
                                       'description': 'Terms of service page URL',
                                       'description_ar': 'رابط صفحة شروط الخدمة'},
        'footer_contact_page_url': {'value': '/contact', 'type': 'string', 'category': 'footer',
                                   'description': 'Contact page URL',
                                   'description_ar': 'رابط صفحة التواصل'},
        'footer_dmca_page_url': {'value': '/dmca', 'type': 'string', 'category': 'footer',
                                'description': 'DMCA page URL',
                                'description_ar': 'رابط صفحة DMCA'},
        'footer_help_page_url': {'value': '/help', 'type': 'string', 'category': 'footer',
                                'description': 'Help page URL',
                                'description_ar': 'رابط صفحة المساعدة'},
        'footer_custom_content': {'value': '', 'type': 'string', 'category': 'footer',
                                 'description': 'Custom HTML content for footer (English)',
                                 'description_ar': 'محتوى HTML مخصص للفوتر (بالإنجليزية)'},
        'footer_custom_content_ar': {'value': '', 'type': 'string', 'category': 'footer',
                                    'description': 'Custom HTML content for footer (Arabic)',
                                    'description_ar': 'محتوى HTML مخصص للفوتر (بالعربية)'},
        'footer_site_name': {'value': 'Global Manga Platform', 'type': 'string', 'category': 'footer',
                             'description': 'Site name in footer (English)',
                             'description_ar': 'اسم الموقع في الفوتر (بالإنجليزية)'},
        'footer_site_name_ar': {'value': 'منصة المانجا العالمية', 'type': 'string', 'category': 'footer',
                                'description': 'Site name in footer (Arabic)',
                                'description_ar': 'اسم الموقع في الفوتر (بالعربية)'},
        'footer_site_description': {'value': 'Your ultimate destination for manga, manhwa, and manhua reading.',
                                   'type': 'string', 'category': 'footer',
                                   'description': 'Site description in footer (English)',
                                   'description_ar': 'وصف الموقع في الفوتر (بالإنجليزية)'},
        'footer_site_description_ar': {'value': 'وجهتك المثلى لقراءة المانجا والمانهوا والمانهوا.',
                                      'type': 'string', 'category': 'footer',
                                      'description': 'Site description in footer (Arabic)',
                                      'description_ar': 'وصف الموقع في الفوتر (بالعربية)'},
        
        # Cloudinary Settings
        'cloudinary_enabled': {'value': 'true', 'type': 'boolean', 'category': 'cloudinary',
                              'description': 'Enable Cloudinary integration',
                              'description_ar': 'تفعيل تكامل Cloudinary'},
        'cloudinary_auto_switch': {'value': 'true', 'type': 'boolean', 'category': 'cloudinary',
                                  'description': 'Auto switch accounts when storage is full',
                                  'description_ar': 'التبديل التلقائي للحسابات عند امتلاء المساحة'},
        'cloudinary_storage_warning_threshold': {'value': '85', 'type': 'number', 'category': 'cloudinary',
                                                'description': 'Storage usage warning threshold (%)',
                                                'description_ar': 'حد التحذير لاستخدام المساحة (%)'},
        'cloudinary_backup_enabled': {'value': 'true', 'type': 'boolean', 'category': 'cloudinary',
                                     'description': 'Keep local backup of images',
                                     'description_ar': 'الاحتفاظ بنسخة احتياطية محلية للصور'},
        'cloudinary_usage_monitoring': {'value': 'true', 'type': 'boolean', 'category': 'cloudinary',
                                       'description': 'Enable usage monitoring and analytics',
                                       'description_ar': 'تفعيل مراقبة الاستخدام والتحليلات'},
        
        # Google OAuth Settings
        'google_oauth_enabled': {'value': 'true', 'type': 'boolean', 'category': 'authentication',
                               'description': 'Enable Google OAuth authentication',
                               'description_ar': 'تفعيل المصادقة بواسطة Google'},
        'google_oauth_client_id': {'value': '', 'type': 'string', 'category': 'authentication',
                                 'description': 'Google OAuth Client ID',
                                 'description_ar': 'معرف عميل Google OAuth'},
        'google_oauth_client_secret': {'value': '', 'type': 'string', 'category': 'authentication',
                                     'description': 'Google OAuth Client Secret',
                                     'description_ar': 'سر عميل Google OAuth'},
        'google_oauth_auto_register': {'value': 'true', 'type': 'boolean', 'category': 'authentication',
                                     'description': 'Automatically register new users from Google',
                                     'description_ar': 'تسجيل المستخدمين الجدد من Google تلقائياً'},
        'google_oauth_default_language': {'value': 'en', 'type': 'string', 'category': 'authentication',
                                        'description': 'Default language for Google OAuth users',
                                        'description_ar': 'اللغة الافتراضية لمستخدمي Google OAuth'},
        'google_oauth_redirect_url': {'value': '', 'type': 'string', 'category': 'authentication',
                                    'description': 'Google OAuth redirect URL (auto-generated)',
                                    'description_ar': 'رابط إعادة توجيه Google OAuth (يتم إنشاؤه تلقائياً)'},
        
        # Reading Settings
        'default_reading_mode': {'value': 'vertical', 'type': 'string', 'category': 'reading',
                               'description': 'Default reading mode (vertical/horizontal)',
                               'description_ar': 'وضع القراءة الافتراضي (عمودي/أفقي)'},
        'image_quality': {'value': 'high', 'type': 'string', 'category': 'reading',
                         'description': 'Default image quality (low/medium/high)',
                         'description_ar': 'جودة الصور الافتراضية (منخفضة/متوسطة/عالية)'},
        'allow_preloading': {'value': 'true', 'type': 'boolean', 'category': 'reading',
                           'description': 'Allow image preloading',
                           'description_ar': 'السماح بتحميل الصور مسبقاً'},
        'allow_fullscreen': {'value': 'true', 'type': 'boolean', 'category': 'reading',
                           'description': 'Allow fullscreen reading',
                           'description_ar': 'السماح بالقراءة في وضع ملء الشاشة'},
        'enable_keyboard_shortcuts': {'value': 'true', 'type': 'boolean', 'category': 'reading',
                                    'description': 'Enable keyboard shortcuts',
                                    'description_ar': 'تفعيل اختصارات لوحة المفاتيح'},
        'auto_scroll_speed': {'value': '2', 'type': 'integer', 'category': 'reading',
                             'description': 'Auto scroll speed (1-5)',
                             'description_ar': 'سرعة التمرير التلقائي (1-5)'},
        
        # Webtoon Settings
        'enable_webtoon_mode': {'value': 'true', 'type': 'boolean', 'category': 'reading',
                              'description': 'Enable webtoon reading mode',
                              'description_ar': 'تفعيل وضع قراءة الويبتون'},
        'webtoon_auto_height': {'value': 'true', 'type': 'boolean', 'category': 'reading',
                              'description': 'Auto-adjust webtoon panel height',
                              'description_ar': 'ضبط ارتفاع لوحة الويبتون تلقائياً'},
        'manhwa_default_mode': {'value': 'webtoon', 'type': 'string', 'category': 'reading',
                              'description': 'Default reading mode for manhwa',
                              'description_ar': 'وضع القراءة الافتراضي للمانهوا'},
        'webtoon_gap_size': {'value': '5', 'type': 'integer', 'category': 'reading',
                           'description': 'Gap size between webtoon panels (px)',
                           'description_ar': 'حجم الفجوة بين لوحات الويبتون (بكسل)'},
        'webtoon_max_width': {'value': '100', 'type': 'integer', 'category': 'reading',
                            'description': 'Maximum webtoon width percentage',
                            'description_ar': 'الحد الأقصى لعرض الويبتون بالنسبة المئوية'},
        
        # Content Settings
        'allow_user_uploads': {'value': 'false', 'type': 'boolean', 'category': 'content',
                             'description': 'Allow regular users to upload content',
                             'description_ar': 'السماح للمستخدمين العاديين برفع المحتوى'},
        'require_chapter_approval': {'value': 'true', 'type': 'boolean', 'category': 'content',
                                   'description': 'Require admin approval for new chapters',
                                   'description_ar': 'طلب موافقة المدير على الفصول الجديدة'},
        'max_upload_size': {'value': '100', 'type': 'integer', 'category': 'content',
                          'description': 'Maximum upload size in MB',
                          'description_ar': 'الحد الأقصى لحجم الرفع بالميجابايت'},
        'allowed_image_formats': {'value': 'jpg,jpeg,png,webp', 'type': 'string', 'category': 'content',
                                'description': 'Allowed image formats (comma separated)',
                                'description_ar': 'تنسيقات الصور المسموحة (مفصولة بفواصل)'},
        'auto_optimize_images': {'value': 'true', 'type': 'boolean', 'category': 'content',
                               'description': 'Automatically optimize uploaded images',
                               'description_ar': 'تحسين الصور المرفوعة تلقائياً'},
        'watermark_images': {'value': 'false', 'type': 'boolean', 'category': 'content',
                           'description': 'Add watermark to uploaded images',
                           'description_ar': 'إضافة علامة مائية على الصور المرفوعة'},
        'watermark_text': {'value': 'Manga Platform', 'type': 'string', 'category': 'content',
                          'description': 'Watermark text',
                          'description_ar': 'نص العلامة المائية'},
        
        # Security Settings
        'enable_rate_limiting': {'value': 'true', 'type': 'boolean', 'category': 'security',
                               'description': 'Enable rate limiting for API calls',
                               'description_ar': 'تفعيل تحديد معدل استدعاءات API'},
        'max_login_attempts': {'value': '5', 'type': 'integer', 'category': 'security',
                             'description': 'Maximum login attempts before lockout',
                             'description_ar': 'الحد الأقصى لمحاولات تسجيل الدخول قبل الحظر'},
        'session_timeout': {'value': '7200', 'type': 'integer', 'category': 'security',
                           'description': 'Session timeout in seconds',
                           'description_ar': 'انتهاء مهلة الجلسة بالثواني'},
        'require_email_verification': {'value': 'true', 'type': 'boolean', 'category': 'security',
                                     'description': 'Require email verification for new accounts',
                                     'description_ar': 'طلب تأكيد البريد الإلكتروني للحسابات الجديدة'},
        'enable_2fa': {'value': 'false', 'type': 'boolean', 'category': 'security',
                      'description': 'Enable two-factor authentication',
                      'description_ar': 'تفعيل المصادقة الثنائية'},
        
        # Advanced Settings
        'cache_enabled': {'value': 'true', 'type': 'boolean', 'category': 'advanced',
                         'description': 'Enable content caching',
                         'description_ar': 'تفعيل تخزين المحتوى مؤقتاً'},
        'cache_duration': {'value': '3600', 'type': 'integer', 'category': 'advanced',
                          'description': 'Cache duration in seconds',
                          'description_ar': 'مدة التخزين المؤقت بالثواني'},
        'enable_compression': {'value': 'true', 'type': 'boolean', 'category': 'advanced',
                             'description': 'Enable response compression',
                             'description_ar': 'تفعيل ضغط الاستجابات'},
        'debug_mode': {'value': 'false', 'type': 'boolean', 'category': 'advanced',
                      'description': 'Enable debug mode',
                      'description_ar': 'تفعيل وضع التصحيح'},
        'analytics_enabled': {'value': 'true', 'type': 'boolean', 'category': 'advanced',
                             'description': 'Enable analytics tracking',
                             'description_ar': 'تفعيل تتبع التحليلات'},
        'backup_frequency': {'value': 'daily', 'type': 'string', 'category': 'advanced',
                           'description': 'Backup frequency (daily/weekly/monthly)',
                           'description_ar': 'تكرار النسخ الاحتياطي (يومي/أسبوعي/شهري)'},
        'max_concurrent_users': {'value': '1000', 'type': 'integer', 'category': 'advanced',
                                'description': 'Maximum concurrent users',
                                'description_ar': 'الحد الأقصى للمستخدمين المتزامنين'},
    }
    
    @classmethod
    def get(cls, key, default=None):
        """Get setting value with caching"""
        if key in cls._cache:
            value = cls._cache[key]
            # Handle None values or string "None" for string fields
            if (value is None or value == "None" or value == 'None') and key in cls._default_settings:
                return cls._default_settings[key]['value']
            return value
        
        setting = SiteSetting.query.filter_by(key=key).first()
        if setting:
            value = setting.parsed_value
            # Handle None values or string "None" for string fields
            if (value is None or value == "None" or value == 'None') and key in cls._default_settings:
                value = cls._default_settings[key]['value']
            cls._cache[key] = value
            return value
        
        # Return default from _default_settings or provided default
        if key in cls._default_settings:
            return cls._default_settings[key]['value']
        return default
    
    @classmethod
    def set(cls, key, value, data_type='string', category='general', description='', description_ar=''):
        """Set setting value and update cache"""
        try:
            setting = SiteSetting.query.filter_by(key=key).first()
            
            if setting:
                setting.value = str(value)
                setting.data_type = data_type
                setting.category = category
                setting.description = description
                setting.description_ar = description_ar
            else:
                setting = SiteSetting()
                setting.key = key
                setting.value = str(value)
                setting.data_type = data_type
                setting.category = category
                setting.description = description
                setting.description_ar = description_ar
                db.session.add(setting)
            
            db.session.commit()
            cls._cache[key] = setting.parsed_value
            return setting
        except Exception as e:
            db.session.rollback()
            # Store in cache instead when database is read-only
            if 'setting' in locals() and 'setting' in locals() and hasattr(locals().get('setting'), 'parsed_value'):
                cls._cache[key] = setting.parsed_value
            else:
                cls._cache[key] = value
            logging.debug(f"Could not update setting '{key}' in database: {e}")
            return None
    
    @classmethod
    def get_category(cls, category):
        """Get all settings in a category"""
        settings = SiteSetting.query.filter_by(category=category).all()
        result = {}
        for setting in settings:
            result[setting.key] = setting.parsed_value
        return result
    
    @classmethod
    def get_all(cls):
        """Get all settings grouped by category"""
        settings = SiteSetting.query.all()
        result = {}
        for setting in settings:
            if setting.category not in result:
                result[setting.category] = {}
            result[setting.category][setting.key] = {
                'value': setting.parsed_value,
                'type': setting.data_type,
                'description': setting.description,
                'description_ar': setting.description_ar
            }
        return result
    
    @classmethod
    def initialize_defaults(cls):
        """Initialize default settings in database"""
        for key, config in cls._default_settings.items():
            existing = SiteSetting.query.filter_by(key=key).first()
            if not existing:
                setting = SiteSetting()
                setting.key = key
                setting.value = config['value']
                setting.data_type = config['type']
                setting.category = config['category']
                setting.description = config['description']
                setting.description_ar = config['description_ar']
                db.session.add(setting)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error initializing settings: {e}")
    
    @classmethod
    def clear_cache(cls):
        """Clear settings cache"""
        cls._cache.clear()
    
    @classmethod
    def export_settings(cls):
        """Export all settings as JSON"""
        settings = SiteSetting.query.all()
        export_data = {}
        for setting in settings:
            export_data[setting.key] = {
                'value': setting.value,
                'type': setting.data_type,
                'category': setting.category,
                'description': setting.description,
                'description_ar': setting.description_ar
            }
        return json.dumps(export_data, indent=2, ensure_ascii=False)
    
    @classmethod
    def import_settings(cls, json_data):
        """Import settings from JSON"""
        try:
            data = json.loads(json_data)
            for key, config in data.items():
                cls.set(
                    key=key,
                    value=config['value'],
                    data_type=config.get('type', 'string'),
                    category=config.get('category', 'general'),
                    description=config.get('description', ''),
                    description_ar=config.get('description_ar', '')
                )
            return True
        except Exception as e:
            logging.error(f"Error importing settings: {e}")
            return False

def get_setting(key, default=None):
    """Helper function to get setting value"""
    return SettingsManager.get(key, default)

def set_setting(key, value, **kwargs):
    """Helper function to set setting value"""
    return SettingsManager.set(key, value, **kwargs)