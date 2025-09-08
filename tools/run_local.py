"""
Local development server runner
This file is specifically for running the application on Windows/local environments
"""
import os
import logging

# Configure logging first
logging.basicConfig(level=logging.DEBUG)

# Set environment variable for local development
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('SESSION_SECRET', 'dev-secret-key-change-in-production')

# Import the app
from app import app

# Initialize database if needed
try:
    from database.database_init import initialize_database
    initialize_database()
except Exception as e:
    logging.error(f"Database initialization failed: {e}")
    print("Warning: Database initialization failed, but continuing...")

# Initialize Flask-Login
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore

@login_manager.user_loader
def load_user(user_id):
    try:
        from app.models import User
        return User.query.get(int(user_id))
    except Exception as e:
        logging.error(f"Error loading user: {e}")
        return None

# Import routes
try:
    import routes
    logging.info("Routes imported successfully")
except Exception as e:
    logging.error(f"Error importing routes: {e}")

if __name__ == '__main__':
    print("Starting Flask development server on Windows...")
    print("Access the application at: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)