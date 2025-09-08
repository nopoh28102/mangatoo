"""
Production configuration settings for deployment
"""
import os

class ProductionConfig:
    """Configuration for production deployment"""
    
    # Environment detection
    IS_PRODUCTION = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('DATABASE_URL') is not None
    
    # Database Configuration
    if IS_PRODUCTION:
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
            "echo": False,
        }
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.abspath('manga_platform.db')}"
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
        }
    
    # Security Settings
    SECRET_KEY = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT", "dev-salt-change-in-production")
    
    # File Upload Settings
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year cache
    
    # Cloudinary Settings (if available)
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')
    
    # CSRF Protection
    WTF_CSRF_ENABLED = IS_PRODUCTION
    WTF_CSRF_TIME_LIMIT = None
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Logging
    LOG_LEVEL = 'INFO' if IS_PRODUCTION else 'DEBUG'
    
    # Performance
    TEMPLATES_AUTO_RELOAD = not IS_PRODUCTION
    
    @staticmethod
    def init_app(app):
        """Initialize application with production settings"""
        # Set logging level
        import logging
        if ProductionConfig.IS_PRODUCTION:
            logging.basicConfig(level=logging.INFO)
        else:
            logging.basicConfig(level=logging.DEBUG)
        
        # Ensure upload directories exist
        os.makedirs(os.path.join(ProductionConfig.UPLOAD_FOLDER, 'manga'), exist_ok=True)
        os.makedirs(os.path.join(ProductionConfig.UPLOAD_FOLDER, 'covers'), exist_ok=True)
        
        return app

def get_config():
    """Get appropriate configuration based on environment"""
    return ProductionConfig