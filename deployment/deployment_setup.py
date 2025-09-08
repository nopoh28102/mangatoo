#!/usr/bin/env python3
"""
Deployment Setup Script
Configures the application for different hosting environments
with automatic database selection
"""

import os
import sys
import logging
import json
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DeploymentSetup:
    def __init__(self):
        self.deployment_info = self.detect_environment()
        
    def detect_environment(self):
        """Detect deployment environment"""
        env_info = {
            'platform': 'unknown',
            'database_preference': 'sqlite',
            'read_only_filesystem': False,
            'environment': os.environ.get('FLASK_ENV', 'production')
        }
        
        # Check various hosting platforms
        if os.environ.get('REPLIT_DB_URL'):
            env_info['platform'] = 'replit'
            env_info['database_preference'] = 'sqlite'
        elif os.environ.get('RAILWAY_ENVIRONMENT'):
            env_info['platform'] = 'railway'
            env_info['database_preference'] = 'postgresql'
        elif os.environ.get('DYNO'):
            env_info['platform'] = 'heroku'
            env_info['database_preference'] = 'postgresql'
        elif os.environ.get('VERCEL'):
            env_info['platform'] = 'vercel'
            env_info['database_preference'] = 'postgresql'
            env_info['read_only_filesystem'] = True
        elif os.environ.get('LEAPCELL_ENV'):
            env_info['platform'] = 'leapcell'
            env_info['database_preference'] = 'postgresql'
            env_info['read_only_filesystem'] = True
        
        return env_info
    
    def setup_database_config(self):
        """Setup database configuration"""
        logger.info(f"Setting up database for {self.deployment_info['platform']} platform")
        
        # Check if PostgreSQL is available and preferred
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url and database_url.startswith(('postgresql://', 'postgres://')):
            logger.info("PostgreSQL detected - using PostgreSQL")
            os.environ['DATABASE_TYPE'] = 'postgresql'
            return 'postgresql'
        else:
            logger.info("No PostgreSQL detected - using SQLite")
            os.environ['DATABASE_TYPE'] = 'sqlite'
            return 'sqlite'
    
    def setup_file_storage(self):
        """Setup file storage configuration"""
        if self.deployment_info['read_only_filesystem']:
            logger.info("Read-only filesystem detected - configuring for cloud storage")
            os.environ['USE_CLOUDINARY'] = 'true'
            os.environ['SKIP_LOCAL_UPLOADS'] = 'true'
        else:
            logger.info("Writable filesystem - enabling local uploads")
    
    def create_deployment_config_file(self):
        """Create deployment configuration file"""
        config = {
            'deployment_info': self.deployment_info,
            'database_type': os.environ.get('DATABASE_TYPE', 'sqlite'),
            'setup_timestamp': datetime.now().isoformat(),
            'features_enabled': {
                'local_uploads': not self.deployment_info['read_only_filesystem'],
                'cloudinary': os.environ.get('USE_CLOUDINARY', 'false') == 'true',
                'postgresql': os.environ.get('DATABASE_TYPE') == 'postgresql',
                'background_uploads': True,
                'content_scraping': True,
                'payment_processing': True,
                'premium_features': True
            }
        }
        
        try:
            with open('deployment_config.json', 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("Deployment configuration saved")
        except Exception as e:
            logger.warning(f"Could not save deployment config: {e}")
        
        return config
    
    def setup_environment_defaults(self):
        """Setup default environment variables"""
        defaults = {
            'SESSION_SECRET': 'change-this-in-production-' + os.urandom(16).hex(),
            'FLASK_ENV': 'production',
            'SQLALCHEMY_TRACK_MODIFICATIONS': 'False',
            'MAX_CONTENT_LENGTH': '200000000',  # 200MB
            'UPLOAD_FOLDER': 'static/uploads'
        }
        
        for key, value in defaults.items():
            if not os.environ.get(key):
                os.environ[key] = value
                logger.info(f"Set default {key}")
    
    def run_setup(self):
        """Run complete setup process"""
        logger.info("Starting deployment setup...")
        
        try:
            # Setup environment defaults
            self.setup_environment_defaults()
            
            # Setup database
            db_type = self.setup_database_config()
            
            # Setup file storage
            self.setup_file_storage()
            
            # Create config file
            config = self.create_deployment_config_file()
            
            logger.info(f"Deployment setup completed successfully!")
            logger.info(f"Platform: {self.deployment_info['platform']}")
            logger.info(f"Database: {db_type}")
            logger.info(f"Read-only filesystem: {self.deployment_info['read_only_filesystem']}")
            
            return True, config
            
        except Exception as e:
            logger.error(f"Deployment setup failed: {e}")
            return False, str(e)

if __name__ == '__main__':
    setup = DeploymentSetup()
    success, result = setup.run_setup()
    
    if success:
        print("✅ Deployment setup completed successfully!")
        sys.exit(0)
    else:
        print(f"❌ Deployment setup failed: {result}")
        sys.exit(1)