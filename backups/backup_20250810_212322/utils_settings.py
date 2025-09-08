"""
Settings management utilities for the manga platform
"""

from app import db
from models import SiteSetting
import json

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
        
        # Appearance Settings
        'theme_color': {'value': '#007bff', 'type': 'string', 'category': 'appearance',
                       'description': 'Primary theme color',
                       'description_ar': 'اللون الأساسي للموقع'},
        'secondary_color': {'value': '#6c757d', 'type': 'string', 'category': 'appearance',
                           'description': 'Secondary theme color',
                           'description_ar': 'اللون الثانوي للموقع'},
        'logo_url': {'value': '', 'type': 'string', 'category': 'appearance',
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
        setting = SiteSetting.query.filter_by(key=key).first()
        
        if setting:
            setting.value = str(value)
            setting.data_type = data_type
            setting.category = category
            setting.description = description
            setting.description_ar = description_ar
        else:
            setting = SiteSetting(
                key=key,
                value=str(value),
                data_type=data_type,
                category=category,
                description=description,
                description_ar=description_ar
            )
            db.session.add(setting)
        
        db.session.commit()
        cls._cache[key] = setting.parsed_value
        return setting
    
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
                setting = SiteSetting(
                    key=key,
                    value=config['value'],
                    data_type=config['type'],
                    category=config['category'],
                    description=config['description'],
                    description_ar=config['description_ar']
                )
                db.session.add(setting)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error initializing settings: {e}")
    
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
            print(f"Error importing settings: {e}")
            return False

def get_setting(key, default=None):
    """Helper function to get setting value"""
    return SettingsManager.get(key, default)

def set_setting(key, value, **kwargs):
    """Helper function to set setting value"""
    return SettingsManager.set(key, value, **kwargs)