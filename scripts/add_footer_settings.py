#!/usr/bin/env python3
"""
Add Footer Settings to Database
This script adds footer configuration settings to the SiteSetting table.
"""

import os
import sys
from app import app, db
from models import SiteSetting

def add_footer_settings():
    """Add footer configuration settings"""
    with app.app_context():
        footer_settings = [
            # Footer Display Settings
            {
                'key': 'footer_enabled',
                'value': 'true',
                'data_type': 'boolean',
                'category': 'footer',
                'description': 'Enable/disable footer display',
                'description_ar': 'تفعيل/إلغاء تفعيل عرض الفوتر'
            },
            {
                'key': 'footer_copyright_text',
                'value': '© 2025 Manga Platform. All rights reserved.',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Copyright text in footer',
                'description_ar': 'نص حقوق الطبع والنشر في الفوتر'
            },
            {
                'key': 'footer_copyright_text_ar',
                'value': '© 2025 منصة المانجا. جميع الحقوق محفوظة.',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Arabic copyright text in footer',
                'description_ar': 'نص حقوق الطبع والنشر بالعربية في الفوتر'
            },
            
            # Social Media Links
            {
                'key': 'footer_facebook_url',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Facebook page URL',
                'description_ar': 'رابط صفحة الفيسبوك'
            },
            {
                'key': 'footer_twitter_url',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Twitter profile URL',
                'description_ar': 'رابط ملف تويتر'
            },
            {
                'key': 'footer_instagram_url',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Instagram profile URL',
                'description_ar': 'رابط ملف الانستجرام'
            },
            {
                'key': 'footer_youtube_url',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'YouTube channel URL',
                'description_ar': 'رابط قناة اليوتيوب'
            },
            {
                'key': 'footer_discord_url',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Discord server URL',
                'description_ar': 'رابط سيرفر الديسكورد'
            },
            {
                'key': 'footer_telegram_url',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Telegram channel URL',
                'description_ar': 'رابط قناة التليجرام'
            },
            
            # Footer Pages Links
            {
                'key': 'footer_about_page_url',
                'value': '/about',
                'data_type': 'string',
                'category': 'footer',
                'description': 'About page URL',
                'description_ar': 'رابط صفحة حول الموقع'
            },
            {
                'key': 'footer_privacy_policy_url',
                'value': '/privacy-policy',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Privacy Policy page URL',
                'description_ar': 'رابط صفحة سياسة الخصوصية'
            },
            {
                'key': 'footer_terms_of_service_url',
                'value': '/terms-of-service',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Terms of Service page URL',
                'description_ar': 'رابط صفحة شروط الخدمة'
            },
            {
                'key': 'footer_contact_page_url',
                'value': '/contact',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Contact page URL',
                'description_ar': 'رابط صفحة الاتصال'
            },
            {
                'key': 'footer_dmca_page_url',
                'value': '/dmca',
                'data_type': 'string',
                'category': 'footer',
                'description': 'DMCA page URL',
                'description_ar': 'رابط صفحة DMCA'
            },
            {
                'key': 'footer_help_page_url',
                'value': '/help',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Help/FAQ page URL',
                'description_ar': 'رابط صفحة المساعدة/الأسئلة الشائعة'
            },
            
            # Footer Sections Display
            {
                'key': 'footer_show_social_links',
                'value': 'true',
                'data_type': 'boolean',
                'category': 'footer',
                'description': 'Show social media links in footer',
                'description_ar': 'عرض روابط وسائل التواصل في الفوتر'
            },
            {
                'key': 'footer_show_quick_links',
                'value': 'true',
                'data_type': 'boolean',
                'category': 'footer',
                'description': 'Show quick links section in footer',
                'description_ar': 'عرض قسم الروابط السريعة في الفوتر'
            },
            {
                'key': 'footer_custom_content',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Custom HTML content for footer',
                'description_ar': 'محتوى HTML مخصص للفوتر'
            },
            {
                'key': 'footer_custom_content_ar',
                'value': '',
                'data_type': 'string',
                'category': 'footer',
                'description': 'Custom HTML content for footer (Arabic)',
                'description_ar': 'محتوى HTML مخصص للفوتر (العربية)'
            }
        ]
        
        added_count = 0
        for setting_data in footer_settings:
            # Check if setting already exists
            existing_setting = SiteSetting.query.filter_by(key=setting_data['key']).first()
            if not existing_setting:
                setting = SiteSetting(**setting_data)
                db.session.add(setting)
                added_count += 1
                print(f"Added setting: {setting_data['key']}")
            else:
                print(f"Setting already exists: {setting_data['key']}")
        
        try:
            db.session.commit()
            print(f"Successfully added {added_count} footer settings to database")
        except Exception as e:
            db.session.rollback()
            print(f"Error adding footer settings: {e}")
            return False
        
        return True

if __name__ == '__main__':
    print("Adding footer settings to database...")
    if add_footer_settings():
        print("Footer settings added successfully!")
    else:
        print("Failed to add footer settings.")
        sys.exit(1)