"""
Advanced SEO utilities for comprehensive search engine optimization
"""

from flask import request, url_for
from .utils_settings import SettingsManager
import re
import json
from urllib.parse import urljoin

def get_base_url():
    """Get base URL of the site dynamically"""
    try:
        if request:
            return request.url_root.rstrip('/')
    except RuntimeError:
        # Outside request context
        pass
    
    # Fallback to configured URL from settings
    configured_url = SettingsManager.get('site_url', None)
    if configured_url:
        return configured_url.rstrip('/')
    
    # Last resort fallback
    return 'https://example.com'

def generate_meta_title(page_title=None, page_type='page'):
    """Generate complete meta title with site branding"""
    site_title = SettingsManager.get('seo_site_title', 'منصة المانجا')
    separator = SettingsManager.get('seo_title_separator', ' | ')
    
    if page_title:
        if page_type == 'manga':
            return f"{page_title}{separator}قراءة مانجا{separator}{site_title}"
        elif page_type == 'chapter':
            return f"{page_title}{separator}قراءة الفصل{separator}{site_title}"
        elif page_type == 'category':
            return f"{page_title}{separator}تصنيف{separator}{site_title}"
        else:
            return f"{page_title}{separator}{site_title}"
    
    return site_title

def generate_meta_description(content=None, page_type='page', max_length=160):
    """Generate optimized meta description"""
    default_description = SettingsManager.get('seo_meta_description', 
                                              'منصة شاملة لقراءة المانجا والمانهوا باللغة العربية مجاناً')
    
    if not content:
        return default_description[:max_length]
    
    # Clean HTML tags
    clean_content = re.sub(r'<[^>]+>', '', str(content))
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
    
    # Add context based on page type
    if page_type == 'manga':
        prefix = "اقرأ "
        suffix = " مجاناً على منصة المانجا"
    elif page_type == 'chapter':
        prefix = "اقرأ الفصل "
        suffix = " مجاناً"
    else:
        prefix = ""
        suffix = ""
    
    full_description = prefix + clean_content + suffix
    
    # Truncate to max length
    if len(full_description) > max_length:
        return full_description[:max_length-3] + "..."
    
    return full_description

def generate_meta_keywords(custom_keywords=None, page_type='page'):
    """Generate meta keywords"""
    default_keywords = SettingsManager.get('seo_meta_keywords', 
                                          'مانجا, مانهوا, قراءة مانجا, مانجا عربية')
    
    keywords_list = [kw.strip() for kw in default_keywords.split(',') if kw.strip()]
    
    if custom_keywords:
        if isinstance(custom_keywords, str):
            custom_list = [kw.strip() for kw in custom_keywords.split(',') if kw.strip()]
        else:
            custom_list = [str(kw).strip() for kw in custom_keywords if str(kw).strip()]
        
        keywords_list.extend(custom_list)
    
    # Add contextual keywords based on page type
    if page_type == 'manga':
        keywords_list.extend(['قراءة مانجا اون لاين', 'مانجا مجانية'])
    elif page_type == 'chapter':
        keywords_list.extend(['فصل مانجا', 'قراءة فصل'])
    elif page_type == 'category':
        keywords_list.extend(['تصنيف مانجا', 'نوع مانجا'])
    
    # Remove duplicates while preserving order
    unique_keywords = []
    for kw in keywords_list:
        if kw not in unique_keywords:
            unique_keywords.append(kw)
    
    return ', '.join(unique_keywords[:15])  # Limit to 15 keywords

