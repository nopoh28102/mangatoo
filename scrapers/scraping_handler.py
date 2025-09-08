"""
معالج كشط الصور للمواقع المختلفة
يحل مشكلة التحقق من الصور المكشوطة في النظام
"""
import os

def check_scraped_images():
    """
    فحص الصور المكشوطة في المجلد المؤقت
    إرجاع: قائمة بأسماء الصور الموجودة
    """
    temp_scraped_dir = os.path.join('static', 'uploads', 'temp_scraped')
    scraped_images = []
    
    try:
        if os.path.exists(temp_scraped_dir):
            all_files = os.listdir(temp_scraped_dir)
            scraped_images = [
                f for f in all_files 
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                and os.path.isfile(os.path.join(temp_scraped_dir, f))
            ]
            print(f"🔍 تم العثور على {len(scraped_images)} صورة مكشوطة في المجلد المؤقت")
            for img in scraped_images[:5]:  # عرض أول 5 صور
                print(f"  - {img}")
        else:
            print("📂 المجلد المؤقت للصور المكشوطة غير موجود")
            
    except Exception as e:
        print(f"⚠️ خطأ في فحص الصور المكشوطة: {e}")
        scraped_images = []
    
    return scraped_images

def perform_olympus_scraping(chapter_url):
    """
    كشط مباشر من موقع OlympusStaff
    """
    temp_scraped_dir = os.path.join('static', 'uploads', 'temp_scraped')
    
    try:
        # إنشاء المجلد وتنظيفه
        os.makedirs(temp_scraped_dir, exist_ok=True)
        
        # تنظيف المجلد من الصور القديمة
        for file in os.listdir(temp_scraped_dir):
            file_path = os.path.join(temp_scraped_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        
        print(f"📥 بدء كشط الصور من OlympusStaff: {chapter_url}")
        
        # كشط الصور
        from olympustaff_scraper import scrape_olympustaff_enhanced, download_olympustaff_images
        scrape_result = scrape_olympustaff_enhanced(chapter_url)
        
        if scrape_result['success'] and scrape_result['images']:
            downloaded_images = download_olympustaff_images(
                scrape_result['images'], 
                temp_scraped_dir, 
                chapter_url
            )
            
            print(f"✅ تم كشط وحفظ {len(downloaded_images)} صورة بنجاح")
            return {
                'success': True,
                'images_count': len(downloaded_images),
                'chapter_title': scrape_result.get('chapter_title', 'غير محدد'),
                'message': f'تم حفظ {len(downloaded_images)} صورة'
            }
        else:
            error_msg = scrape_result.get('error', 'خطأ غير محدد في الكشط')
            print(f"❌ فشل في كشط الصور: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }
            
    except Exception as e:
        error_msg = f"خطأ في عملية الكشط: {str(e)}"
        print(f"❌ خطأ في perform_olympus_scraping: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }

def validate_scraped_images_for_upload():
    """
    التحقق من صحة الصور المكشوطة للرفع
    """
    scraped_images = check_scraped_images()
    
    if not scraped_images:
        return {
            'valid': False,
            'message': 'لم يتم العثور على صور مكشوطة. يرجى كشط الصور أولاً.',
            'images_count': 0
        }
    
    return {
        'valid': True,
        'message': f'تم العثور على {len(scraped_images)} صورة جاهزة للرفع',
        'images_count': len(scraped_images),
        'images': scraped_images
    }