"""
Database initialization script
This file handles database table creation and initial data setup
"""
import logging
from app import app, db

def initialize_database():
    """Initialize database tables and create admin user"""
    with app.app_context():
        # Make sure to import the models here or their tables won't be created
        import models  # noqa: F401
        try:
            import models_cloudinary  # noqa: F401
            logging.info("✅ Cloudinary models imported successfully")
        except ImportError as e:
            logging.warning(f"⚠️ Could not import Cloudinary models: {e}")
        
        # Create all database tables
        try:
            db.create_all()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {e}")
            raise
        
        # Create admin user if it doesn't exist
        try:
            from models import User
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
                logging.info("Admin user created successfully")
            else:
                logging.info("Admin user already exists")
        except Exception as e:
            logging.error(f"Error creating admin user: {e}")
            # Don't raise here, the database tables are created so the app can still run

if __name__ == "__main__":
    initialize_database()