def generate_structured_data(manga=None, chapter=None):
    """Generate JSON-LD structured data for SEO"""
    import json
    
    if chapter and manga:
        # Chapter page structured data
        structured_data = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": f"{manga.title} - Chapter {chapter.chapter_number}",
            "description": chapter.title or f"Chapter {chapter.chapter_number} of {manga.title}",
            "author": {
                "@type": "Person",
                "name": manga.author or "Unknown"
            },
            "publisher": {
                "@type": "Organization",
                "name": "Manga Platform"
            },
            "datePublished": chapter.created_at.isoformat() if chapter.created_at else "",
            "image": manga.cover_image if manga.cover_image else "",
            "url": f"/read/{manga.slug}/{chapter.slug}" if manga.slug and chapter.slug else "",
            "isPartOf": {
                "@type": "Series",
                "name": manga.title,
                "url": f"/manga/{manga.slug}" if manga.slug else ""
            }
        }
    elif manga:
        # Manga page structured data
        structured_data = {
            "@context": "https://schema.org",
            "@type": "ComicSeries",
            "name": manga.title,
            "description": manga.description or f"Read {manga.title} manga online",
            "author": {
                "@type": "Person",
                "name": manga.author or "Unknown"
            },
            "publisher": {
                "@type": "Organization",
                "name": "Manga Platform"
            },
            "dateCreated": manga.created_at.isoformat() if manga.created_at else "",
            "image": manga.cover_image if manga.cover_image else "",
            "url": f"/manga/{manga.slug}" if manga.slug else "",
            "genre": [cat.name for cat in manga.categories] if manga.categories else [],
            "numberOfEpisodes": manga.total_chapters,
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": manga.average_rating,
                "ratingCount": len(manga.ratings.all()) if manga.ratings else 0
            } if manga.average_rating > 0 else None
        }
    else:
        # Default home page structured data
        structured_data = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "Manga Platform",
            "description": "أفضل منصة لقراءة المانجا والمانهوا والمانهوا باللغة العربية مجاناً",
            "url": "/",
            "potentialAction": {
                "@type": "SearchAction",
                "target": "/search?q={search_term_string}",
                "query-input": "required name=search_term_string"
            }
        }
    
    return json.dumps(structured_data, ensure_ascii=False, indent=2)

def generate_meta_tags(title=None, description=None, image=None, url=None, manga=None, chapter=None):
    """Generate complete meta tags for SEO"""
    
    # Default values
    default_title = "Manga Platform - أفضل منصة لقراءة المانجا العربية"
    default_description = "اقرأ آلاف المانجا والمانهوا والمانهوا مجاناً باللغة العربية. تحديث يومي لأحدث الفصول."
    default_image = "/static/images/logo.png"
    
    # Set values based on context
    if manga and chapter:
        page_title = f"{manga.title} - الفصل {chapter.chapter_number}"
        if chapter.title:
            page_title += f" - {chapter.title}"
        page_description = f"اقرأ الفصل {chapter.chapter_number} من مانجا {manga.title} مجاناً. {chapter.title or ''}"
        page_image = manga.cover_image if manga.cover_image else default_image
        page_url = f"/read/{manga.slug}/{chapter.slug}" if manga.slug and chapter.slug else ""
    elif manga:
        page_title = f"{manga.title} - قراءة مانجا مجانية"
        page_description = generate_meta_description(manga.description) if manga.description else f"اقرأ مانجا {manga.title} مجاناً بجودة عالية. {manga.total_chapters} فصل متاح."
        page_image = manga.cover_image if manga.cover_image else default_image
        page_url = f"/manga/{manga.slug}" if manga.slug else ""
    else:
        page_title = title or default_title
        page_description = description or default_description
        page_image = image or default_image
        page_url = url or "/"
    
    return {
        'title': page_title,
        'description': page_description,
        'image': page_image,
        'url': page_url,
        'structured_data': generate_structured_data(manga, chapter)
    }

def generate_canonical_url(request, manga=None, chapter=None):
    """Generate canonical URL for the page"""
    base_url = request.url_root.rstrip('/')
    
    if manga and chapter and manga.slug and chapter.slug:
        return f"{base_url}/read/{manga.slug}/{chapter.slug}"
    elif manga and manga.slug:
        return f"{base_url}/manga/{manga.slug}"
    else:
        return request.url

def generate_breadcrumbs(manga=None, chapter=None):
    """Generate breadcrumb structured data"""
    import json
    
    breadcrumbs = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "الرئيسية",
            "item": "/"
        }
    ]
    
    if manga:
        breadcrumbs.append({
            "@type": "ListItem", 
            "position": 2,
            "name": manga.title,
            "item": f"/manga/{manga.slug}" if manga.slug else f"/manga/{manga.id}"
        })
        
        if chapter:
            breadcrumbs.append({
                "@type": "ListItem",
                "position": 3, 
                "name": f"الفصل {chapter.chapter_number}",
                "item": f"/read/{manga.slug}/{chapter.slug}" if manga.slug and chapter.slug else "#"
            })
    
    structured_breadcrumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": breadcrumbs
    }
    
    return json.dumps(structured_breadcrumbs, ensure_ascii=False)

def generate_og_tags(title, description, image, url, page_type='website'):
    """Generate Open Graph meta tags"""
    if not SettingsManager.get('seo_og_enabled', True):
        return {}
    
    base_url = get_base_url()
    site_name = SettingsManager.get('site_name', 'منصة المانجا')
    
    og_tags = {
        'og:title': title,
        'og:description': description,
        'og:image': urljoin(base_url, image) if image else '',
        'og:url': urljoin(base_url, url) if url else base_url,
        'og:type': page_type,
        'og:site_name': site_name,
        'og:locale': 'ar_SA'
    }
    
    # Add Facebook App ID if configured
    fb_app_id = SettingsManager.get('seo_facebook_app_id')
    if fb_app_id:
        og_tags['fb:app_id'] = fb_app_id
        
    return og_tags

