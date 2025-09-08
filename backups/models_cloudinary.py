from datetime import datetime
import logging
from app import db


class CloudinaryAccount(db.Model):
    """Cloudinary account model for managing multiple accounts"""
    __tablename__ = 'cloudinary_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cloud_name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(100), nullable=False)
    api_secret = db.Column(db.String(100), nullable=False)
    
    # Storage limits and usage
    storage_limit_mb = db.Column(db.Float, default=25600.0)  # 25GB default for free plan
    storage_used_mb = db.Column(db.Float, default=0.0)
    
    # Account settings
    is_primary = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    priority_order = db.Column(db.Integer, default=1)
    plan_type = db.Column(db.String(50), default='free')  # free, plus, advanced, etc.
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    
    # Additional fields
    notes = db.Column(db.Text)  # Admin notes for this account
    
    @property
    def storage_usage_percentage(self):
        """Calculate storage usage percentage"""
        if self.storage_limit_mb <= 0:
            return 0
        return (self.storage_used_mb / self.storage_limit_mb) * 100
    
    @property
    def is_near_storage_limit(self):
        """Check if account is near storage limit (>90%)"""
        return self.storage_usage_percentage > 90
    
    @property
    def is_storage_full(self):
        """Check if account storage is full (>95%)"""
        return self.storage_usage_percentage > 95
    
    @property
    def is_usable(self):
        """Check if account can be used for uploads"""
        return self.is_active and not self.is_storage_full
    
    def mark_as_used(self):
        """Mark account as recently used"""
        self.last_used_at = datetime.utcnow()
        db.session.commit()
    
    def update_usage_stats(self, used_mb):
        """Update storage usage statistics"""
        self.storage_used_mb = used_mb
        self.last_used_at = datetime.utcnow()
        db.session.commit()
        
        # Log usage update
        logging.info(f"Updated storage usage for {self.name}: {self.storage_usage_percentage:.1f}%")
    
    def to_dict(self):
        """Convert account to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'cloud_name': self.cloud_name,
            'storage_limit_mb': self.storage_limit_mb,
            'storage_used_mb': self.storage_used_mb,
            'storage_usage_percentage': self.storage_usage_percentage,
            'is_primary': self.is_primary,
            'is_active': self.is_active,
            'priority_order': self.priority_order,
            'is_near_storage_limit': self.is_near_storage_limit,
            'is_full': self.is_storage_full,
            'plan_type': self.plan_type,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat()
        }


class CloudinaryUsageLog(db.Model):
    """Log of Cloudinary usage for monitoring and analytics"""
    __tablename__ = 'cloudinary_usage_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('cloudinary_accounts.id'), nullable=False)
    
    # Usage data
    operation_type = db.Column(db.String(50), nullable=False)  # upload, delete, transform
    resource_count = db.Column(db.Integer, default=1)  # Number of resources affected
    data_size_mb = db.Column(db.Float, default=0.0)  # Size of data processed
    
    # Context information
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'))
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    
    # Relationships
    account = db.relationship('CloudinaryAccount', backref='usage_logs')
    manga = db.relationship('Manga', backref='cloudinary_logs')
    chapter = db.relationship('Chapter', backref='cloudinary_logs')


class CloudinaryAccountManager:
    """Manager class for Cloudinary account operations"""
    
    @staticmethod
    def create_account(name, cloud_name, api_key, api_secret, storage_limit_mb=25600, is_primary=False, plan_type='free'):
        """Create a new Cloudinary account"""
        
        # If this is set as primary, unset other primary accounts
        if is_primary:
            CloudinaryAccount.query.filter_by(is_primary=True).update({'is_primary': False})
        
        # Calculate priority order
        max_priority = db.session.query(db.func.max(CloudinaryAccount.priority_order)).scalar() or 0
        
        account = CloudinaryAccount()
        account.name = name
        account.cloud_name = cloud_name
        account.api_key = api_key
        account.api_secret = api_secret
        account.storage_limit_mb = storage_limit_mb
        account.is_primary = is_primary
        account.priority_order = max_priority + 1
        account.plan_type = plan_type
        account.is_active = True
        
        db.session.add(account)
        db.session.commit()
        
        logging.info(f"Created new Cloudinary account: {name} ({cloud_name})")
        return account
    
    @staticmethod
    def get_available_account():
        """Get the next available account for upload"""
        
        # Try primary account first
        primary_account = CloudinaryAccount.query.filter_by(
            is_primary=True, 
            is_active=True
        ).first()
        
        if primary_account and primary_account.is_usable:
            primary_account.mark_as_used()
            return primary_account
        
        # If primary is not available, try other accounts by priority
        available_accounts = CloudinaryAccount.query.filter_by(
            is_active=True
        ).order_by(CloudinaryAccount.priority_order).all()
        
        for account in available_accounts:
            if account.is_usable:
                account.mark_as_used()
                return account
        
        # No available accounts
        logging.warning("No available Cloudinary accounts found!")
        return None
    
    @staticmethod
    def switch_to_next_account():
        """Switch to the next available account when current is full"""
        current_account = CloudinaryAccountManager.get_current_account()
        
        if current_account and current_account.is_storage_full:
            # Deactivate current account
            current_account.is_active = False
            db.session.commit()
            
            # Get next available account
            next_account = CloudinaryAccountManager.get_available_account()
            if next_account:
                logging.info(f"Switched from {current_account.name} to {next_account.name}")
                return next_account
            else:
                logging.error("No alternative Cloudinary account available!")
                return None
        
        return current_account
    
    @staticmethod
    def get_current_account():
        """Get the currently active account"""
        return CloudinaryAccount.query.filter_by(
            is_primary=True,
            is_active=True
        ).first()
    
    @staticmethod
    def log_usage(account_id, operation_type, resource_count=1, data_size_mb=0.0, 
                  manga_id=None, chapter_id=None, user_id=None, success=True, error_message=None):
        """Log Cloudinary usage for analytics"""
        
        usage_log = CloudinaryUsageLog()
        usage_log.account_id = account_id
        usage_log.operation_type = operation_type
        usage_log.resource_count = resource_count
        usage_log.data_size_mb = data_size_mb
        usage_log.manga_id = manga_id
        usage_log.chapter_id = chapter_id
        usage_log.user_id = user_id
        usage_log.success = success
        usage_log.error_message = error_message
        
        db.session.add(usage_log)
        db.session.commit()
        
        logging.debug(f"Logged Cloudinary usage: {operation_type} - {resource_count} resources")
    
    @staticmethod
    def get_account_statistics():
        """Get statistics about all Cloudinary accounts"""
        try:
            accounts = CloudinaryAccount.query.all()
            
            stats = {
                'total_accounts': len(accounts),
                'active_accounts': sum(1 for acc in accounts if acc.is_active),
                'primary_accounts': sum(1 for acc in accounts if acc.is_primary),
                'total_storage_limit_mb': sum(acc.storage_limit_mb for acc in accounts),
                'total_storage_used_mb': sum(acc.storage_used_mb for acc in accounts),
                'accounts_near_limit': sum(1 for acc in accounts if acc.is_near_storage_limit),
                'accounts_full': sum(1 for acc in accounts if acc.is_storage_full),
                'accounts': [acc.to_dict() for acc in accounts]
            }
            
            # Calculate overall usage percentage
            if stats['total_storage_limit_mb'] > 0:
                stats['overall_usage_percentage'] = (stats['total_storage_used_mb'] / stats['total_storage_limit_mb']) * 100
            else:
                stats['overall_usage_percentage'] = 0
                
            return stats
            
        except Exception as e:
            logging.error(f"Error getting account statistics: {e}")
            return {
                'total_accounts': 0,
                'active_accounts': 0,
                'primary_accounts': 0,
                'total_storage_limit_mb': 0,
                'total_storage_used_mb': 0,
                'accounts_near_limit': 0,
                'accounts_full': 0,
                'overall_usage_percentage': 0,
                'accounts': []
            }