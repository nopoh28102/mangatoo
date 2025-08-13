#!/usr/bin/env python3
import os
import sys
import logging

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.DEBUG)

try:
    from app import app  # noqa: F401
    logging.info("Successfully imported app from app.py")
except ImportError as e:
    logging.error(f"Failed to import app: {e}")
    # Fallback - import everything directly
    import os
    import logging
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy.orm import DeclarativeBase
    from werkzeug.middleware.proxy_fix import ProxyFix

    class Base(DeclarativeBase):
        pass

    db = SQLAlchemy(model_class=Base)

    # create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Configure database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL:
        app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
        }
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath('manga_platform.db')}"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
        }

    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000

    db.init_app(app)

    # Try to create directories (skip if read-only)
    try:
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'manga'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'covers'), exist_ok=True)
    except OSError as e:
        if e.errno == 30:
            logging.info("Running on read-only file system - skipping directory creation")
        else:
            logging.error(f"Failed to create upload directories: {e}")

    # Initialize Flask-Login
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة.'

    # Initialize database if models exist
    try:
        with app.app_context():
            import models  # noqa: F401
            db.create_all()
            logging.info("Database tables created successfully")
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")

    # Import routes
    try:
        import routes  # noqa: F401
        logging.info("Routes imported successfully")
    except Exception as e:
        logging.error(f"Failed to import routes: {e}")

    logging.info("Fallback app initialization completed")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
