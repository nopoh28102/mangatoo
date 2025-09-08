#!/usr/bin/env python3
"""
Auto Setup System
Automatically configures the project on first run
"""

import os
import sys
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_first_run():
    """Check if this is the first run of the application"""
    return not os.path.exists('deployment_config.json')

def setup_for_new_deployment():
    """Setup application for new deployment"""
    logger.info("🚀 Initiating first-time setup...")
    
    try:
        # Run deployment setup
        from deployment.deployment_setup import DeploymentSetup
        
        setup = DeploymentSetup()
        success, config = setup.run_setup()
        
        if success:
            logger.info("✅ Deployment setup completed successfully!")
            
            # Create welcome message
            create_welcome_message(config)
            
            return True
        else:
            logger.error(f"❌ Deployment setup failed: {config}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Auto setup failed: {e}")
        return False

def create_welcome_message(config):
    """Create welcome message for new deployment"""
    welcome_info = {
        'setup_completed_at': datetime.now().isoformat(),
        'database_type': config.get('database_type', 'sqlite'),
        'features_enabled': config.get('features_enabled', {}),
        'platform': config.get('deployment_info', {}).get('platform', 'unknown'),
        'welcome_message': generate_welcome_text(config)
    }
    
    try:
        with open('welcome_info.json', 'w', encoding='utf-8') as f:
            json.dump(welcome_info, f, indent=2, ensure_ascii=False)
        logger.info("📝 Welcome information saved")
    except Exception as e:
        logger.warning(f"Could not save welcome info: {e}")

def generate_welcome_text(config):
    """Generate welcome message text"""
    database_type = config.get('database_type', 'sqlite')
    platform = config.get('deployment_info', {}).get('platform', 'unknown')
    
    welcome_text = f"""
🎉 مرحباً بك في منصة المانجا!

تم إعداد مشروعك بنجاح:
📊 نوع قاعدة البيانات: {database_type.upper()}
🌐 المنصة: {platform.title()}
✨ جميع المميزات متاحة ومفعلة

المميزات المتاحة:
- قراءة المانجا والمانهوا
- نظام إدارة متكامل
- دعم اللغات المتعددة (العربية/الإنجليزية)
- نظام اشتراكات مميز
- رفع وإدارة المحتوى
- نظام تعليقات تفاعلي

للبدء:
1. أنشئ حساب مدير جديد
2. ارفع أول مانجا
3. استمتع بالمنصة!

💡 نصيحة: يمكنك ترقية قاعدة البيانات إلى PostgreSQL لاحقاً للحصول على أداء أفضل.
"""
    
    return welcome_text

def run_auto_setup():
    """Run automatic setup if needed"""
    if is_first_run():
        logger.info("🔍 First run detected - starting auto setup...")
        return setup_for_new_deployment()
    else:
        logger.info("✅ Application already configured")
        return True

if __name__ == '__main__':
    success = run_auto_setup()
    sys.exit(0 if success else 1)