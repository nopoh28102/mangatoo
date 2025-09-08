"""
Bravo Mail integration utilities for sending emails
"""

import requests
import json
import logging
from typing import Dict, List, Optional, Any
try:
    from .utils_settings import SettingsManager
except ImportError:
    try:
        from app.utils_settings import SettingsManager
    except ImportError:
        # Fallback settings manager
        class SettingsManager:
            @staticmethod
            def get(key, default=None):
                return default

logger = logging.getLogger(__name__)

class BravoMailService:
    """Bravo Mail service integration"""
    
    def __init__(self):
        self.api_key = str(SettingsManager.get('bravo_mail_api_key', ''))
        self.api_url = str(SettingsManager.get('bravo_mail_api_url', 'https://api.bravo-mail.com/v1/'))
        self.sender_name = str(SettingsManager.get('bravo_mail_sender_name', 'منصة المانجا'))
        self.sender_email = str(SettingsManager.get('bravo_mail_sender_email', 'noreply@mangaplatform.com'))
        self.reply_to = str(SettingsManager.get('bravo_mail_reply_to', 'support@mangaplatform.com'))
        timeout_val = SettingsManager.get('bravo_mail_timeout', '30')
        self.timeout = int(timeout_val) if timeout_val and str(timeout_val).isdigit() else 30
        retries_val = SettingsManager.get('bravo_mail_max_retries', '3')
        self.max_retries = int(retries_val) if retries_val and str(retries_val).isdigit() else 3
        enabled_val = SettingsManager.get('bravo_mail_enabled', 'false')
        self.enabled = str(enabled_val).lower() == 'true' if enabled_val else False
    
    def is_enabled(self) -> bool:
        """Check if Bravo Mail is enabled and configured"""
        return self.enabled and bool(self.api_key)
    
    def get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'MangaPlatform/1.0'
        }
    
    def send_email(self, 
                   to_email: str, 
                   subject: str, 
                   html_body: str,
                   text_body: Optional[str] = None,
                   to_name: Optional[str] = None,
                   attachments: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Send email via Bravo Mail API
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
            to_name: Recipient name (optional)
            attachments: List of attachments (optional)
        
        Returns:
            Dict with success status and message
        """
        if not self.is_enabled():
            return {
                'success': False, 
                'error': 'Bravo Mail service is not enabled or configured'
            }
        
        # Prepare email data
        email_data = {
            'from': {
                'email': self.sender_email,
                'name': self.sender_name
            },
            'to': [{
                'email': to_email,
                'name': to_name or to_email
            }],
            'subject': subject,
            'html': html_body,
            'reply_to': {
                'email': self.reply_to,
                'name': self.sender_name
            }
        }
        
        if text_body:
            email_data['text'] = text_body
        
        if attachments:
            email_data['attachments'] = attachments
        
        # Send email with retries
        for attempt in range(self.max_retries):
            try:
                api_url = self.api_url.rstrip('/') if self.api_url else 'https://api.bravo-mail.com/v1'
                response = requests.post(
                    f"{api_url}/send",
                    headers=self.get_headers(),
                    json=email_data,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Email sent successfully to {to_email}")
                    return {
                        'success': True,
                        'message_id': result.get('id'),
                        'message': 'Email sent successfully'
                    }
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"Failed to send email (attempt {attempt + 1}): {error_msg}")
                    
                    if attempt == self.max_retries - 1:
                        return {
                            'success': False,
                            'error': error_msg
                        }
                        
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {str(e)}")
                if attempt == self.max_retries - 1:
                    return {
                        'success': False,
                        'error': f'Request failed: {str(e)}'
                    }
        
        return {
            'success': False,
            'error': 'Failed to send email after multiple attempts'
        }
    
    def send_bulk_email(self, recipients: List[Dict], subject: str, html_body: str, text_body: Optional[str] = None) -> Dict[str, Any]:
        """
        Send bulk email to multiple recipients
        
        Args:
            recipients: List of recipient dictionaries with 'email' and optional 'name'
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
        
        Returns:
            Dict with success status and results
        """
        if not self.is_enabled():
            return {
                'success': False, 
                'error': 'Bravo Mail service is not enabled or configured'
            }
        
        # Prepare bulk email data
        email_data = {
            'from': {
                'email': self.sender_email,
                'name': self.sender_name
            },
            'to': recipients,
            'subject': subject,
            'html': html_body,
            'reply_to': {
                'email': self.reply_to,
                'name': self.sender_name
            }
        }
        
        if text_body:
            email_data['text'] = text_body
        
        try:
            api_url = self.api_url.rstrip('/') if self.api_url else 'https://api.bravo-mail.com/v1'
            response = requests.post(
                f"{api_url}/send-bulk",
                headers=self.get_headers(),
                json=email_data,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Bulk email sent to {len(recipients)} recipients")
                return {
                    'success': True,
                    'sent_count': len(recipients),
                    'message': 'Bulk email sent successfully'
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"Failed to send bulk email: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Bulk email request failed: {str(e)}")
            return {
                'success': False,
                'error': f'Request failed: {str(e)}'
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """Test Bravo Mail API connection"""
        if not self.is_enabled():
            return {
                'success': False,
                'error': 'Bravo Mail service is not enabled or configured'
            }
        
        try:
            api_url = self.api_url.rstrip('/') if self.api_url else 'https://api.bravo-mail.com/v1'
            response = requests.get(
                f"{api_url}/account",
                headers=self.get_headers(),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                account_info = response.json()
                return {
                    'success': True,
                    'message': 'Connection successful',
                    'account_info': account_info
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Connection failed: {str(e)}'
            }

# Global instance
bravo_mail = BravoMailService()

# Email template functions
def send_contact_form_email(name: str, email: str, subject: str, message: str) -> Dict[str, Any]:
    """Send contact form email to admin"""
    admin_email = SettingsManager.get('admin_email', 'admin@mangaplatform.com')
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px;">رسالة جديدة من نموذج التواصل</h2>
            
            <div style="margin: 20px 0;">
                <p style="margin: 10px 0;"><strong>الاسم:</strong> {name}</p>
                <p style="margin: 10px 0;"><strong>البريد الإلكتروني:</strong> {email}</p>
                <p style="margin: 10px 0;"><strong>الموضوع:</strong> {subject}</p>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #495057; margin-top: 0;">الرسالة:</h3>
                <p style="line-height: 1.6; color: #6c757d;">{message}</p>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 20px 0;">
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                تم إرسال هذه الرسالة من نموذج التواصل في {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    رسالة جديدة من نموذج التواصل
    
    الاسم: {name}
    البريد الإلكتروني: {email}
    الموضوع: {subject}
    
    الرسالة:
    {message}
    
    ---
    تم إرسال هذه الرسالة من نموذج التواصل في {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=admin_email,
        subject=f"[{site_name}] رسالة جديدة من {name}",
        html_body=html_body,
        text_body=text_body,
        to_name="مدير الموقع"
    )

def send_user_verification_email(user_email: str, user_name: str, verification_code: str) -> Dict[str, Any]:
    """Send email verification to user"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #007bff; text-align: center; margin-bottom: 30px;">مرحباً بك في {site_name}</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">شكراً لك على التسجيل في منصتنا. لتفعيل حسابك، يرجى استخدام رمز التحقق التالي:</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <div style="background: #e3f2fd; padding: 20px; border-radius: 8px; display: inline-block;">
                    <h3 style="color: #1976d2; margin: 0; font-size: 24px; letter-spacing: 3px;">{verification_code}</h3>
                </div>
            </div>
            
            <p style="line-height: 1.6; color: #666;">هذا الرمز صالح لمدة 24 ساعة فقط.</p>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d;">
                إذا لم تقم بالتسجيل في موقعنا، يمكنك تجاهل هذه الرسالة.
            </p>
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    مرحباً بك في {site_name}
    
    عزيزي {user_name}،
    
    شكراً لك على التسجيل في منصتنا. لتفعيل حسابك، يرجى استخدام رمز التحقق التالي:
    
    {verification_code}
    
    هذا الرمز صالح لمدة 24 ساعة فقط.
    
    إذا لم تقم بالتسجيل في موقعنا، يمكنك تجاهل هذه الرسالة.
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] تفعيل الحساب - رمز التحقق",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_password_reset_email(user_email: str, user_name: str, temp_password: str) -> Dict[str, Any]:
    """Send temporary password to user"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #dc3545; text-align: center; margin-bottom: 30px;">إعادة تعيين كلمة المرور</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">تم إعادة تعيين كلمة مرورك بناءً على طلبك. كلمة المرور المؤقتة الجديدة هي:</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <div style="background: #fff3cd; border: 2px solid #ffc107; padding: 20px; border-radius: 8px; display: inline-block;">
                    <h3 style="color: #856404; margin: 0; font-size: 18px; font-family: monospace;">{temp_password}</h3>
                </div>
            </div>
            
            <div style="background: #d1ecf1; border: 1px solid #bee5eb; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 0; color: #0c5460;"><strong>مهم:</strong> يرجى تغيير كلمة المرور هذه فور تسجيل الدخول لضمان أمان حسابك.</p>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d;">
                إذا لم تطلب إعادة تعيين كلمة المرور، يرجى التواصل معنا فوراً.
            </p>
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    إعادة تعيين كلمة المرور - {site_name}
    
    عزيزي {user_name}،
    
    تم إعادة تعيين كلمة مرورك بناءً على طلبك. كلمة المرور المؤقتة الجديدة هي:
    
    {temp_password}
    
    مهم: يرجى تغيير كلمة المرور هذه فور تسجيل الدخول لضمان أمان حسابك.
    
    إذا لم تطلب إعادة تعيين كلمة المرور، يرجى التواصل معنا فوراً.
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] إعادة تعيين كلمة المرور",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_welcome_email(user_email: str, user_name: str) -> Dict[str, Any]:
    """Send welcome email to new users"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #28a745; text-align: center; margin-bottom: 30px;">مرحباً بك في {site_name}! 🎉</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">نرحب بك في منصتنا! نحن سعداء لانضمامك إلى مجتمعنا لمحبي المانجا والمانهوا.</p>
            
            <div style="background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #155724; margin-top: 0;">ماذا يمكنك فعله الآن:</h3>
                <ul style="line-height: 1.8; color: #155724;">
                    <li>تصفح مكتبتنا الضخمة من المانجا والمانهوا</li>
                    <li>إضافة المانجا المفضلة إلى قائمة المتابعة</li>
                    <li>ترك تعليقات وتقييمات للمحتوى</li>
                    <li>تخصيص ملفك الشخصي</li>
                    <li>الاشتراك في الإشعارات للفصول الجديدة</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="#" style="background: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    ابدأ التصفح الآن
                </a>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d;">
                إذا كان لديك أي أسئلة، لا تتردد في التواصل معنا. نحن هنا لمساعدتك!
            </p>
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    مرحباً بك في {site_name}!
    
    عزيزي {user_name}،
    
    نرحب بك في منصتنا! نحن سعداء لانضمامك إلى مجتمعنا لمحبي المانجا والمانهوا.
    
    ماذا يمكنك فعله الآن:
    • تصفح مكتبتنا الضخمة من المانجا والمانهوا
    • إضافة المانجا المفضلة إلى قائمة المتابعة
    • ترك تعليقات وتقييمات للمحتوى
    • تخصيص ملفك الشخصي
    • الاشتراك في الإشعارات للفصول الجديدة
    
    إذا كان لديك أي أسئلة، لا تتردد في التواصل معنا. نحن هنا لمساعدتك!
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] مرحباً بك في منصتنا! 🎉",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_notification_email(user_email: str, user_name: str, notification_title: str, notification_message: str, notification_link: str = None) -> Dict[str, Any]:
    """Send notification email to user"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    link_html = ""
    link_text = ""
    if notification_link:
        link_html = f"""
        <div style="text-align: center; margin: 20px 0;">
            <a href="{notification_link}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                عرض التفاصيل
            </a>
        </div>
        """
        link_text = f"\n\nللمزيد من التفاصيل: {notification_link}\n"
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #007bff; margin-bottom: 20px;">📢 {notification_title}</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">{notification_message}</p>
            
            {link_html}
            
            <hr style="border: 1px solid #dee2e6; margin: 20px 0;">
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    {notification_title}
    
    عزيزي {user_name}،
    
    {notification_message}
    {link_text}
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] {notification_title}",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_manga_chapter_notification(user_email: str, user_name: str, manga_title: str, chapter_title: str, chapter_url: str) -> Dict[str, Any]:
    """Send notification about new manga chapter"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #28a745; margin-bottom: 20px;">📚 فصل جديد متاح!</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">تم نشر فصل جديد من المانجا التي تتابعها:</p>
            
            <div style="background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; border-right: 4px solid #28a745;">
                <h3 style="color: #155724; margin: 0 0 10px 0;">{manga_title}</h3>
                <p style="color: #155724; margin: 0; font-size: 18px; font-weight: bold;">{chapter_title}</p>
            </div>
            
            <div style="text-align: center; margin: 25px 0;">
                <a href="{chapter_url}" style="background: #28a745; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    قراءة الفصل الآن
                </a>
            </div>
            
            <p style="font-size: 14px; color: #6c757d; line-height: 1.5;">
                لا تفوت الأحداث المثيرة! اقرأ الفصل الجديد الآن واستمتع بالمغامرة.
            </p>
            
            <hr style="border: 1px solid #dee2e6; margin: 20px 0;">
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    فصل جديد متاح!
    
    عزيزي {user_name}،
    
    تم نشر فصل جديد من المانجا التي تتابعها:
    
    المانجا: {manga_title}
    الفصل: {chapter_title}
    
    اقرأ الفصل الآن: {chapter_url}
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] فصل جديد: {manga_title} - {chapter_title}",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_premium_subscription_email(user_email: str, user_name: str, subscription_type: str, expiry_date: str) -> Dict[str, Any]:
    """Send premium subscription confirmation email"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #ffc107; text-align: center; margin-bottom: 30px;">⭐ تم تفعيل العضوية المدفوعة!</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">مبروك! تم تفعيل عضويتك المدفوعة بنجاح.</p>
            
            <div style="background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border: 2px solid #ffc107;">
                <h3 style="color: #856404; margin-top: 0;">تفاصيل الاشتراك:</h3>
                <p style="margin: 10px 0; color: #856404;"><strong>نوع الاشتراك:</strong> {subscription_type}</p>
                <p style="margin: 10px 0; color: #856404;"><strong>تاريخ الانتهاء:</strong> {expiry_date}</p>
            </div>
            
            <div style="background: #d4edda; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #155724; margin-top: 0;">مميزات العضوية المدفوعة:</h3>
                <ul style="line-height: 1.8; color: #155724;">
                    <li>قراءة الفصول المحجوبة والحصرية</li>
                    <li>إزالة الإعلانات من جميع الصفحات</li>
                    <li>الوصول المبكر للفصول الجديدة</li>
                    <li>مميزات خاصة في الملف الشخصي</li>
                    <li>دعم أولوية من فريق الدعم</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 25px 0;">
                <a href="#" style="background: #ffc107; color: #212529; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    استكشف المحتوى الحصري
                </a>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d;">
                شكراً لدعمك لمنصتنا! نتمنى لك تجربة رائعة مع المحتوى الحصري.
            </p>
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    تم تفعيل العضوية المدفوعة!
    
    عزيزي {user_name}،
    
    مبروك! تم تفعيل عضويتك المدفوعة بنجاح.
    
    تفاصيل الاشتراك:
    • نوع الاشتراك: {subscription_type}
    • تاريخ الانتهاء: {expiry_date}
    
    مميزات العضوية المدفوعة:
    • قراءة الفصول المحجوبة والحصرية
    • إزالة الإعلانات من جميع الصفحات
    • الوصول المبكر للفصول الجديدة
    • مميزات خاصة في الملف الشخصي
    • دعم أولوية من فريق الدعم
    
    شكراً لدعمك لمنصتنا! نتمنى لك تجربة رائعة مع المحتوى الحصري.
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] تم تفعيل العضوية المدفوعة! ⭐",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_payment_receipt_email(user_email: str, user_name: str, amount: str, payment_method: str, transaction_id: str) -> Dict[str, Any]:
    """Send payment receipt email"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #28a745; text-align: center; margin-bottom: 30px;">✅ إيصال الدفع</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">تم استلام دفعتك بنجاح. شكراً لك!</p>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #dee2e6;">
                <h3 style="color: #495057; margin-top: 0;">تفاصيل الدفعة:</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">المبلغ:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{amount}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">طريقة الدفع:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{payment_method}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">رقم المعاملة:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-family: monospace;">{transaction_id}</td>
                    </tr>
                </table>
            </div>
            
            <div style="background: #d1ecf1; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 0; color: #0c5460;">
                    <strong>ملاحظة:</strong> احتفظ بهذا الإيصال للمراجعة المستقبلية.
                </p>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d;">
                إذا كان لديك أي استفسارات حول هذه الدفعة، يرجى التواصل معنا.
            </p>
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    إيصال الدفع - {site_name}
    
    عزيزي {user_name}،
    
    تم استلام دفعتك بنجاح. شكراً لك!
    
    تفاصيل الدفعة:
    • المبلغ: {amount}
    • طريقة الدفع: {payment_method}
    • رقم المعاملة: {transaction_id}
    
    ملاحظة: احتفظ بهذا الإيصال للمراجعة المستقبلية.
    
    إذا كان لديك أي استفسارات حول هذه الدفعة، يرجى التواصل معنا.
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] إيصال دفعة - {amount}",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_translator_approval_email(user_email: str, user_name: str) -> Dict[str, Any]:
    """Send translator approval notification email"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #28a745; text-align: center; margin-bottom: 30px;">🎉 تم قبولك كمترجم!</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            <p style="line-height: 1.6;">مبروك! تم قبول طلبك للانضمام كمترجم في منصتنا.</p>
            
            <div style="background: #d4edda; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #155724; margin-top: 0;">صلاحياتك الجديدة:</h3>
                <ul style="line-height: 1.8; color: #155724;">
                    <li>إمكانية ترجمة الفصول والمانجا</li>
                    <li>الوصول إلى لوحة تحكم المترجم</li>
                    <li>إدارة مشاريع الترجمة الخاصة بك</li>
                    <li>التعاون مع فريق الترجمة</li>
                    <li>إمكانية رفع الترجمات الجديدة</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 25px 0;">
                <a href="#" style="background: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    ادخل إلى لوحة المترجم
                </a>
            </div>
            
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-right: 4px solid #ffc107;">
                <p style="margin: 0; color: #856404;">
                    <strong>ملاحظة:</strong> يرجى مراجعة إرشادات الترجمة وقواعد الجودة قبل البدء في العمل.
                </p>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d;">
                نتطلع للعمل معك وإثراء المحتوى العربي في منصتنا. مرحباً بك في فريق المترجمين!
            </p>
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    تم قبولك كمترجم!
    
    عزيزي {user_name}،
    
    مبروك! تم قبول طلبك للانضمام كمترجم في منصتنا.
    
    صلاحياتك الجديدة:
    • إمكانية ترجمة الفصول والمانجا
    • الوصول إلى لوحة تحكم المترجم
    • إدارة مشاريع الترجمة الخاصة بك
    • التعاون مع فريق الترجمة
    • إمكانية رفع الترجمات الجديدة
    
    ملاحظة: يرجى مراجعة إرشادات الترجمة وقواعد الجودة قبل البدء في العمل.
    
    نتطلع للعمل معك وإثراء المحتوى العربي في منصتنا. مرحباً بك في فريق المترجمين!
    
    فريق {site_name}
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] تم قبولك كمترجم! 🎉",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_bulk_notification_email(user_email: str, user_name: str, subject: str, message: str) -> Dict[str, Any]:
    """Send bulk notification email for marketing or announcements"""
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #007bff; text-align: center; margin-bottom: 30px;">{subject}</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
            
            <div style="line-height: 1.8; font-size: 16px; margin: 20px 0;">
                {message.replace(chr(10), '<br>')}
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="#" style="background: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    زيارة الموقع
                </a>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
            
            <p style="font-size: 12px; color: #adb5bd; text-align: center; margin-top: 20px;">
                إذا كنت لا تريد استلام هذه الرسائل، يمكنك إلغاء الاشتراك من إعدادات حسابك.
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    {subject}
    
    عزيزي {user_name}،
    
    {message}
    
    فريق {site_name}
    
    إذا كنت لا تريد استلام هذه الرسائل، يمكنك إلغاء الاشتراك من إعدادات حسابك.
    """
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=f"[{site_name}] {subject}",
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_translator_approval_email(user_email: str, user_name: str, approval_status: str) -> Dict[str, Any]:
    """Send translator approval/rejection email"""
    site_name = str(SettingsManager.get('site_name', 'منصة المانجا'))
    
    if approval_status == 'approved':
        html_body = f"""
        <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
            <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #28a745; text-align: center; margin-bottom: 30px;">🎉 تم قبول طلب الترجمة!</h2>
                
                <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
                <p style="line-height: 1.6;">مبروك! تم قبول طلبك للانضمام كمترجم في منصتنا.</p>
                
                <div style="background: #d4edda; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #155724; margin-top: 0;">صلاحياتك الجديدة:</h3>
                    <ul style="line-height: 1.8; color: #155724;">
                        <li>رفع المانجا والفصول الجديدة</li>
                        <li>تعديل معلومات المانجا الموجودة</li>
                        <li>الوصول لأدوات الترجمة المتقدمة</li>
                        <li>إدارة المحتوى المرفوع من قبلك</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 25px 0;">
                    <a href="#" style="background: #28a745; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                        الدخول لوحة المترجم
                    </a>
                </div>
                
                <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
                
                <p style="font-size: 14px; color: #6c757d; text-align: center;">
                    فريق {site_name}
                </p>
            </div>
        </div>
        """
        
        text_body = f"""
        تم قبول طلب الترجمة!
        
        عزيزي {user_name}،
        
        مبروك! تم قبول طلبك للانضمام كمترجم في منصتنا.
        
        صلاحياتك الجديدة:
        • رفع المانجا والفصول الجديدة
        • تعديل معلومات المانجا الموجودة
        • الوصول لأدوات الترجمة المتقدمة
        • إدارة المحتوى المرفوع من قبلك
        
        فريق {site_name}
        """
        
        subject = f"[{site_name}] تم قبول طلب الترجمة! 🎉"
    else:
        html_body = f"""
        <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
            <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #dc3545; text-align: center; margin-bottom: 30px;">طلب الترجمة</h2>
                
                <p style="font-size: 16px; line-height: 1.6;">عزيزي {user_name}،</p>
                <p style="line-height: 1.6;">نشكرك على اهتمامك بالانضمام كمترجم في منصتنا.</p>
                
                <div style="background: #f8d7da; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="color: #721c24; margin: 0;">للأسف، لم يتم قبول طلبك في الوقت الحالي. يمكنك التقديم مرة أخرى في المستقبل.</p>
                </div>
                
                <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
                
                <p style="font-size: 14px; color: #6c757d; text-align: center;">
                    فريق {site_name}
                </p>
            </div>
        </div>
        """
        
        text_body = f"""
        طلب الترجمة
        
        عزيزي {user_name}،
        
        نشكرك على اهتمامك بالانضمام كمترجم في منصتنا.
        
        للأسف، لم يتم قبول طلبك في الوقت الحالي. يمكنك التقديم مرة أخرى في المستقبل.
        
        فريق {site_name}
        """
        
        subject = f"[{site_name}] حالة طلب الترجمة"
    
    return bravo_mail.send_email(
        to_email=user_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        to_name=user_name
    )