def generate_twitter_tags(title, description, image, url):
    """Generate Twitter Card meta tags"""
    if not SettingsManager.get('seo_twitter_enabled', True):
        return {}
    
    base_url = get_base_url()
    twitter_username = SettingsManager.get('seo_twitter_username', '')
    
    twitter_tags = {
        'twitter:card': 'summary_large_image',
        'twitter:title': title,
        'twitter:description': description,
        'twitter:image': urljoin(base_url, image) if image else ''
    }
    
    if twitter_username:
        twitter_tags['twitter:site'] = twitter_username if twitter_username.startswith('@') else f'@{twitter_username}'
    
    return twitter_tags

def generate_robots_meta():
    """Generate robots meta tag"""
    return SettingsManager.get('seo_robots_meta', 'index, follow')

def generate_preconnect_tags():
    """Generate preconnect link tags for performance"""
    if not SettingsManager.get('seo_page_speed_enabled', True):
        return []
    
    domains = SettingsManager.get('seo_preconnect_domains', '')
    if not domains:
        return []
    
    preconnect_tags = []
    for domain in domains.split(','):
        domain = domain.strip()
        if domain:
            preconnect_tags.append(f'https://{domain}' if not domain.startswith('http') else domain)
    
    return preconnect_tags

def generate_hreflang_tags(current_lang='ar'):
    """Generate hreflang tags for multilingual content"""
    if not SettingsManager.get('seo_hreflang_enabled', True):
        return {}
    
    base_url = get_base_url()
    current_path = request.path
    
    hreflang_tags = {
        'ar': f"{base_url}{current_path}",
        'en': f"{base_url}/en{current_path}" if current_path != '/' else f"{base_url}/en",
        'x-default': f"{base_url}{current_path}"  # Default for unknown locales
    }
    
    return hreflang_tags

def get_seo_analytics_code():
    """Get analytics tracking codes"""
    codes = {}
    
    # Google Analytics
    ga_id = SettingsManager.get('seo_google_analytics')
    if ga_id:
        codes['google_analytics'] = ga_id
    
    # Google Tag Manager
    gtm_id = SettingsManager.get('seo_google_tag_manager')
    if gtm_id:
        codes['google_tag_manager'] = gtm_id
    
    return codes

def get_custom_seo_code():
    """Get custom SEO code injections"""
    return {
        'head': SettingsManager.get('seo_custom_head', ''),
        'body_start': SettingsManager.get('seo_custom_body_start', ''),
        'body_end': SettingsManager.get('seo_custom_body_end', '')
    }

def generate_complete_seo_data(page_title=None, page_description=None, page_image=None, 
                              page_url=None, page_type='website', manga=None, chapter=None,
                              custom_keywords=None):
    """Generate complete SEO data for a page"""
    
    # Generate meta data
    meta_title = generate_meta_title(page_title, 'manga' if manga else 'chapter' if chapter else 'page')
    meta_description = generate_meta_description(page_description, 'manga' if manga else 'chapter' if chapter else 'page')
    meta_keywords = generate_meta_keywords(custom_keywords, 'manga' if manga else 'chapter' if chapter else 'page')
    
    # Determine final values
    final_title = meta_title
    final_description = meta_description
    final_image = page_image or manga.cover_image if manga else SettingsManager.get('seo_default_image')
    final_url = page_url or request.path
    
    # Generate all SEO components
    seo_data = {
        'meta': {
            'title': final_title,
            'description': final_description,
            'keywords': meta_keywords,
            'robots': generate_robots_meta()
        },
        'canonical_url': urljoin(get_base_url(), final_url) if SettingsManager.get('seo_canonical_enabled', True) else None,
        'og_tags': generate_og_tags(final_title, final_description, final_image, final_url, page_type),
        'twitter_tags': generate_twitter_tags(final_title, final_description, final_image, final_url),
        'hreflang_tags': generate_hreflang_tags(),
        'structured_data': generate_structured_data(manga, chapter) if SettingsManager.get('seo_schema_enabled', True) else None,
        'breadcrumbs': generate_breadcrumbs(manga, chapter) if SettingsManager.get('seo_breadcrumb_enabled', True) else None,
        'preconnect_domains': generate_preconnect_tags(),
        'analytics': get_seo_analytics_code(),
        'custom_code': get_custom_seo_code()
    }
    
    return seo_data