"""
Cloudinary integration utilities for manga chapter image uploads
Handles image upload, optimization, and URL generation for all upload methods
"""

import os
import tempfile
import logging
import zipfile
import shutil
from typing import List, Dict, Optional, Tuple
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import cloudinary.api
from PIL import Image
import requests
from io import BytesIO

# Configure Cloudinary - will be set dynamically from database
def configure_cloudinary_from_db():
    """Configure Cloudinary using database credentials"""
    try:
        from models_cloudinary import CloudinaryAccount
        from app import app
        
        with app.app_context():
            # Get primary active account
            account = CloudinaryAccount.query.filter_by(
                is_active=True, 
                is_primary=True
            ).first()
            
            if not account:
                # Fallback to any active account
                account = CloudinaryAccount.query.filter_by(is_active=True).first()
            
            if account:
                cloudinary.config(
                    cloud_name=account.cloud_name,
                    api_key=account.api_key,
                    api_secret=account.api_secret
                )
                logging.info(f"✅ Configured Cloudinary with account: {account.name}")
                return account
            else:
                logging.error("❌ No active Cloudinary account found")
                return None
            
    except Exception as e:
        logging.error(f"❌ Failed to configure Cloudinary from database: {e}")
        return None

class CloudinaryAccountManager:
    """Manages multiple Cloudinary accounts with automatic switching"""
    
    def __init__(self):
        self.current_account = None
        self.from_app = None
    
    def get_available_account(self):
        """Get the most suitable available Cloudinary account"""
        try:
            from models_cloudinary import CloudinaryAccount
            from app import app, db
            
            with app.app_context():
                # Get accounts ordered by priority (primary first, then by priority_order)
                accounts = CloudinaryAccount.query.filter_by(
                    is_active=True
                ).order_by(
                    CloudinaryAccount.is_primary.desc(),
                    CloudinaryAccount.priority_order.asc()
                ).all()
                
                for account in accounts:
                    # Check if account has available storage (less than 95% full)
                    if account.storage_usage_percentage < 95:
                        logging.info(f"🎯 Selected Cloudinary account: {account.name} ({account.storage_usage_percentage:.1f}% full)")
                        return account
                
                # If all accounts are near full, use the one with most space
                if accounts:
                    best_account = min(accounts, key=lambda a: a.storage_usage_percentage)
                    logging.warning(f"⚠️ All accounts near full, using best available: {best_account.name} ({best_account.storage_usage_percentage:.1f}% full)")
                    return best_account
                
                logging.error("❌ No Cloudinary accounts available")
                return None
                
        except Exception as e:
            logging.error(f"❌ Error getting available account: {e}")
            return None
    
    def configure_cloudinary_with_account(self, account):
        """Configure Cloudinary with specific account"""
        try:
            if not account:
                return False
                
            cloudinary.config(
                cloud_name=account.cloud_name,
                api_key=account.api_key,
                api_secret=account.api_secret
            )
            
            self.current_account = account
            logging.info(f"✅ Configured Cloudinary with account: {account.name}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Failed to configure Cloudinary with account: {e}")
            return False
    
    def switch_to_next_account(self):
        """Switch to the next available account when current is full"""
        try:
            from models_cloudinary import CloudinaryAccount
            from app import app, db
            
            with app.app_context():
                if self.current_account:
                    # Mark current account as near full if needed
                    if self.current_account.storage_usage_percentage > 95:
                        logging.warning(f"🚨 Account {self.current_account.name} is full, switching...")
                        
                        # Don't deactivate, just deprioritize
                        self.current_account.priority_order += 1000
                        db.session.commit()
                
                # Find next available account
                next_account = self.get_available_account()
                if next_account and next_account != self.current_account:
                    if self.configure_cloudinary_with_account(next_account):
                        logging.info(f"🔄 Successfully switched from {self.current_account.name if self.current_account else 'None'} to {next_account.name}")
                        return True
                
                return False
                
        except Exception as e:
            logging.error(f"❌ Error switching accounts: {e}")
            return False
    
    def update_account_usage(self, account, bytes_uploaded):
        """Update account usage statistics"""
        try:
            from app import db
            
            if account and bytes_uploaded > 0:
                account.storage_used_mb += bytes_uploaded / (1024 * 1024)  # Convert to MB
                db.session.commit()
                logging.info(f"📊 Updated usage for {account.name}: {account.storage_usage_percentage:.1f}% full")
                
        except Exception as e:
            logging.error(f"❌ Error updating account usage: {e}")

# Global account manager instance
account_manager = CloudinaryAccountManager()

