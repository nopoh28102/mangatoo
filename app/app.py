import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# create the app
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Dynamic Database Configuration System
try:
    import sys
    sys.path.append('..')
    from config.database_config import db_config
    
    # Use the dynamic configuration system
    app.config["SQLALCHEMY_DATABASE_URI"] = db_config.get_database_uri()
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = db_config.get_engine_options()
    
    logging.info(f"Using {db_config.database_type.upper()} database")
    logging.info(f"Database URI: {db_config.get_database_uri()}")
    
except ImportError:
    # Fallback to original system if database_config not available
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    if DATABASE_URL:
        # Production database (PostgreSQL)
        app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
        }
        logging.info("Using PostgreSQL database (fallback)")
    else:
        # Local development (SQLite)
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath('manga_platform.db')}"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
        }
        logging.info("Using SQLite database (fallback)")

# Configure upload settings
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25MB max file size for better stability
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files

# initialize the app with the extension, flask-sqlalchemy >= 3.0.x
db.init_app(app)

# Create upload directories (only in development environment)
try:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'manga'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'covers'), exist_ok=True)
except OSError as e:
    # Handle read-only file systems (like in deployment environments)
    if e.errno == 30:  # Read-only file system
        logging.info("Running on read-only file system - skipping directory creation")
    else:
        logging.error(f"Failed to create upload directories: {e}")
        # Continue without creating directories

# Initialize database directly to avoid circular imports
def init_database_directly():
    """Initialize database tables directly"""
    try:
        # Import models to create tables
        from . import models  # noqa: F401
        # Cloudinary models are now part of app.models
        
        with app.app_context():
            db.create_all()
            logging.info("✅ Database tables created successfully")
            
            # Create admin user if it doesn't exist
            from .models import User
            from werkzeug.security import generate_password_hash
            
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin_user = User()
                admin_user.username = 'admin'
                admin_user.email = 'admin@manga.com'
                admin_user.password_hash = generate_password_hash('admin123')
                admin_user.is_admin = True
                db.session.add(admin_user)
                db.session.commit()
                logging.info("✅ Admin user created successfully")
            else:
                logging.debug("Admin user already exists")
                
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")

# Only initialize when not run directly
if __name__ != '__main__':
    init_database_directly()

# Initialize Flask-Login after models are imported
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))

# Add custom Jinja2 filters
@app.template_filter('nl2br')
def nl2br(value):
    """Convert newlines to <br> tags"""
    if not value:
        return value
    return str(value).replace('\n', '<br>')

# Add SettingsManager function to Jinja2 context
@app.context_processor
def inject_settings():
    from .utils_settings import SettingsManager
    def get_setting(key, default=None):
        return SettingsManager.get(key, default)
    return dict(get_setting=get_setting)

# Auto-update site URL setting based on current domain
@app.before_request
def auto_detect_domain():
    """Automatically detect and update the site_url setting based on current request"""
    try:
        from .utils_dynamic_urls import update_site_url_setting
        update_site_url_setting()
    except Exception as e:
        logging.debug(f"Could not auto-update site URL: {e}")

# Health check endpoint for deployment platforms
@app.route('/health')
@app.route('/healthcheck') 
@app.route('/kaithheathcheck')
def health_check():
    """Health check endpoint for deployment platforms"""
    try:
        # Test database connection
        from .models import User
        User.query.first()
        return {'status': 'healthy', 'database': 'connected'}, 200
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}, 500

# Register Google OAuth blueprint
try:
    from .google_auth import google_auth, is_google_oauth_enabled
    app.register_blueprint(google_auth)
    
    # Add Google OAuth status to template context
    @app.context_processor
    def inject_google_oauth():
        return dict(is_google_oauth_enabled=is_google_oauth_enabled)
        
    logging.info("✅ Google OAuth blueprint registered successfully")
except ImportError as e:
    logging.warning(f"⚠️ Google OAuth not available: {e}")
except Exception as e:
    logging.error(f"❌ Failed to register Google OAuth blueprint: {e}")


# The database initialization is now handled by init_database_directly above

# Routes will be imported from main.py
