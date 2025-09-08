"""
Database initialization script
This file handles database table creation and initial data setup
"""
import logging
from app.app import app, db

def initialize_database():
    """Initialize database tables and create admin user"""
    with app.app_context():
        # Make sure to import the models here or their tables won't be created
        import app.models  # noqa: F401
        # Cloudinary models are now part of app.models
        
        # Create all database tables
        try:
            db.create_all()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {e}")
            raise
        
        # Create admin user if it doesn't exist
        try:
            from app.models import User
            from werkzeug.security import generate_password_hash
            
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin_user = User(
                    username='admin',
                    email='admin@manga.com',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True
                )
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