class CloudinaryUploader:
    """Handles all Cloudinary operations for manga images with auto account switching"""
    
    def __init__(self):
        self.folder_prefix = "manga_chapters"
        self.quality = "auto:best"
        # Initialize account manager
        self.account_manager = account_manager
        
    def upload_image_file(self, file_obj, manga_id: int, chapter_id: int, page_number: int) -> Dict:
        """
        Upload a single image file to Cloudinary with automatic account switching
        
        Args:
            file_obj: File object or file path
            manga_id: Manga ID
            chapter_id: Chapter ID  
            page_number: Page number for ordering
            
        Returns:
            Dict with success status, URL, and metadata
        """
        try:
            # Get best available account
            account = self.account_manager.get_available_account()
            if not account:
                return {
                    'success': False,
                    'error': 'No Cloudinary accounts available',
                    'page_number': page_number
                }
            
            # Configure Cloudinary with selected account
            if not self.account_manager.configure_cloudinary_with_account(account):
                return {
                    'success': False,
                    'error': 'Failed to configure Cloudinary account',
                    'page_number': page_number
                }
            
            public_id = f"{self.folder_prefix}/manga_{manga_id}/chapter_{chapter_id}/page_{page_number:03d}"
            
            # Simplified upload configuration for speed
            upload_options = {
                'public_id': public_id,
                'folder': f"{self.folder_prefix}/manga_{manga_id}",
                'quality': 'auto:low',  # Lower quality for faster upload
                'format': 'webp',       # WebP for better compression
                'overwrite': True,
                'timeout': 10           # Reduced timeout
            }
            
            # Upload the image
            result = cloudinary.uploader.upload(file_obj, **upload_options)
            
            # Update account usage statistics
            if result.get('bytes'):
                self.account_manager.update_account_usage(account, result['bytes'])
            
            # Check if account is getting full and log warning
            if account.storage_usage_percentage > 90:
                logging.warning(f"⚠️ Account {account.name} is {account.storage_usage_percentage:.1f}% full - consider adding more accounts")
            
            return {
                'success': True,
                'url': result['secure_url'],
                'public_id': result['public_id'],
                'width': result.get('width'),
                'height': result.get('height'),
                'format': result.get('format'),
                'bytes': result.get('bytes'),
                'page_number': page_number,
                'account_used': account.name
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # Check if error is due to storage limit and try to switch accounts
            if 'storage limit' in error_msg.lower() or 'quota' in error_msg.lower():
                logging.warning(f"🚨 Storage limit reached, attempting to switch accounts...")
                
                if self.account_manager.switch_to_next_account():
                    logging.info(f"🔄 Switched to new account, retrying upload...")
                    # Retry upload with new account (recursive call, but only once)
                    if hasattr(self, '_retry_count'):
                        self._retry_count += 1
                    else:
                        self._retry_count = 1
                    
                    if self._retry_count <= 1:  # Prevent infinite recursion
                        return self.upload_image_file(file_obj, manga_id, chapter_id, page_number)
                
            logging.error(f"❌ Cloudinary upload failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'page_number': page_number
            }
    
    def upload_from_zip(self, zip_file, manga_id: int, chapter_id: int) -> List[Dict]:
        """
        Extract images from ZIP file and upload to Cloudinary
        
        Args:
            zip_file: ZIP file object
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            List of upload results
        """
        results = []
        temp_dir = None
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            
            # Save ZIP file temporarily
            zip_path = os.path.join(temp_dir, 'chapter.zip')
            zip_file.save(zip_path)
            
            # Extract images from ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find all image files
            image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
            image_files = []
            
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith(image_extensions):
                        image_files.append(os.path.join(root, file))
            
            # Sort images by name for proper order
            image_files.sort()
            
            logging.info(f"Found {len(image_files)} images in ZIP file")
            
            # Upload each image to Cloudinary
            for i, image_path in enumerate(image_files, 1):
                try:
                    result = self.upload_image_file(image_path, manga_id, chapter_id, i)
                    results.append(result)
                    
                    if result['success']:
                        logging.info(f"Uploaded page {i}: {result['url']}")
                    else:
                        logging.error(f"Failed to upload page {i}: {result.get('error')}")
                        
                except Exception as e:
                    logging.error(f"Error uploading page {i}: {e}")
                    results.append({
                        'success': False,
                        'error': str(e),
                        'page_number': i
                    })
            
        except Exception as e:
            logging.error(f"ZIP extraction failed: {e}")
            results.append({
                'success': False,
                'error': f"ZIP extraction failed: {str(e)}",
                'page_number': 0
            })
            
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        
        return results
    
    def upload_multiple_files(self, file_list, manga_id: int, chapter_id: int) -> List[Dict]:
        """
        Upload multiple image files to Cloudinary
        
        Args:
            file_list: List of file objects
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            List of upload results
        """
        results = []
        
        for i, file_obj in enumerate(file_list, 1):
            if file_obj and file_obj.filename:
                try:
                    result = self.upload_image_file(file_obj, manga_id, chapter_id, i)
                    results.append(result)
                    
                    if result['success']:
                        logging.info(f"Uploaded page {i}: {result['url']}")
                    else:
                        logging.error(f"Failed to upload page {i}: {result.get('error')}")
                        
                except Exception as e:
                    logging.error(f"Error uploading page {i}: {e}")
                    results.append({
                        'success': False,
                        'error': str(e),
                        'page_number': i
                    })
        
        return results
    
    def upload_scraped_images(self, image_urls: List[str], manga_id: int, chapter_id: int, headers: Optional[Dict] = None) -> List[Dict]:
        """
        Download and upload scraped images to Cloudinary with better timeout handling
        
        Args:
            image_urls: List of image URLs
            manga_id: Manga ID
            chapter_id: Chapter ID
            headers: HTTP headers for downloading
            
        Returns:
            List of upload results
        """
        results = []
        headers = headers or {}
        successful_uploads = 0
        
        logging.info(f"🚀 Starting upload of {len(image_urls)} images to Cloudinary")
        
        for i, url in enumerate(image_urls, 1):
            try:
                # Super fast processing with minimal timeout
                response = requests.get(url, headers=headers, stream=True, timeout=5)
                response.raise_for_status()
                
                # Upload to Cloudinary with minimal processing
                image_data = BytesIO(response.content)
                result = self.upload_image_file(image_data, manga_id, chapter_id, i)
                results.append(result)
                
                if result['success']:
                    successful_uploads += 1
                    logging.info(f"✅ Uploaded page {i}/{len(image_urls)}")
                else:
                    logging.error(f"❌ Failed to upload page {i}: {result.get('error')}")
                    
                # Progress logging every 2 images for faster feedback
                if i % 2 == 0:
                    logging.info(f"📊 Progress: {i}/{len(image_urls)} images processed, {successful_uploads} successful")
                    
            except Exception as e:
                logging.error(f"❌ Error processing image {i}: {e}")
                results.append({
                    'success': False,
                    'error': str(e),
                    'page_number': i
                })
        
        logging.info(f"🎯 Upload completed: {successful_uploads}/{len(image_urls)} images uploaded successfully")
        return results
    
    def fast_upload_scraped_image(self, image_url: str, manga_id: int, chapter_id: int, page_number: int, headers: Optional[Dict] = None) -> Dict:
        """
        Ultra-fast upload for scraped images with minimal processing and auto account switching
        """
        try:
            # Get best available account
            account = self.account_manager.get_available_account()
            if not account:
                return {'success': False, 'error': 'No Cloudinary accounts available', 'page_number': page_number}
            
            # Configure Cloudinary with selected account
            if not self.account_manager.configure_cloudinary_with_account(account):
                return {'success': False, 'error': 'Failed to configure account', 'page_number': page_number}
            
            # Download with minimal timeout
            response = requests.get(image_url, headers=headers or {}, timeout=3, stream=True)
            response.raise_for_status()
            
            # Ultra-minimal upload options for speed
            public_id = f"manga_{manga_id}/chapter_{chapter_id}/page_{page_number:03d}"
            
            result = cloudinary.uploader.upload(
                BytesIO(response.content),
                public_id=public_id,
                quality='auto:low',
                format='webp',
                overwrite=True,
                timeout=8
            )
            
            # Update account usage
            if result.get('bytes'):
                self.account_manager.update_account_usage(account, result['bytes'])
            
            return {
                'success': True,
                'url': result['secure_url'],
                'page_number': page_number,
                'account_used': account.name
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # Handle storage limit errors with account switching
            if 'storage limit' in error_msg.lower() or 'quota' in error_msg.lower():
                logging.warning(f"🚨 Storage limit reached on fast upload, switching accounts...")
                
                if self.account_manager.switch_to_next_account():
                    # Retry once with new account
                    if not hasattr(self, '_fast_retry_count'):
                        self._fast_retry_count = 0
                    
                    if self._fast_retry_count < 1:
                        self._fast_retry_count += 1
                        return self.fast_upload_scraped_image(image_url, manga_id, chapter_id, page_number, headers)
            
            return {
                'success': False,
                'error': str(e),
                'page_number': page_number
            }

    def delete_chapter_images(self, manga_id: int, chapter_id: int) -> Dict:
        """
        Delete all images for a specific chapter from Cloudinary
        
        Args:
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            Dict with success status and details
        """
        try:
            # Configure Cloudinary
            if not configure_cloudinary_from_db():
                return {'success': False, 'error': 'Failed to configure Cloudinary'}
            
            # Delete all images with the chapter prefix
            prefix = f"manga_{manga_id}/chapter_{chapter_id}/"
            
            # Get all resources with this prefix
            search_result = cloudinary.api.resources_by_tag(
                tag=f"manga_{manga_id}_chapter_{chapter_id}",
                resource_type="image",
                max_results=500
            )
            
            deleted_count = 0
            errors = []
            
            # If no tagged resources, try prefix search
            if not search_result.get('resources'):
                # Search by prefix (less reliable but backup method)
                try:
                    search_result = cloudinary.api.resources(
                        type="upload",
                        prefix=prefix,
                        max_results=500
                    )
                except Exception as e:
                    logging.warning(f"Prefix search failed: {e}")
            
            # Delete each image
            for resource in search_result.get('resources', []):
                try:
                    cloudinary.uploader.destroy(resource['public_id'])
                    deleted_count += 1
                    logging.info(f"✅ Deleted Cloudinary image: {resource['public_id']}")
                except Exception as e:
                    error_msg = f"Failed to delete {resource['public_id']}: {e}"
                    errors.append(error_msg)
                    logging.error(f"❌ {error_msg}")
            
            # Try to delete folder if empty
            try:
                folder_path = f"manga_{manga_id}/chapter_{chapter_id}"
                cloudinary.api.delete_folder(folder_path)
                logging.info(f"✅ Deleted Cloudinary folder: {folder_path}")
            except Exception as e:
                logging.warning(f"Could not delete folder (may not be empty): {e}")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'errors': errors
            }
            
        except Exception as e:
            logging.error(f"❌ Error deleting chapter images from Cloudinary: {e}")
            return {'success': False, 'error': str(e)}
    
    def delete_manga_images(self, manga_id: int) -> Dict:
        """
        Delete all images for a specific manga from Cloudinary
        
        Args:
            manga_id: Manga ID
            
        Returns:
            Dict with success status and details
        """
        try:
            # Configure Cloudinary
            if not configure_cloudinary_from_db():
                return {'success': False, 'error': 'Failed to configure Cloudinary'}
            
            # Delete all images with the manga prefix
            prefix = f"manga_{manga_id}/"
            
            # Get all resources with this prefix
            try:
                search_result = cloudinary.api.resources(
                    type="upload",
                    prefix=prefix,
                    max_results=500
                )
            except Exception as e:
                logging.error(f"Failed to search for manga images: {e}")
                return {'success': False, 'error': f'Search failed: {e}'}
            
            deleted_count = 0
            errors = []
            
            # Delete each image
            for resource in search_result.get('resources', []):
                try:
                    cloudinary.uploader.destroy(resource['public_id'])
                    deleted_count += 1
                    logging.info(f"✅ Deleted Cloudinary image: {resource['public_id']}")
                except Exception as e:
                    error_msg = f"Failed to delete {resource['public_id']}: {e}"
                    errors.append(error_msg)
                    logging.error(f"❌ {error_msg}")
            
            # Try to delete manga folder
            try:
                folder_path = f"manga_{manga_id}"
                cloudinary.api.delete_folder(folder_path)
                logging.info(f"✅ Deleted Cloudinary folder: {folder_path}")
            except Exception as e:
                logging.warning(f"Could not delete manga folder: {e}")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'errors': errors
            }
            
        except Exception as e:
            logging.error(f"❌ Error deleting manga images from Cloudinary: {e}")
            return {'success': False, 'error': str(e)}
    
    def delete_single_image(self, public_id: str) -> Dict:
        """
        Delete a single image from Cloudinary
        
        Args:
            public_id: Cloudinary public ID of the image
            
        Returns:
            Dict with success status and details
        """
        try:
            # Configure Cloudinary
            if not configure_cloudinary_from_db():
                return {'success': False, 'error': 'Failed to configure Cloudinary'}
            
            result = cloudinary.uploader.destroy(public_id)
            
            if result.get('result') == 'ok':
                logging.info(f"✅ Successfully deleted image: {public_id}")
                return {'success': True, 'public_id': public_id}
            else:
                error_msg = f"Failed to delete image: {public_id} - {result}"
                logging.error(f"❌ {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            error_msg = f"Error deleting image {public_id}: {e}"
            logging.error(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}

# Create global uploader instance
cloudinary_uploader = CloudinaryUploader()