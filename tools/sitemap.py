"""
Dynamic XML Sitemap generator for the manga platform
"""

from flask import url_for, Response
from app.models import Manga, Chapter, Category
from app.app import db
from app.utils_settings import SettingsManager
from datetime import datetime
# XML creation (safe) - defusedxml is only needed for parsing external XML
from xml.etree.ElementTree import Element, SubElement, indent, tostring

def generate_sitemap_xml():
    """Generate complete XML sitemap"""
    if not SettingsManager.get('seo_sitemap_enabled', True):
        return None
    
    # Create root element
    urlset = Element('urlset')
    urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    urlset.set('xmlns:xhtml', 'http://www.w3.org/1999/xhtml')
    
    # Get base URL dynamically from request context or settings
    from flask import request, url_for, has_request_context
    try:
        if has_request_context() and request:
            # Generate base URL from current request
            base_url = request.url_root.rstrip('/')
        else:
            # Fallback to settings with dynamic default
            configured_url = SettingsManager.get('site_url', None)
            if configured_url:
                base_url = configured_url.rstrip('/')
            else:
                base_url = 'https://example.com'  # Last resort fallback
    except Exception:
        # Outside request context or error, use configured setting
        configured_url = SettingsManager.get("site_url", "https://example.com")
        base_url = (configured_url or "https://example.com").rstrip("/")
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # Homepage
    url_elem = SubElement(urlset, 'url')
    SubElement(url_elem, 'loc').text = base_url + '/'
    SubElement(url_elem, 'lastmod').text = current_date
    SubElement(url_elem, 'changefreq').text = 'daily'
    SubElement(url_elem, 'priority').text = '1.0'
    
    # Static pages
    static_pages = [
        {'url': '/browse', 'priority': '0.9', 'changefreq': 'daily'},
        {'url': '/popular', 'priority': '0.8', 'changefreq': 'daily'},
        {'url': '/latest', 'priority': '0.8', 'changefreq': 'daily'},
        {'url': '/categories', 'priority': '0.7', 'changefreq': 'weekly'},
        {'url': '/about', 'priority': '0.3', 'changefreq': 'monthly'},
        {'url': '/contact', 'priority': '0.3', 'changefreq': 'monthly'},
        {'url': '/privacy', 'priority': '0.2', 'changefreq': 'yearly'},
        {'url': '/terms', 'priority': '0.2', 'changefreq': 'yearly'},
    ]
    
    for page in static_pages:
        url_elem = SubElement(urlset, 'url')
        SubElement(url_elem, 'loc').text = base_url + page['url']
        SubElement(url_elem, 'lastmod').text = current_date
        SubElement(url_elem, 'changefreq').text = page['changefreq']
        SubElement(url_elem, 'priority').text = page['priority']
    
    # Categories
    try:
        categories = Category.query.filter_by(is_active=True).all()
        for category in categories:
            url_elem = SubElement(urlset, 'url')
            category_url = f"/category/{category.slug}" if category.slug else f"/category/{category.id}"
            SubElement(url_elem, 'loc').text = base_url + category_url
            SubElement(url_elem, 'lastmod').text = current_date
            SubElement(url_elem, 'changefreq').text = 'weekly'
            SubElement(url_elem, 'priority').text = '0.6'
    except Exception as e:
        print(f"Error adding categories to sitemap: {e}")
    
    # Manga pages
    try:
        manga_list = Manga.query.filter_by(status='published').limit(10000).all()
        for manga in manga_list:
            url_elem = SubElement(urlset, 'url')
            manga_url = f"/manga/{manga.slug}" if manga.slug else f"/manga/{manga.id}"
            SubElement(url_elem, 'loc').text = base_url + manga_url
            lastmod = manga.created_at.strftime('%Y-%m-%d') if manga.created_at else current_date
            SubElement(url_elem, 'lastmod').text = lastmod
            SubElement(url_elem, 'changefreq').text = 'weekly'
            SubElement(url_elem, 'priority').text = '0.8'
    except Exception as e:
        print(f"Error adding manga to sitemap: {e}")
    
    # Chapter pages (limit to recent ones to avoid huge sitemap)
    try:
        recent_chapters = Chapter.query.filter_by(status='published')\
                                     .order_by(Chapter.created_at.desc())\
                                     .limit(5000).all()
        
        for chapter in recent_chapters:
            manga = chapter.manga
            if manga and manga.status == 'published':
                url_elem = SubElement(urlset, 'url')
                if manga.slug and chapter.slug:
                    chapter_url = f"/read/{manga.slug}/{chapter.slug}"
                else:
                    chapter_url = f"/read/{manga.id}/{chapter.id}"
                
                SubElement(url_elem, 'loc').text = base_url + chapter_url
                lastmod = chapter.created_at.strftime('%Y-%m-%d') if chapter.created_at else current_date
                SubElement(url_elem, 'lastmod').text = lastmod
                SubElement(url_elem, 'changefreq').text = 'monthly'
                SubElement(url_elem, 'priority').text = '0.7'
    except Exception as e:
        print(f"Error adding chapters to sitemap: {e}")
    
    # Convert to string
    indent(urlset, space="  ", level=0)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_str += tostring(urlset, encoding='unicode')
    
    return xml_str

def generate_sitemap_index():
    """Generate sitemap index for large sites"""
    # Get base URL dynamically from request context or settings
    from flask import request, url_for, has_request_context
    try:
        if has_request_context() and request:
            # Generate base URL from current request
            base_url = request.url_root.rstrip('/')
        else:
            # Fallback to settings with dynamic default
            configured_url = SettingsManager.get('site_url', None)
            if configured_url:
                base_url = configured_url.rstrip('/')
            else:
                base_url = 'https://example.com'  # Last resort fallback
    except Exception:
        configured_url = SettingsManager.get("site_url", "https://example.com")
        base_url = (configured_url or "https://example.com").rstrip("/")
    
    sitemapindex = Element('sitemapindex')
    sitemapindex.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    
    # Main sitemap
    sitemap = SubElement(sitemapindex, 'sitemap')
    SubElement(sitemap, 'loc').text = base_url + '/sitemap.xml'
    SubElement(sitemap, 'lastmod').text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')
    
    # Generate additional sitemaps if needed (manga, chapters, etc.)
    # This can be expanded for very large sites
    
    indent(sitemapindex, space="  ", level=0)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_str += tostring(sitemapindex, encoding='unicode')
    
    return xml_str