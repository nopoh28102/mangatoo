"""
Deployment configuration for different hosting environments
"""
import os
import logging


def is_read_only_filesystem():
    """Check if the current environment has a read-only filesystem"""
    try:
        # Try to create a temporary file in the current directory
        test_file = "temp_write_test.txt"
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        return False
    except (OSError, IOError):
        return True


def configure_for_deployment():
    """Configure the application for deployment environments"""
    config = {}
    
    # Detect deployment environment
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        config['platform'] = 'railway'
    elif os.environ.get('HEROKU_APP_NAME'):
        config['platform'] = 'heroku'
    elif os.environ.get('VERCEL_ENV'):
        config['platform'] = 'vercel'
    elif is_read_only_filesystem():
        config['platform'] = 'read_only'  # Generic read-only environment like leapcell.io
    else:
        config['platform'] = 'local'
    
    # Set appropriate configurations
    if config['platform'] in ['railway', 'heroku', 'vercel', 'read_only']:
        config['use_temp_storage'] = True
        config['skip_directory_creation'] = True
        config['use_cloudinary_only'] = True
        logging.info(f"Configured for {config['platform']} deployment")
    else:
        config['use_temp_storage'] = False
        config['skip_directory_creation'] = False
        config['use_cloudinary_only'] = False
        logging.info("Configured for local development")
    
    return config


# Global deployment configuration
DEPLOYMENT_CONFIG = configure_for_deployment()