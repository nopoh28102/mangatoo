import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import random
import re

class SimpleMangaDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://olympustaff.com/'
        })
    
    def scrape_and_download_chapter(self, chapter_url, output_folder):
        """
        كشط وتحميل فصل كامل - الطريقة المبسطة الموحدة
        """
        try:
            os.makedirs(output_folder, exist_ok=True)
            
            print(f"🔍 جاري كشط الفصل من: {chapter_url}")
            
            response = self.session.get(chapter_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            chapter_title = self.extract_chapter_title(soup)
            print(f"📖 عنوان الفصل: {chapter_title}")
            
            image_urls = self.extract_image_urls(soup)
            
            if not image_urls:
                print("❌ لم يتم العثور على أي صور في هذا الفصل!")
                return {
                    'success': False,
                    'error': 'لم يتم العثور على صور',
                    'chapter_title': chapter_title,
                    'images_found': 0,
                    'downloaded_files': []
                }
            
            print(f"✅ تم العثور على {len(image_urls)} صورة")
            
            # تحميل الصور بالترتيب
            downloaded_files = []
            for i, img_url in enumerate(image_urls):
                try:
                    print(f"⬇️ تحميل الصورة {i+1}/{len(image_urls)}")
                    
                    img_response = self.session.get(img_url, stream=True, headers={'Referer': chapter_url})
                    img_response.raise_for_status()
                    
                    # تحديد اسم الملف مع الترقيم الصحيح
                    file_extension = self.get_file_extension(img_url)
                    filename = f"page_{i+1:03d}{file_extension}"
                    img_path = os.path.join(output_folder, filename)
                    
                    with open(img_path, 'wb') as f:
                        for chunk in img_response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # تحقق من حجم الملف
                    file_size = os.path.getsize(img_path)
                    if file_size > 1000:  # أكبر من 1KB
                        downloaded_files.append(img_path)
                        print(f"✅ تم تحميل: {filename} ({file_size} bytes)")
                    else:
                        print(f"⚠️ ملف صغير، سيتم حذفه: {filename}")
                        os.remove(img_path)
                    
                    # تأخير عشوائي لتجنب الحظر
                    time.sleep(random.uniform(0.1, 0.3))
                
                except Exception as img_error:
                    print(f"❌ خطأ في تحميل الصورة {i+1}: {img_error}")
            
            print(f"🎯 تم تحميل {len(downloaded_files)} من أصل {len(image_urls)} صورة بنجاح")
            
            return {
                'success': True,
                'error': None,
                'chapter_title': chapter_title,
                'images_found': len(image_urls),
                'downloaded_files': downloaded_files
            }
            
        except Exception as e:
            print(f"❌ حدث خطأ: {e}")
            return {
                'success': False,
                'error': str(e),
                'chapter_title': None,
                'images_found': 0,
                'downloaded_files': []
            }
    
    def extract_chapter_title(self, soup):
        """استخراج عنوان الفصل"""
        title_tag = soup.find('h1', class_='entry-title')
        if title_tag:
            return title_tag.text.strip()
        
        # جرب محددات أخرى
        for selector in ['h1', 'h2', '.title', '.chapter-title']:
            title_element = soup.select_one(selector)
            if title_element:
                return title_element.get_text().strip()
        
        return "فصل غير معروف"
    
    def extract_image_urls(self, soup):
        """استخراج روابط الصور من الصفحة"""
        images = []
        
        # البحث في div.entry-content img كما في الكود المرفق
        img_containers = soup.select('div.entry-content img')
        
        for img in img_containers:
            img_url = img.get('src') or img.get('data-src') or img.get('data-original')
            if img_url and not img_url.startswith('data:'):
                # تحويل الروابط النسبية إلى مطلقة
                if 'olympustaff.com' not in img_url:
                    img_url = urljoin('https://olympustaff.com/', img_url)
                
                # تأكد من أن الرابط يحتوي على صورة
                if any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                    images.append(img_url)
        
        # إذا لم نجد صور في entry-content، جرب جميع الصور
        if not images:
            all_images = soup.find_all('img')
            for img in all_images:
                img_url = img.get('src') or img.get('data-src')
                if img_url and 'olympustaff.com' in img_url:
                    if any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        images.append(img_url)
        
        # إزالة التكرارات مع الحفاظ على الترتيب
        unique_images = []
        seen_urls = set()
        for img_url in images:
            if img_url not in seen_urls:
                unique_images.append(img_url)
                seen_urls.add(img_url)
        
        return unique_images
    
    def get_file_extension(self, url):
        """تحديد امتداد الملف من الرابط"""
        if '.webp' in url.lower():
            return '.webp'
        elif '.png' in url.lower():
            return '.png'
        elif '.jpg' in url.lower() or '.jpeg' in url.lower():
            return '.jpg'
        else:
            return '.jpg'  # افتراضي

# دالة مساعدة للاستخدام في routes.py
def scrape_olympustaff_simple(chapter_url, output_folder):
    """
    دالة مبسطة لكشط وتحميل فصل من olympustaff
    """
    downloader = SimpleMangaDownloader()
    return downloader.scrape_and_download_chapter(chapter_url, output_folder)

def test_olympustaff_scraping(chapter_url):
    """
    دالة اختبار الكشط بدون تحميل للاستخدام في /admin/test-scrape
    """
    try:
        downloader = SimpleMangaDownloader()
        
        print(f"🧪 اختبار الكشط من: {chapter_url}")
        
        response = downloader.session.get(chapter_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        chapter_title = downloader.extract_chapter_title(soup)
        image_urls = downloader.extract_image_urls(soup)
        
        if not image_urls:
            return {
                'success': False,
                'error': 'لم يتم العثور على أي صور في هذا الفصل'
            }
        
        # إرجاع جميع الصور المكتشفة
        return {
            'success': True,
            'chapter_title': chapter_title or 'غير محدد',
            'total_images': len(image_urls),
            'sample_images': image_urls[:6],  # أول 6 صور للعرض السريع
            'all_images': image_urls  # جميع الصور للرفع الفعلي
        }
        
    except Exception as e:
        print(f"❌ خطأ في اختبار الكشط: {e}")
        return {
            'success': False,
            'error': f'خطأ في الاختبار: {str(e)}'
        }

# للاختبار المباشر
if __name__ == "__main__":
    downloader = SimpleMangaDownloader()
    
    chapter_url = input("الرجاء إدخال رابط الفصل الذي تريد تنزيله: ")
    output_folder = "downloads"
    
    result = downloader.scrape_and_download_chapter(chapter_url, output_folder)
    
    if result['success']:
        print(f"\n🎉 تم بنجاح!")
        print(f"📁 المجلد: {output_folder}")
        print(f"📄 الملفات المحملة: {len(result['downloaded_files'])}")
    else:
        print(f"\n💔 فشل: {result['error']}")