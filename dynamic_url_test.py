"""
Test script to verify dynamic URL functionality
"""

import requests
from flask import Flask
from utils_dynamic_urls import get_dynamic_base_url, generate_absolute_url, generate_api_url
from utils_settings import SettingsManager

def test_dynamic_urls():
    """Test that URLs are generated dynamically"""
    
    print("Testing Dynamic URL Generation")
    print("=" * 40)
    
    # Test 1: Check if site_url setting is automatically configured
    site_url = SettingsManager.get('site_url', None)
    print(f"✅ Site URL Setting: {site_url}")
    
    # Test 2: Test base URL generation
    try:
        base_url = get_dynamic_base_url()
        print(f"✅ Dynamic Base URL: {base_url}")
    except Exception as e:
        print(f"❌ Error getting base URL: {e}")
    
    # Test 3: Test absolute URL generation
    test_paths = ['/manga/123', 'api/notifications', 'admin/settings']
    for path in test_paths:
        try:
            abs_url = generate_absolute_url(path)
            print(f"✅ Absolute URL for '{path}': {abs_url}")
        except Exception as e:
            print(f"❌ Error generating URL for '{path}': {e}")
    
    # Test 4: Test API URL generation
    api_endpoints = ['manga/123', 'notifications/unread-count', 'update_progress']
    for endpoint in api_endpoints:
        try:
            api_url = generate_api_url(endpoint)
            print(f"✅ API URL for '{endpoint}': {api_url}")
        except Exception as e:
            print(f"❌ Error generating API URL for '{endpoint}': {e}")
    
    print("\n" + "=" * 40)
    print("Dynamic URL Test Complete")

if __name__ == "__main__":
    test_dynamic_urls()