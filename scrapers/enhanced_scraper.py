import os
import re
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
import hashlib
from PIL import Image


def generate_possible_hash(page_num, chapter_num):
    """
    توليد hash محتمل للصفحة (محاولة تخمين نمط olympustaff)
    """
    # أنماط hash محتملة
    base_strings = [
        f"{page_num}_{chapter_num}",
        f"page_{page_num}_chapter_{chapter_num}",
        f"{chapter_num}_{page_num}",
        f"img_{page_num}_{chapter_num}",
    ]
    
    for base in base_strings:
        # جرب hash algorithms مختلفة
        hashes = [
            hashlib.md5(base.encode()).hexdigest(),
            hashlib.md5(base.encode()).hexdigest()[:8],
            hashlib.md5(base.encode()).hexdigest()[:16],
            hashlib.md5(base.encode()).hexdigest()[:32],
        ]
        
        for h in hashes:
            if len(h) == 32:  # MD5 32 character hash كما في المثال
                return h
    
    return f"{page_num:02d}"


def extract_olympustaff_hash_images(base_url, headers, chapter_num):
    """
    محاولة استخراج الصور بنمط hash من olympustaff
    """
    image_urls = []
    
    # بما أن نمط hash صعب التنبؤ، نحتاج لطريقة أخرى
    # محاولة فحص صفحة الفصل للحصول على روابط الصور الفعلية
    chapter_url = f"https://olympustaff.com/series/return-from-the-depths/{chapter_num}"
    
    try:
        response = requests.get(chapter_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # البحث في JavaScript عن مصفوفة الصور
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    script_content = script.string
                    # البحث عن أنماط مختلفة للصور
                    patterns = [
                        r'images\s*:\s*\[(.*?)\]',
                        r'pages\s*:\s*\[(.*?)\]',
                        r'"([^"]*manga_ce514[^"]*\.webp)"',
                        r"'([^']*manga_ce514[^']*\.webp)'",
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, script_content, re.DOTALL)
                        for match in matches:
                            if 'manga_ce514' in match:
                                # استخراج جميع روابط الصور من النص
                                urls = re.findall(r'["\']([^"\']*manga_ce514[^"\']*\.webp)["\']', match)
                                for url in urls:
                                    if url.startswith('/'):
                                        url = 'https://olympustaff.com' + url
                                    image_urls.append(url)
                                    
                                if image_urls:
                                    return image_urls
    except:
        pass
    
    return image_urls


def scrape_olympustaff(chapter_url):
    """
    كاشط مخصص لموقع olympustaff.com
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(chapter_url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # محاولة إصلاح مشكلة الترميز
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')
        
        # استخراج عنوان الفصل
        title_selectors = [
            'h1', 'h2', '.title', '.chapter-title', 
            '.page-title', '.entry-title'
        ]
        
        for selector in title_selectors:
            title_element = soup.select_one(selector)
            if title_element and title_element.get_text().strip():
                scraped_data['chapter_title'] = title_element.get_text().strip()
                break
        
        # البحث عن الصور في أنماط مختلفة
        image_urls = []
        
        # البحث في عناصر img مختلفة
        images = soup.find_all('img')
        for img in images:
            src_attrs = ['src', 'data-src', 'data-original', 'data-lazy-src']
            for attr in src_attrs:
                src = img.get(attr)
                if src and 'olympustaff.com' in src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(chapter_url, src)
                    image_urls.append(src)
                    break
        
        # البحث الذكي في JavaScript للصور
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'manga_ce514' in script.string:
                script_content = script.string
                # البحث عن أنماط الصور المحددة
                patterns = [
                    r'"(https://olympustaff\.com/uploads/manga_ce514/\d+/[^"]+\.webp)"',
                    r"'(https://olympustaff\.com/uploads/manga_ce514/\d+/[^']+\.webp)'",
                    r'"(/uploads/manga_ce514/\d+/[^"]+\.webp)"',
                    r"'(/uploads/manga_ce514/\d+/[^']+\.webp)'",
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, script_content)
                    for match in matches:
                        url = match.strip('\'"')
                        if url.startswith('/'):
                            url = 'https://olympustaff.com' + url
                        if url not in image_urls:
                            image_urls.append(url)
                
                if image_urls:
                    print(f"عُثر على {len(image_urls)} صورة في JavaScript")
                    break
        
        # إذا لم نجد صور، جرب أساليب أكثر ذكاء
        if not image_urls:
            print("جاري البحث عن الصور في olympustaff...")
            
            # تحليل الرابط لاستخراج معلومات الفصل
            url_parts = chapter_url.split('/')
            series_name = None
            chapter_num = None
            
            for i, part in enumerate(url_parts):
                if part == 'series' and i + 1 < len(url_parts):
                    series_name = url_parts[i + 1]
                elif part.isdigit():
                    chapter_num = part
            
            print(f"معرف السلسلة: {series_name}, رقم الفصل: {chapter_num}")
            
            if series_name and chapter_num:
                # جرب أولاً النمط المحدد من المستخدم
                manga_id = 'manga_ce514'
                print(f"اختبار النمط الأساسي: {manga_id}")
                base_url = f'https://olympustaff.com/uploads/{manga_id}/{chapter_num}/'
                
                # فحص سريع للملف الأول
                test_formats = [
                    ('82738e304153e6dcdc038a3fb020d9db', '.webp'),  # نمط hash من المثال
                    ('01', '.webp'),
                    ('1', '.webp'),
                ]
                
                for name, ext in test_formats:
                    test_url = f'{base_url}{name}{ext}'
                    try:
                        test_response = requests.head(test_url, headers=headers, timeout=3)
                        if test_response.status_code == 200:
                            print(f"✓ وُجد النمط الصحيح: {name}{ext}")
                            
                            # إذا كان hash، جرب تخمين المزيد
                            if len(name) == 32:  # hash format
                                # استخراج جميع الصور بنمط hash مشابه
                                image_urls.extend(extract_olympustaff_hash_images(base_url, headers, chapter_num))
                            else:
                                # إذا كان رقم عادي، استخرج بنمط الأرقام
                                for page_num in range(1, 31):
                                    page_formats = [f'{page_num:02d}', f'{page_num}']
                                    for fmt in page_formats:
                                        page_url = f'{base_url}{fmt}{ext}'
                                        try:
                                            resp = requests.head(page_url, headers=headers, timeout=2)
                                            if resp.status_code == 200:
                                                image_urls.append(page_url)
                                                print(f"✓ صفحة {page_num}")
                                                break
                                        except:
                                            continue
                                    if page_num > 5 and len(image_urls) == 0:
                                        break
                            break
                    except:
                        continue
        
        # إذا ما زلنا لم نجد صور، جرب استخراج من source code للصفحة
        if not image_urls:
            # تحقق من وجود viewer للصور في الصفحة
            viewer_patterns = [
                r'viewer.*?images?\s*[=:]\s*\[([^\]]+)\]',
                r'pages?\s*[=:]\s*\[([^\]]+)\]',
                r'chapter.*?images?\s*[=:]\s*\[([^\]]+)\]',
            ]
            
            page_content = str(soup)
            for pattern in viewer_patterns:
                matches = re.findall(pattern, page_content, re.IGNORECASE | re.DOTALL)
                if matches:
                    image_data = matches[0]
                    # استخراج روابط الصور من البيانات
                    url_matches = re.findall(r'["\']([^"\']+\.(?:webp|jpg|jpeg|png))["\']', image_data)
                    for url in url_matches:
                        if not url.startswith('http'):
                            url = urljoin(chapter_url, url)
                        image_urls.append(url)
        
        # ترتيب الصور حسب الرقم في الرابط
        if image_urls:
            def extract_page_number(url):
                numbers = re.findall(r'/(\d+)\.', url)
                if numbers:
                    return int(numbers[-1])
                numbers = re.findall(r'page_(\d+)', url)
                if numbers:
                    return int(numbers[-1])
                numbers = re.findall(r'/(\d+)/', url)
                if numbers:
                    return int(numbers[-1])
                return 999999
            
            image_urls = sorted(set(image_urls), key=extract_page_number)
            scraped_data['images'] = image_urls
            scraped_data['success'] = True
            print(f"تم العثور على {len(image_urls)} صورة من olympustaff")
        else:
            scraped_data['error'] = 'لم يتم العثور على صور في الصفحة'
            
    except requests.RequestException as e:
        scraped_data['error'] = f'خطأ في الوصول للموقع: {str(e)}'
    except Exception as e:
        scraped_data['error'] = f'خطأ في معالجة الصفحة: {str(e)}'
        import traceback
        print(f"خطأ مفصل: {traceback.format_exc()}")
    
    return scraped_data


def scrape_enhanced_generic_site(chapter_url):
    """
    محسن: كشط عام للمواقع غير المعروفة مع ترتيب أفضل للصور
    """
    scraped_data = {
        'success': False,
        'images': [],
        'chapter_title': None,
        'error': None
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(chapter_url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # جلب عنوان الفصل
        title_selectors = [
            'h1.chapter-title', 'h1.title', '.chapter-title h1', '.title h1',
            'h1', 'h2.chapter-title', 'h2.title', 
            '.panel-chapter-info-top h1', '.chapter-header h1',
            '[class*="chapter"][class*="title"] h1', '[class*="title"] h1'
        ]
        
        for selector in title_selectors:
            title_element = soup.select_one(selector)
            if title_element and title_element.get_text().strip():
                scraped_data['chapter_title'] = title_element.get_text().strip()
                break
        
        # البحث عن حاوي الصور الرئيسي
        main_content_selectors = [
            '.chapter-content', '.reading-content', '.page-break',
            '.chapter-images', '.manga-images', '.pages',
            '.reader-content', '.chapter-body', '.content',
            '#chapter-content', '#reading-content', '#pages',
            '[class*="chapter"][class*="content"]', '[class*="reading"][class*="content"]',
            '[class*="page"][class*="container"]'
        ]
        
        main_container = None
        for selector in main_content_selectors:
            container = soup.select_one(selector)
            if container:
                # تحقق من وجود صور داخل الحاوي
                images_in_container = container.find_all('img')
                if len(images_in_container) > 0:
                    main_container = container
                    break
        
        # إذا لم نجد حاوي محدد، استخدم الصفحة كاملة
        if not main_container:
            main_container = soup
        
        # جمع الصور مع معلومات إضافية للترتيب
        image_candidates = []
        
        # البحث في الصور المرئية والمخفية
        images = main_container.find_all('img')
        
        for img in images:
            # جلب جميع مصادر الصور المحتملة
            sources = [
                img.get('src'),
                img.get('data-src'),
                img.get('data-original'),
                img.get('data-lazy-src'),
                img.get('data-srcset'),
                img.get('data-echo'),
                img.get('data-url')
            ]
            
            for src in sources:
                if src and is_manga_page_image(src, img):
                    # تحويل الرابط إلى مطلق
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(chapter_url, src)
                    elif not src.startswith('http'):
                        src = urljoin(chapter_url, src)
                    
                    # جلب معلومات إضافية للترتيب
                    img_info = extract_image_order_info(img, src)
                    image_candidates.append({
                        'url': src,
                        'order': img_info['order'],
                        'element': img,
                        'dom_position': len(image_candidates)
                    })
                    break
        
        # ترتيب الصور حسب الترتيب المستخرج ثم الموضع في الصفحة
        image_candidates.sort(key=lambda x: (x['order'], x['dom_position']))
        
        # إزالة الصور المكررة والمشبوهة
        seen_urls = set()
        for img_data in image_candidates:
            url = img_data['url']
            if url not in seen_urls and is_valid_manga_image_url(url):
                scraped_data['images'].append(url)
                seen_urls.add(url)
        
        # إذا لم نجد صور كافية، جرب البحث في JavaScript أو البيانات المخفية
        if len(scraped_data['images']) < 3:
            js_images = extract_images_from_scripts(soup, chapter_url)
            for img_url in js_images:
                if img_url not in seen_urls:
                    scraped_data['images'].append(img_url)
                    seen_urls.add(img_url)
        
        if scraped_data['images']:
            scraped_data['success'] = True
            print(f"تم العثور على {len(scraped_data['images'])} صورة من {chapter_url}")
        else:
            scraped_data['error'] = 'لم يتم العثور على صور في الصفحة'
            
    except requests.RequestException as e:
        scraped_data['error'] = f'خطأ في الوصول للموقع: {str(e)}'
    except Exception as e:
        scraped_data['error'] = f'خطأ في معالجة الصفحة: {str(e)}'
        import traceback
        print(f"خطأ مفصل: {traceback.format_exc()}")
    
    return scraped_data


def is_manga_page_image(src, img_element):
    """
    تحقق محسن من كون الصورة صفحة مانجا حقيقية
    """
    if not src:
        return False
    
    # تحقق من امتداد الصورة
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    if not any(ext in src.lower() for ext in image_extensions):
        return False
    
    # تخطي الصور الشائعة غير المرتبطة بالمانجا
    skip_patterns = [
        'logo', 'banner', 'ad', 'advertisement', 'avatar', 'icon', 'button', 
        'bg', 'background', 'thumb', 'thumbnail', 'preview', 'cover',
        'header', 'footer', 'nav', 'menu', 'sidebar', 'widget',
        'comment', 'user', 'profile', 'social', 'share'
    ]
    
    src_lower = src.lower()
    if any(pattern in src_lower for pattern in skip_patterns):
        return False
    
    # تحقق من أبعاد الصورة إذا كانت متاحة
    width = img_element.get('width')
    height = img_element.get('height')
    
    if width and height:
        try:
            w, h = int(width), int(height)
            # تخطي الصور الصغيرة جداً (أقل من 200x200)
            if w < 200 or h < 200:
                return False
            # تخطي الصور المربعة الصغيرة (غالباً أيقونات)
            if w == h and w < 300:
                return False
        except (ValueError, TypeError):
            pass
    
    # تحقق من الفئات والمعرفات في العنصر
    element_class = img_element.get('class', [])
    element_id = img_element.get('id', '')
    
    if isinstance(element_class, list):
        element_class = ' '.join(element_class)
    
    element_attrs = f"{element_class} {element_id}".lower()
    
    # فئات إيجابية تشير لصور المانجا
    positive_patterns = [
        'page', 'chapter', 'manga', 'comic', 'scan', 'image',
        'content', 'reader', 'reading'
    ]
    
    # فئات سلبية يجب تجنبها
    negative_patterns = [
        'ad', 'banner', 'logo', 'avatar', 'thumb', 'icon',
        'button', 'nav', 'menu', 'sidebar', 'footer', 'header'
    ]
    
    has_positive = any(pattern in element_attrs for pattern in positive_patterns)
    has_negative = any(pattern in element_attrs for pattern in negative_patterns)
    
    if has_negative:
        return False
    
    return True


def extract_image_order_info(img_element, src):
    """
    استخراج معلومات الترتيب من عنصر الصورة
    """
    order_info = {
        'order': 999999,  # ترتيب افتراضي عالي
        'page_num': None
    }
    
    # البحث عن رقم الصفحة في رابط الصورة
    url_patterns = [
        r'/page[_-]?(\d+)',
        r'/(\d+)\.(jpg|jpeg|png|gif|webp)',
        r'[_-](\d+)\.(jpg|jpeg|png|gif|webp)',
        r'p(\d+)\.',
        r'page(\d+)',
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, src, re.IGNORECASE)
        if match:
            try:
                page_num = int(match.group(1))
                order_info['order'] = page_num
                order_info['page_num'] = page_num
                break
            except (ValueError, IndexError):
                continue
    
    # البحث في خصائص العنصر
    element_attrs = [
        img_element.get('data-page'),
        img_element.get('data-index'),
        img_element.get('data-order'),
        img_element.get('id'),
        img_element.get('class', [])
    ]
    
    for attr in element_attrs:
        if not attr:
            continue
            
        if isinstance(attr, list):
            attr = ' '.join(attr)
        
        # البحث عن أرقام في الخصائص
        numbers = re.findall(r'\d+', str(attr))
        if numbers:
            try:
                num = int(numbers[0])
                if 0 < num < 1000:  # رقم منطقي
                    if order_info['order'] == 999999:
                        order_info['order'] = num
                        order_info['page_num'] = num
                    break
            except ValueError:
                continue
    
    return order_info


def is_valid_manga_image_url(url):
    """
    تحقق نهائي من صحة رابط صورة المانجا
    """
    if not url:
        return False
    
    # تحقق من البروتوكول
    if not url.startswith(('http://', 'https://')):
        return False
    
    # تحقق من الامتداد
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    if not any(url.lower().endswith(ext) for ext in image_extensions):
        # قد تكون هناك معاملات إضافية في الرابط
        parsed = urlparse(url)
        path = parsed.path.lower()
        if not any(ext in path for ext in image_extensions):
            return False
    
    # تجنب الروابط المشبوهة
    suspicious_patterns = [
        'data:image',  # Base64 images
        'placeholder',
        'loading',
        'spinner',
        'blank'
    ]
    
    if any(pattern in url.lower() for pattern in suspicious_patterns):
        return False
    
    return True


def extract_images_from_scripts(soup, base_url):
    """
    استخراج روابط الصور من JavaScript والبيانات المخفية
    """
    image_urls = []
    
    # البحث في جميع عناصر script
    scripts = soup.find_all('script')
    
    for script in scripts:
        if not script.string:
            continue
        
        script_content = script.string
        
        # أنماط شائعة للصور في JavaScript
        js_patterns = [
            r'(?:src|url|image)["\']\s*:\s*["\']([^"\']+\.(jpg|jpeg|png|gif|webp))["\']',
            r'["\']([^"\']*\.(jpg|jpeg|png|gif|webp))["\']',
            r'images?\s*=\s*\[([^\]]+)\]',
            r'pages?\s*=\s*\[([^\]]+)\]',
        ]
        
        for pattern in js_patterns:
            matches = re.findall(pattern, script_content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    url = match[0]
                else:
                    url = match
                
                # تنظيف الرابط
                url = url.strip('\'"')
                
                if url and is_valid_manga_image_url(url):
                    # تحويل إلى رابط مطلق
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = urljoin(base_url, url)
                    elif not url.startswith('http'):
                        url = urljoin(base_url, url)
                    
                    image_urls.append(url)
    
    # إزالة التكرارات مع الحفاظ على الترتيب
    seen = set()
    unique_images = []
    for url in image_urls:
        if url not in seen:
            seen.add(url)
            unique_images.append(url)
    
    return unique_images


def download_images_with_retry(image_urls, temp_dir, referer_url=None):
    """
    تحميل الصور مع إعادة المحاولة والتحسين
    """
    downloaded_images = []
    failed_downloads = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
    }
    
    if referer_url:
        headers['Referer'] = referer_url
    
    for i, image_url in enumerate(image_urls, 1):
        success = False
        attempts = 0
        max_attempts = 3
        
        while not success and attempts < max_attempts:
            try:
                attempts += 1
                print(f"تحميل الصورة {i}/{len(image_urls)} (محاولة {attempts}/{max_attempts}): {image_url[:60]}...")
                
                response = requests.get(image_url, headers=headers, timeout=45, stream=True)
                response.raise_for_status()
                
                # تحديد امتداد الملف
                content_type = response.headers.get('content-type', '').lower()
                if 'jpeg' in content_type or 'jpg' in content_type:
                    ext = 'jpg'
                elif 'png' in content_type:
                    ext = 'png'
                elif 'gif' in content_type:
                    ext = 'gif'
                elif 'webp' in content_type:
                    ext = 'webp'
                else:
                    # استخراج الامتداد من الرابط
                    parsed_url = urlparse(image_url)
                    path_ext = parsed_url.path.split('.')[-1].lower()
                    if path_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                        ext = path_ext
                    else:
                        ext = 'jpg'  # افتراضي
                
                # حفظ الصورة
                filename = f"page_{i:03d}.{ext}"
                filepath = os.path.join(temp_dir, filename)
                
                # تحميل وحفظ الصورة
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # تحسين الصورة
                try:
                    optimized_path = optimize_manga_image(filepath, temp_dir, i)
                    if optimized_path:
                        downloaded_images.append(optimized_path)
                        success = True
                        print(f"✓ تم تحميل وتحسين الصورة {i}")
                    else:
                        downloaded_images.append(filepath)
                        success = True
                        print(f"✓ تم تحميل الصورة {i}")
                        
                except Exception as opt_error:
                    print(f"⚠ خطأ في تحسين الصورة {i}: {opt_error}")
                    downloaded_images.append(filepath)
                    success = True
                
                # توقف قصير بين التحميلات
                time.sleep(0.5)
                
            except Exception as e:
                print(f"✗ خطأ في تحميل الصورة {i} (محاولة {attempts}): {e}")
                if attempts < max_attempts:
                    time.sleep(2)  # انتظار قبل إعادة المحاولة
                else:
                    failed_downloads.append((i, image_url, str(e)))
    
    if failed_downloads:
        print(f"⚠ فشل تحميل {len(failed_downloads)} صورة:")
        for page_num, url, error in failed_downloads:
            print(f"  صفحة {page_num}: {error}")
    
    return downloaded_images


def optimize_manga_image(image_path, temp_dir, page_num):
    """
    تحسين صورة المانجا للعرض على الويب
    """
    try:
        with Image.open(image_path) as img:
            # تحويل إلى RGB إذا لزم الأمر
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # تحسين الحجم إذا كان كبيراً جداً
            max_width = 1200
            max_height = 1800
            
            if img.width > max_width or img.height > max_height:
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # حفظ النسخة المحسنة
            optimized_path = os.path.join(temp_dir, f"page_{page_num:03d}.jpg")
            img.save(optimized_path, 'JPEG', quality=85, optimize=True)
            
            # حذف الملف الأصلي إذا كان مختلفاً
            if image_path != optimized_path and os.path.exists(image_path):
                os.remove(image_path)
            
            return optimized_path
            
    except Exception as e:
        print(f"خطأ في تحسين الصورة: {e}")
        return None