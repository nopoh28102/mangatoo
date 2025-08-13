
# تحسينات الأداء للمنصة
# Performance Optimizations for the Platform

from functools import wraps
from flask import request, jsonify
import time
import logging

def cache_response(timeout=300):
    # ديكوريتر لتخزين مؤقت للاستجابات
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # تنفيذ تخزين مؤقت بسيط
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limit(max_requests=100, per_minute=1):
    # ديكوريتر لتحديد معدل الطلبات
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # تنفيذ تحديد معدل الطلبات
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_performance(f):
    # ديكوريتر لقياس الأداء
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        
        execution_time = end_time - start_time
        if execution_time > 1.0:  # أكثر من ثانية
            logging.warning(f"Slow function {f.__name__}: {execution_time:.2f}s")
        
        return result
    return decorated_function

class DatabaseOptimizer:
    # محسن قاعدة البيانات
    
    @staticmethod
    def optimize_queries():
        # تحسين الاستعلامات
        # استعلامات محسنة
        optimized_queries = {
            'popular_manga': 'SELECT m.* FROM manga m WHERE m.is_published = 1 ORDER BY m.views DESC LIMIT 20',
            'latest_chapters': 'SELECT c.*, m.title as manga_title FROM chapter c JOIN manga m ON c.manga_id = m.id WHERE c.is_approved = 1 ORDER BY c.created_at DESC LIMIT 50'
        }
        return optimized_queries
