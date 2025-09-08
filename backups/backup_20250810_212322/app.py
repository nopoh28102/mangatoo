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

# configure the database, using SQLite for local development
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath('manga_platform.db')}"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}

# Configure upload settings
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# initialize the app with the extension, flask-sqlalchemy >= 3.0.x
db.init_app(app)

# Create upload directories
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'manga'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'covers'), exist_ok=True)

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    
    # Create all database tables
    try:
        db.create_all()
        logging.info("Database tables created successfully")
    except Exception as e:
        logging.error(f"Error creating database tables: {e}")
        raise
    
    # Create admin user if it doesn't exist
    from models import User
    from werkzeug.security import generate_password_hash
    
    try:
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin_user = User()
            admin_user.username = 'admin'
            admin_user.email = 'admin@manga.com'
            admin_user.password_hash = generate_password_hash('admin123')
            admin_user.is_admin = True
            db.session.add(admin_user)
            db.session.commit()
            logging.info("Admin user created: admin/admin123")
        else:
            logging.info("Admin user already exists")
    except Exception as e:
        logging.error(f"Error creating admin user: {e}")
        # Don't raise here, the database tables are created so the app can still run

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

# Import routes
import routes  # noqa: F401
