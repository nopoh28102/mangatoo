#!/usr/bin/env python3
import os
import sys
import logging
import json

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

logging.basicConfig(level=logging.INFO)

# Run auto setup on first run
try:
    import sys
    sys.path.append('.')
    from config.auto_setup import run_auto_setup
    run_auto_setup()
except ImportError:
    logging.info("Auto setup not available")
except Exception as setup_error:
    logging.warning(f"Auto setup failed: {setup_error}")

# Try to import app normally first
app = None
db = None

try:
    from app.app import app, db
    logging.info("Successfully imported app from app.py")
    
    # Import routes here while we have app and db available
    try:
        import routes
        logging.info("✅ Routes imported successfully!")
    except Exception as routes_error:
        logging.error(f"Failed to import routes: {routes_error}")
        # Add fallback route
        @app.route('/fallback')
        def fallback_index():
            return "<h1>منصة المانجا</h1><p>التطبيق يعمل ولكن routes لم يتم تحميله</p>"
except ImportError as e:
    logging.error(f"Failed to import app: {e}")
    
    # Fallback - create app directly
    from flask import Flask, render_template, request, jsonify
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy.orm import DeclarativeBase
    from werkzeug.middleware.proxy_fix import ProxyFix
    from flask_login import LoginManager

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Configure database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    # إذا كنت تريد وضع بيانات الاتصال مباشرة، قم بإلغاء التعليق عن السطر التالي:
    # DATABASE_URL = "postgresql://username:password@host:port/database_name"
    
    if DATABASE_URL:
        app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
        }
        logging.info("Using PostgreSQL database")
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath('manga_platform.db')}"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
        }
        logging.info("Using SQLite database")

    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000

    db.init_app(app)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'  # type: ignore
    login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة.'

    # Try to create directories (skip if read-only)
    try:
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'manga'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'covers'), exist_ok=True)
    except OSError as e:
        if e.errno == 30:
            logging.info("Running on read-only file system - skipping directory creation")
        else:
            logging.warning(f"Could not create upload directories: {e}")

    # Initialize database and import models
    with app.app_context():
        try:
            # Import models first
            import app.models
            db.create_all()
            logging.info("Database tables created successfully")
            
            # Check if admin user exists, create if not
            from app.models import User
            from werkzeug.security import generate_password_hash
            
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                admin_user = User()
                admin_user.username = 'admin'
                admin_user.email = 'admin@manga.com'
                admin_user.password_hash = generate_password_hash('admin')
                admin_user.is_admin = True
                db.session.add(admin_user)
                db.session.commit()
                logging.info("Admin user created: admin/admin")
            else:
                logging.info("Admin user already exists")
                
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")

    # Simple routes for basic functionality
    @app.route('/')
    def index():
        try:
            return render_template('index.html')
        except Exception as e:
            logging.error(f"Error in index route: {e}")
            return f"<h1>منصة المانجا</h1><p>التطبيق يعمل! Database: {app.config['SQLALCHEMY_DATABASE_URI'][:20]}...</p>"

    @app.route('/api/notifications/unread-count')
    def unread_notifications():
        return jsonify({"count": 0})

    @app.route('/login')
    def login():
        return "<h1>صفحة تسجيل الدخول</h1><p>التطبيق يعمل بنجاح!</p>"

    # Try to import routes if available
    try:
        import routes
        logging.info("✅ Routes imported successfully from main.py")
    except Exception as e:
        logging.warning(f"Could not import routes: {e}")
        logging.warning("Application running in fallback mode with basic routes only")
        
    logging.info("Fallback app initialization completed")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