def send_bulk_notification_email(recipients: List[Dict], title: str, message: str, action_url: str = None) -> Dict[str, Any]:
    """Send bulk notification email to multiple users"""
    site_name = str(SettingsManager.get('site_name', 'منصة المانجا'))
    
    action_html = ""
    action_text = ""
    if action_url:
        action_html = f"""
        <div style="text-align: center; margin: 25px 0;">
            <a href="{action_url}" style="background: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                عرض التفاصيل
            </a>
        </div>
        """
        action_text = f"\n\nللمزيد من التفاصيل: {action_url}\n"
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #007bff; margin-bottom: 20px;">📢 {title}</h2>
            
            <p style="line-height: 1.6;">{message}</p>
            
            {action_html}
            
            <hr style="border: 1px solid #dee2e6; margin: 20px 0;">
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    {title}
    
    {message}
    {action_text}
    فريق {site_name}
    """
    
    return bravo_mail.send_bulk_email(
        recipients=recipients,
        subject=f"[{site_name}] {title}",
        html_body=html_body,
        text_body=text_body
    )

def send_system_maintenance_email(recipients: List[Dict], maintenance_start: str, maintenance_end: str, reason: str) -> Dict[str, Any]:
    """Send system maintenance notification to users"""
    site_name = str(SettingsManager.get('site_name', 'منصة المانجا'))
    
    html_body = f"""
    <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #ffc107; text-align: center; margin-bottom: 30px;">⚠️ صيانة مجدولة للموقع</h2>
            
            <p style="font-size: 16px; line-height: 1.6;">عزيزي المستخدم،</p>
            <p style="line-height: 1.6;">نود إعلامك بأنه سيتم إجراء صيانة مجدولة للموقع:</p>
            
            <div style="background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border: 2px solid #ffc107;">
                <h3 style="color: #856404; margin-top: 0;">تفاصيل الصيانة:</h3>
                <p style="margin: 10px 0; color: #856404;"><strong>وقت البدء:</strong> {maintenance_start}</p>
                <p style="margin: 10px 0; color: #856404;"><strong>وقت الانتهاء المتوقع:</strong> {maintenance_end}</p>
                <p style="margin: 10px 0; color: #856404;"><strong>السبب:</strong> {reason}</p>
            </div>
            
            <div style="background: #d1ecf1; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 0; color: #0c5460;">
                    خلال فترة الصيانة، قد لا يكون الموقع متاحاً بشكل مؤقت. نعتذر عن أي إزعاج قد يحدث.
                </p>
            </div>
            
            <hr style="border: 1px solid #dee2e6; margin: 30px 0;">
            
            <p style="font-size: 14px; color: #6c757d; text-align: center;">
                فريق {site_name}
            </p>
        </div>
    </div>
    """
    
    text_body = f"""
    صيانة مجدولة للموقع
    
    عزيزي المستخدم،
    
    نود إعلامك بأنه سيتم إجراء صيانة مجدولة للموقع:
    
    تفاصيل الصيانة:
    • وقت البدء: {maintenance_start}
    • وقت الانتهاء المتوقع: {maintenance_end}
    • السبب: {reason}
    
    خلال فترة الصيانة، قد لا يكون الموقع متاحاً بشكل مؤقت. نعتذر عن أي إزعاج قد يحدث.
    
    فريق {site_name}
    """
    
    return bravo_mail.send_bulk_email(
        recipients=recipients,
        subject=f"[{site_name}] صيانة مجدولة للموقع ⚠️",
        html_body=html_body,
        text_body=text_body
    )

# Simple Email Queue System for bulk operations
class EmailQueue:
    """Simple in-memory email queue for bulk operations"""
    
    def __init__(self):
        self.queue = []
        self.processing = False
    
    def add_bulk_email(self, recipients: List[Dict], subject: str, html_body: str, text_body: str = None, priority: int = 1) -> str:
        """Add bulk email to queue"""
        import uuid
        from datetime import datetime
        
        job_id = str(uuid.uuid4())
        email_job = {
            'job_id': job_id,
            'type': 'bulk_email',
            'recipients': recipients,
            'subject': subject,
            'html_body': html_body,
            'text_body': text_body,
            'priority': priority,
            'created_at': datetime.now(),
            'status': 'queued',
            'attempts': 0,
            'max_attempts': 3
        }
        
        self.queue.append(email_job)
        # Sort queue by priority (higher priority first)
        self.queue.sort(key=lambda x: x['priority'], reverse=True)
        
        return job_id
    
    def add_single_email(self, to_email: str, subject: str, html_body: str, text_body: str = None, to_name: str = None, priority: int = 1) -> str:
        """Add single email to queue"""
        import uuid
        from datetime import datetime
        
        job_id = str(uuid.uuid4())
        email_job = {
            'job_id': job_id,
            'type': 'single_email',
            'to_email': to_email,
            'to_name': to_name,
            'subject': subject,
            'html_body': html_body,
            'text_body': text_body,
            'priority': priority,
            'created_at': datetime.now(),
            'status': 'queued',
            'attempts': 0,
            'max_attempts': 3
        }
        
        self.queue.append(email_job)
        # Sort queue by priority (higher priority first)
        self.queue.sort(key=lambda x: x['priority'], reverse=True)
        
        return job_id
    
    def process_queue(self) -> Dict[str, Any]:
        """Process email queue"""
        if self.processing or not self.queue:
            return {'success': False, 'message': 'Queue empty or already processing'}
        
        self.processing = True
        results = {
            'success': True,
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'job_results': []
        }
        
        try:
            jobs_to_process = [job for job in self.queue if job['status'] == 'queued']
            
            for job in jobs_to_process[:10]:  # Process max 10 jobs at a time
                try:
                    if job['type'] == 'bulk_email':
                        result = bravo_mail.send_bulk_email(
                            recipients=job['recipients'],
                            subject=job['subject'],
                            html_body=job['html_body'],
                            text_body=job['text_body']
                        )
                    else:  # single_email
                        result = bravo_mail.send_email(
                            to_email=job['to_email'],
                            subject=job['subject'],
                            html_body=job['html_body'],
                            text_body=job['text_body'],
                            to_name=job['to_name']
                        )
                    
                    if result['success']:
                        job['status'] = 'completed'
                        results['processed'] += 1
                    else:
                        job['attempts'] += 1
                        if job['attempts'] >= job['max_attempts']:
                            job['status'] = 'failed'
                            results['failed'] += 1
                        else:
                            job['status'] = 'retry'
                        
                    results['job_results'].append({
                        'job_id': job['job_id'],
                        'status': job['status'],
                        'attempts': job['attempts'],
                        'result': result
                    })
                    
                except Exception as e:
                    job['attempts'] += 1
                    if job['attempts'] >= job['max_attempts']:
                        job['status'] = 'failed'
                        results['failed'] += 1
                    else:
                        job['status'] = 'retry'
                    
                    results['job_results'].append({
                        'job_id': job['job_id'],
                        'status': job['status'],
                        'attempts': job['attempts'],
                        'error': str(e)
                    })
            
            # Clean up completed jobs older than 1 hour
            from datetime import datetime, timedelta
            cutoff_time = datetime.now() - timedelta(hours=1)
            self.queue = [job for job in self.queue if not (
                job['status'] == 'completed' and job['created_at'] < cutoff_time
            )]
            
            # Reset retry jobs to queued for next processing
            for job in self.queue:
                if job['status'] == 'retry':
                    job['status'] = 'queued'
            
        finally:
            self.processing = False
        
        return results
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        from collections import Counter
        
        status_counts = Counter(job['status'] for job in self.queue)
        
        return {
            'total_jobs': len(self.queue),
            'queued': status_counts.get('queued', 0),
            'processing': 1 if self.processing else 0,
            'completed': status_counts.get('completed', 0),
            'failed': status_counts.get('failed', 0),
            'retry': status_counts.get('retry', 0),
            'queue_processing': self.processing
        }
    
    def clear_completed_jobs(self) -> int:
        """Clear completed and failed jobs"""
        original_count = len(self.queue)
        self.queue = [job for job in self.queue if job['status'] not in ['completed', 'failed']]
        return original_count - len(self.queue)

# Global email queue instance
email_queue = EmailQueue()

def queue_bulk_email(recipients: List[Dict], subject: str, html_body: str, text_body: str = None, priority: int = 1) -> str:
    """Queue bulk email for later processing"""
    return email_queue.add_bulk_email(recipients, subject, html_body, text_body, priority)

def queue_single_email(to_email: str, subject: str, html_body: str, text_body: str = None, to_name: str = None, priority: int = 1) -> str:
    """Queue single email for later processing"""
    return email_queue.add_single_email(to_email, subject, html_body, text_body, to_name, priority)

def process_email_queue() -> Dict[str, Any]:
    """Process the email queue"""
    return email_queue.process_queue()

def get_email_queue_status() -> Dict[str, Any]:
    """Get email queue status"""
    return email_queue.get_queue_status()

def send_newsletter_welcome_email(email: str, language: str = 'ar') -> Dict[str, Any]:
    """Send welcome email to new newsletter subscriber"""
    try:
        from .utils_dynamic_urls import get_dynamic_url
        
        if language == 'ar':
            subject = "مرحباً بك في النشرة الإخبارية لمنصة المانجا"
            html_content = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: rtl; text-align: right;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">مرحباً بك في عائلة المانجا!</h1>
                </div>
                
                <div style="padding: 30px 20px; background-color: #f8f9fa;">
                    <h2 style="color: #333; margin-bottom: 20px;">أهلاً وسهلاً {email}</h2>
                    
                    <p style="color: #666; line-height: 1.6; font-size: 16px;">
                        شكراً لك على الاشتراك في النشرة الإخبارية لمنصة المانجا! 
                        ستحصل الآن على أحدث الأخبار والفصول الجديدة مباشرة في بريدك الإلكتروني.
                    </p>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 25px 0; border-right: 4px solid #667eea;">
                        <h3 style="color: #333; margin-top: 0;">ما ستحصل عليه:</h3>
                        <ul style="color: #666; line-height: 1.8;">
                            <li>إشعارات فورية عند نشر فصول جديدة للمانجا المتابعة</li>
                            <li>أخبار المانجا الجديدة والمثيرة</li>
                            <li>الإعلانات المهمة والتحديثات</li>
                            <li>ملخص أسبوعي للمحتوى الجديد</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{get_dynamic_url()}" style="background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            استكشف المنصة الآن
                        </a>
                    </div>
                    
                    <p style="color: #999; font-size: 14px; margin-top: 30px;">
                        يمكنك إلغاء الاشتراك في أي وقت من خلال النقر على الرابط في أسفل أي رسالة إلكترونية.
                    </p>
                </div>
            </div>
            """
            text_content = f"""
            مرحباً بك في النشرة الإخبارية لمنصة المانجا!
            
            أهلاً وسهلاً {email}
            
            شكراً لك على الاشتراك في النشرة الإخبارية! ستحصل الآن على:
            - إشعارات فورية عند نشر فصول جديدة
            - أخبار المانجا الجديدة
            - الإعلانات المهمة والتحديثات
            - ملخص أسبوعي للمحتوى الجديد
            
            يمكنك إلغاء الاشتراك في أي وقت.
            """
        else:
            subject = "Welcome to Manga Platform Newsletter"
            html_content = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: ltr; text-align: left;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">Welcome to Manga Family!</h1>
                </div>
                
                <div style="padding: 30px 20px; background-color: #f8f9fa;">
                    <h2 style="color: #333; margin-bottom: 20px;">Hello {email}</h2>
                    
                    <p style="color: #666; line-height: 1.6; font-size: 16px;">
                        Thank you for subscribing to Manga Platform newsletter! 
                        You'll now receive the latest news and new chapters directly in your inbox.
                    </p>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 4px solid #667eea;">
                        <h3 style="color: #333; margin-top: 0;">What you'll get:</h3>
                        <ul style="color: #666; line-height: 1.8;">
                            <li>Instant notifications for new chapters of followed manga</li>
                            <li>New and exciting manga announcements</li>
                            <li>Important announcements and updates</li>
                            <li>Weekly digest of new content</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{get_dynamic_url()}" style="background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            Explore Platform Now
                        </a>
                    </div>
                    
                    <p style="color: #999; font-size: 14px; margin-top: 30px;">
                        You can unsubscribe at any time by clicking the link at the bottom of any email.
                    </p>
                </div>
            </div>
            """
            text_content = f"""
            Welcome to Manga Platform Newsletter!
            
            Hello {email}
            
            Thank you for subscribing! You'll now receive:
            - Instant notifications for new chapters
            - New manga announcements
            - Important updates
            - Weekly content digest
            
            You can unsubscribe at any time.
            """
        
        return bravo_mail.send_email(
            recipient_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
    
    except Exception as e:
        logger.exception(f"Error sending newsletter welcome email to {email}: {e}")
        return {'success': False, 'error': str(e)}

def send_new_chapter_newsletter(chapter_id: int) -> Dict[str, Any]:
    """Send newsletter notification for new chapter to subscribers"""
    try:
        from .models import NewsletterSubscription, Chapter, Manga
        from .utils_dynamic_urls import get_dynamic_url
        from .app import db
        from datetime import datetime
        
        # Get chapter info
        chapter = Chapter.query.get(chapter_id)
        if not chapter:
            return {'success': False, 'error': 'Chapter not found'}
        
        manga = chapter.manga
        if not manga:
            return {'success': False, 'error': 'Manga not found'}
        
        # Get active newsletter subscribers who have new_chapters preference enabled
        subscribers = NewsletterSubscription.query.filter(
            NewsletterSubscription.is_active == True
        ).all()
        
        # Filter by preferences (handle JSON field carefully)
        active_subscribers = []
        for sub in subscribers:
            if sub.preferences and sub.preferences.get('new_chapters', True):
                active_subscribers.append(sub)
        
        if not active_subscribers:
            return {'success': True, 'message': 'No active subscribers found', 'sent_count': 0}
        
        sent_count = 0
        failed_count = 0
        
        for subscriber in active_subscribers:
            try:
                language = subscriber.language_preference or 'ar'
                
                if language == 'ar':
                    subject = f"فصل جديد: {manga.title_ar or manga.title} - الفصل {chapter.chapter_number}"
                    html_content = f"""
                    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: rtl; text-align: right;">
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px 20px; text-align: center;">
                            <h1 style="color: white; margin: 0; font-size: 24px;">فصل جديد متاح الآن!</h1>
                        </div>
                        
                        <div style="padding: 20px; background-color: #f8f9fa;">
                            <div style="background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                                <h2 style="color: #333; margin-top: 0;">{manga.title_ar or manga.title}</h2>
                                <p style="color: #667eea; font-size: 18px; margin: 10px 0;">الفصل {chapter.chapter_number}</p>
                                {f'<p style="color: #666; margin: 10px 0;"><strong>العنوان:</strong> {chapter.title}</p>' if chapter.title else ''}
                                
                                <div style="text-align: center; margin: 20px 0;">
                                    <a href="{get_dynamic_url()}/read/{manga.slug}/chapter-{chapter.chapter_number}" 
                                       style="background: #667eea; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                                        اقرأ الفصل الآن
                                    </a>
                                </div>
                            </div>
                            
                            <p style="color: #999; font-size: 14px; text-align: center;">
                                تم إرسال هذه الرسالة لأنك مشترك في النشرة الإخبارية.
                                <a href="{get_dynamic_url()}/newsletter/unsubscribe/{subscriber.unsubscribe_token}" style="color: #667eea;">إلغاء الاشتراك</a>
                            </p>
                        </div>
                    </div>
                    """
                    text_content = f"""
                    فصل جديد متاح الآن!
                    
                    {manga.title_ar or manga.title} - الفصل {chapter.chapter_number}
                    {f'العنوان: {chapter.title}' if chapter.title else ''}
                    
                    اقرأ الفصل: {get_dynamic_url()}/read/{manga.slug}/chapter-{chapter.chapter_number}
                    
                    إلغاء الاشتراك: {get_dynamic_url()}/newsletter/unsubscribe/{subscriber.unsubscribe_token}
                    """
                else:
                    subject = f"New Chapter: {manga.title} - Chapter {chapter.chapter_number}"
                    html_content = f"""
                    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: ltr; text-align: left;">
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px 20px; text-align: center;">
                            <h1 style="color: white; margin: 0; font-size: 24px;">New Chapter Available!</h1>
                        </div>
                        
                        <div style="padding: 20px; background-color: #f8f9fa;">
                            <div style="background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                                <h2 style="color: #333; margin-top: 0;">{manga.title}</h2>
                                <p style="color: #667eea; font-size: 18px; margin: 10px 0;">Chapter {chapter.chapter_number}</p>
                                {f'<p style="color: #666; margin: 10px 0;"><strong>Title:</strong> {chapter.title}</p>' if chapter.title else ''}
                                
                                <div style="text-align: center; margin: 20px 0;">
                                    <a href="{get_dynamic_url()}/read/{manga.slug}/chapter-{chapter.chapter_number}" 
                                       style="background: #667eea; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                                        Read Chapter Now
                                    </a>
                                </div>
                            </div>
                            
                            <p style="color: #999; font-size: 14px; text-align: center;">
                                You received this email because you're subscribed to our newsletter.
                                <a href="{get_dynamic_url()}/newsletter/unsubscribe/{subscriber.unsubscribe_token}" style="color: #667eea;">Unsubscribe</a>
                            </p>
                        </div>
                    </div>
                    """
                    text_content = f"""
                    New Chapter Available!
                    
                    {manga.title} - Chapter {chapter.chapter_number}
                    {f'Title: {chapter.title}' if chapter.title else ''}
                    
                    Read chapter: {get_dynamic_url()}/read/{manga.slug}/chapter-{chapter.chapter_number}
                    
                    Unsubscribe: {get_dynamic_url()}/newsletter/unsubscribe/{subscriber.unsubscribe_token}
                    """
                
                result = bravo_mail.send_email(
                    recipient_email=subscriber.email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )
                
                if result.get('success'):
                    sent_count += 1
                    # Update last email sent timestamp
                    subscriber.last_email_sent = datetime.utcnow()
                else:
                    failed_count += 1
                    logger.warning(f"Failed to send chapter notification to {subscriber.email}: {result}")
                
            except Exception as e:
                failed_count += 1
                logger.exception(f"Error sending chapter notification to {subscriber.email}: {e}")
        
        # Commit database changes
        db.session.commit()
        
        return {
            'success': True,
            'message': f'Newsletter sent to {sent_count} subscribers',
            'sent_count': sent_count,
            'failed_count': failed_count,
            'chapter_title': f"{manga.title} - Chapter {chapter.chapter_number}"
        }
        
    except Exception as e:
        logger.exception(f"Error sending new chapter newsletter for chapter {chapter_id}: {e}")
        return {'success': False, 'error': str(e)}