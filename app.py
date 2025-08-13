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
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure database - support both PostgreSQL (production) and SQLite (local)
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
else:
    # Local development (SQLite)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath('manga_platform.db')}"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
    }

# Configure upload settings
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size for manga archives
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

# Initialize database when imported (delay import to avoid circular imports)
def init_app():
    """Initialize the Flask application"""
    try:
        from database_init import initialize_database
        initialize_database()
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
        # Continue anyway, the app might still work partially

# Only initialize when not run directly
if __name__ != '__main__':
    init_app()

# Initialize Flask-Login after models are imported
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore

@login_manager.user_loader
def load_user(user_id):
    from models import User
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
    from utils_settings import SettingsManager
    def get_setting(key, default=None):
        return SettingsManager.get(key, default)
    return dict(get_setting=get_setting)

# Auto-update site URL setting based on current domain
@app.before_request
def auto_detect_domain():
    """Automatically detect and update the site_url setting based on current request"""
    try:
        from utils_dynamic_urls import update_site_url_setting
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
        from models import User
        User.query.first()
        return {'status': 'healthy', 'database': 'connected'}, 200
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}, 500

# Import routes
import routes  # noqa: F401
