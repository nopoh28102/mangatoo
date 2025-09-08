"""
Dynamic URL utilities for ensuring all URLs adapt to the current domain
"""

from flask import request, url_for, has_request_context
from .utils_settings import SettingsManager
from urllib.parse import urlparse
import logging

def get_dynamic_base_url():
    """
    Get the base URL dynamically based on the current request or configuration.
    This ensures URLs work on any domain the application is deployed to.
    """
    try:
        # First priority: Use current request context
        if has_request_context() and request:
            base_url = request.url_root.rstrip('/')
            logging.debug(f"Base URL from request context: {base_url}")
            return base_url
    except Exception as e:
        logging.debug(f"Could not get URL from request context: {e}")
    
    try:
        # Second priority: Use configured site URL from settings
        configured_url = SettingsManager.get('site_url', None)
        if configured_url and configured_url != 'http://localhost:5000':
            base_url = configured_url.rstrip('/')
            logging.debug(f"Base URL from settings: {base_url}")
            return base_url
    except Exception as e:
        logging.debug(f"Could not get URL from settings: {e}")
    
    # Fallback: Use environment domain or localhost
    import os
    fallback_domain = os.environ.get('REPLIT_DEV_DOMAIN') or os.environ.get('REPLIT_URL', 'http://localhost:5000')
    if not fallback_domain.startswith('http'):
        fallback_domain = 'https://' + fallback_domain
    
    logging.warning(f"Using fallback base URL: {fallback_domain} - please configure 'site_url' in settings")
    return fallback_domain.rstrip('/')

def generate_absolute_url(path=''):
    """
    Generate absolute URL for any path.
    
    Args:
        path (str): Path to append to base URL (e.g., '/manga/123')
    
    Returns:
        str: Complete absolute URL
    """
    base_url = get_dynamic_base_url()
    
    # Ensure path starts with /
    if path and not path.startswith('/'):
        path = '/' + path
    
    return base_url + path

def generate_api_url(endpoint):
    """
    Generate API endpoint URL dynamically.
    
    Args:
        endpoint (str): API endpoint (e.g., 'manga', 'notifications/unread-count')
    
    Returns:
        str: Complete API URL
    """
    # Remove leading slash if present
    if endpoint.startswith('/'):
        endpoint = endpoint[1:]
    
    return generate_absolute_url(f'/api/{endpoint}')

def generate_static_url(path):
    """
    Generate static file URL dynamically.
    
    Args:
        path (str): Static file path (e.g., 'css/style.css')
    
    Returns:
        str: Complete static file URL
    """
    # Remove leading slash if present
    if path.startswith('/'):
        path = path[1:]
    
    return generate_absolute_url(f'/static/{path}')

def get_canonical_url(path=None):
    """
    Generate canonical URL for SEO purposes.
    
    Args:
        path (str, optional): Specific path for canonical URL
    
    Returns:
        str: Canonical URL
    """
    if path:
        return generate_absolute_url(path)
    
    try:
        if has_request_context() and request:
            return request.url.split('?')[0]  # Remove query parameters
    except Exception:
        pass
    
    return get_dynamic_base_url()

def ensure_https(url):
    """
    Ensure URL uses HTTPS protocol.
    
    Args:
        url (str): URL to check
    
    Returns:
        str: URL with HTTPS protocol
    """
    if url.startswith('http://'):
        return url.replace('http://', 'https://', 1)
    elif not url.startswith('https://'):
        return 'https://' + url.lstrip('/')
    return url

def update_site_url_setting():
    """
    Update the site_url setting based on current request.
    Call this function when the application is accessed to auto-configure the domain.
    """
    try:
        if has_request_context() and request:
            current_base = request.url_root.rstrip('/')
            stored_url = SettingsManager.get('site_url', None)
            
            # Update if different or not set
            if stored_url != current_base:
                SettingsManager.set('site_url', current_base)
                logging.info(f"Auto-updated site_url setting to: {current_base}")
                return True
    except Exception as e:
        logging.debug(f"Could not auto-update site_url: {e}")
    
    return False

def validate_and_normalize_url(url):
    """
    Validate and normalize a URL.
    
    Args:
        url (str): URL to validate
    
    Returns:
        str: Normalized URL or None if invalid
    """
    if not url:
        return None
    
    # Remove whitespace
    url = url.strip()
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Remove trailing slash
    url = url.rstrip('/')
    
    return url

def safe_redirect_url(referrer_url, fallback_endpoint='index', **endpoint_kwargs):
    """
    Safely validate a referrer URL to prevent open redirect attacks.
    
    Args:
        referrer_url (str): The URL from request.referrer or user input
        fallback_endpoint (str): Flask endpoint to use if referrer is invalid
        **endpoint_kwargs: Additional arguments for url_for()
    
    Returns:
        str: Safe URL for redirect (either validated referrer or fallback)
    """
    if not referrer_url:
        return url_for(fallback_endpoint, **endpoint_kwargs)
    
    try:
        # Parse the referrer URL
        parsed_referrer = urlparse(referrer_url)
        
        # Get current request info for comparison
        if has_request_context() and request:
            current_host = request.host
            current_scheme = request.scheme
            
            # Only allow redirects to the same host
            if (parsed_referrer.netloc == current_host or 
                parsed_referrer.netloc == '' or  # Relative URLs
                parsed_referrer.netloc is None):
                
                # For relative URLs, make them absolute with current scheme
                if not parsed_referrer.netloc:
                    return referrer_url  # Already relative, safe to use
                
                # For same-host absolute URLs, ensure scheme matches
                if parsed_referrer.scheme in ['http', 'https']:
                    return referrer_url
        
        # If we can't validate or it's external, use fallback
        return url_for(fallback_endpoint, **endpoint_kwargs)
        
    except Exception as e:
        logging.debug(f"Error validating referrer URL '{referrer_url}': {e}")
        return url_for(fallback_endpoint, **endpoint_kwargs)