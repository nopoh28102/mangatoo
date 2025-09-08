"""
Background uploader for manga images
Handles temporary storage and background upload to Cloudinary
"""
import os
import time
import threading
import logging
import shutil
import requests
from pathlib import Path
from typing import List, Dict, Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.utils_cloudinary import cloudinary_uploader
    from app.models import PageImage, Chapter, db
    from app.app import app
except ImportError:
    try:
        from utils_cloudinary import cloudinary_uploader
        from models import PageImage, Chapter, db
        from app import app
    except ImportError as e:
        import logging
        logging.error(f"Failed to import required modules: {e}")
        cloudinary_uploader = None
        PageImage = None
        Chapter = None
        db = None
        app = None

class BackgroundUploader:
    def __init__(self):
        self.upload_queue = []
        self.is_uploading = False
        self.temp_storage_path = Path("static/temp_uploads")
        self.modules_available = all([cloudinary_uploader, PageImage, Chapter, db, app])
        
        # Only try to create directory in writable environments
        try:
            self.temp_storage_path.mkdir(exist_ok=True)
        except OSError as e:
            if e.errno == 30:  # Read-only file system
                logging.info("Running on read-only file system - using in-memory storage for uploads")
                # Use a temporary directory or in-memory storage for read-only systems
                import tempfile
                self.temp_storage_path = Path(tempfile.mkdtemp())
            else:
                logging.error(f"Failed to create temp storage directory: {e}")
                raise
        self.upload_progress = {}  # Track progress by chapter_id
        
        if not self.modules_available:
            logging.warning("Some required modules are not available - background uploader will have limited functionality")
        
    def add_to_upload_queue(self, manga_id: int, chapter_id: int, temp_folder: str, image_files: List[str]):
        """Add upload task to background queue"""
        if not self.modules_available:
            logging.error("Cannot add to upload queue - required modules not available")
            return False
            
        upload_task = {
            'manga_id': manga_id,
            'chapter_id': chapter_id,
            'temp_folder': temp_folder,
            'image_files': image_files,
            'timestamp': time.time()
        }
        self.upload_queue.append(upload_task)
        
        # Start background upload if not already running
        if not self.is_uploading:
            threading.Thread(target=self._process_upload_queue, daemon=True).start()
            
        logging.info(f"📥 Added {len(image_files)} images to upload queue for manga {manga_id}, chapter {chapter_id}")
        return True
        
    def _process_upload_queue(self):
        """Process upload queue in background"""
        self.is_uploading = True
        
        while self.upload_queue:
            task = self.upload_queue.pop(0)
            try:
                self._upload_task(task)
            except Exception as e:
                logging.error(f"❌ Background upload failed for task {task}: {e}")
                
        self.is_uploading = False
        logging.info("🎯 Background upload queue completed")
        
    def _upload_task(self, task: Dict):
        """Upload single task to Cloudinary"""
        manga_id = task['manga_id']
        chapter_id = task['chapter_id']
        temp_folder = task['temp_folder']
        image_files = task['image_files']
        
        # Initialize progress tracking
        self.upload_progress[chapter_id] = {
            'total_images': len(image_files),
            'uploaded_images': 0,
            'status': 'uploading',
            'percentage': 0
        }
        
        logging.info(f"🚀 Starting background upload for manga {manga_id}, chapter {chapter_id}")
        
        successful_uploads = 0
        temp_folder_path = self.temp_storage_path / temp_folder
        
        with app.app_context():
            for i, filename in enumerate(image_files, 1):
                try:
                    file_path = temp_folder_path / filename
                    if file_path.exists():
                        # Upload to Cloudinary
                        with open(file_path, 'rb') as f:
                            result = cloudinary_uploader.upload_image_file(f, manga_id, chapter_id, i)
                            
                        if result.get('success'):
                            # PageImage record is already handled by utils_cloudinary.upload_image_file()
                            # No need to create it again here to avoid duplicates
                            successful_uploads += 1
                            
                            # Delete local file after successful upload to save space
                            try:
                                self._delete_corresponding_local_file(manga_id, chapter_id, i)
                                logging.info(f"🗑️ Deleted local file for page {i} after successful Cloudinary upload")
                            except Exception as delete_error:
                                logging.warning(f"⚠️ Could not delete local file for page {i}: {delete_error}")
                            
                            # Update progress
                            if chapter_id in self.upload_progress:
                                self.upload_progress[chapter_id]['uploaded_images'] = successful_uploads
                                self.upload_progress[chapter_id]['percentage'] = round((successful_uploads / len(image_files)) * 100)
                            
                            logging.info(f"✅ Uploaded page {i}/{len(image_files)} to Cloudinary")
                        else:
                            logging.error(f"❌ Failed to upload page {i}: {result.get('error')}")
                            
                except Exception as e:
                    logging.error(f"❌ Error uploading page {i}: {e}")
                    
            # Commit all database changes
            try:
                db.session.commit()
                logging.info(f"💾 Database updated with {successful_uploads} uploaded images")
            except Exception as e:
                logging.error(f"❌ Database commit failed: {e}")
                db.session.rollback()
                
            # Update chapter status
            try:
                chapter = Chapter.query.get(chapter_id)
                if chapter:
                    chapter.pages = successful_uploads
                    chapter.status = 'published' if successful_uploads > 0 else 'pending'
                    db.session.commit()
                    logging.info(f"📖 Chapter {chapter_id} marked as available with {successful_uploads} pages")
                    
                    # Update progress to completed
                    if chapter_id in self.upload_progress:
                        self.upload_progress[chapter_id]['status'] = 'completed'
                        self.upload_progress[chapter_id]['percentage'] = 100
            except Exception as e:
                logging.error(f"❌ Failed to update chapter status: {e}")
                if chapter_id in self.upload_progress:
                    self.upload_progress[chapter_id]['status'] = 'error'
                
        # Clean up temporary files
        try:
            if temp_folder_path.exists():
                shutil.rmtree(temp_folder_path)
                logging.info(f"🗑️ Cleaned up temporary folder: {temp_folder}")
        except Exception as e:
            logging.error(f"❌ Failed to clean up temporary folder: {e}")
            
        # Clean up the entire manga chapter directory if all uploads were successful
        if successful_uploads == len(image_files) and successful_uploads > 0:
            try:
                self._cleanup_local_chapter_directory(manga_id, chapter_id)
                logging.info(f"🗑️ Cleaned up local chapter directory after all images uploaded successfully")
            except Exception as cleanup_error:
                logging.warning(f"⚠️ Could not clean up local chapter directory: {cleanup_error}")
        
        logging.info(f"🎉 Background upload completed: {successful_uploads}/{len(image_files)} images uploaded successfully")
    
    def _delete_corresponding_local_file(self, manga_id: int, chapter_id: int, page_number: int):
        """Delete the corresponding local file for a specific page after successful Cloudinary upload"""
        try:
            # Query the PageImage to get the local file path
            page_image = PageImage.query.filter_by(
                chapter_id=chapter_id,
                page_number=page_number
            ).first()
            
            if page_image and page_image.image_path and page_image.cloudinary_url:
                local_file_path = Path(page_image.image_path)
                
                # Check if file exists and delete it
                if local_file_path.exists() and local_file_path.is_file():
                    local_file_path.unlink()  # Delete the file
                    logging.info(f"🗑️ Deleted local file: {local_file_path}")
                
                # Clear the local path from database since we're using Cloudinary now
                page_image.image_path = None
                page_image.is_cloudinary = True
                db.session.commit()
                logging.info(f"💾 Updated PageImage record - cleared local path for page {page_number}")
                
        except Exception as e:
            logging.error(f"❌ Error deleting local file for page {page_number}: {e}")
    
    def _cleanup_local_chapter_directory(self, manga_id: int, chapter_id: int):
        """Clean up the entire local chapter directory after all images are uploaded to Cloudinary"""
        try:
            # Construct the path to the chapter directory
            chapter_dir = Path(f"static/uploads/manga/{manga_id}/chapter_{chapter_id}")
            
            # Alternative path patterns that might be used
            alternative_paths = [
                Path(f"static/uploads/manga/{manga_id}/chapter_{chapter_id}"),
                Path(f"static/uploads/manga/{manga_id}/{chapter_id}"),
            ]
            
            # Try to find and clean up the actual directory
            for dir_path in alternative_paths:
                if dir_path.exists() and dir_path.is_dir():
                    # Check if directory has any remaining image files
                    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
                    remaining_images = [
                        f for f in dir_path.iterdir() 
                        if f.is_file() and f.suffix.lower() in image_extensions
                    ]
                    
                    if remaining_images:
                        # Delete remaining image files
                        for img_file in remaining_images:
                            img_file.unlink()
                            logging.info(f"🗑️ Deleted remaining image: {img_file}")
                    
                    # Try to remove the directory if it's empty or only has non-image files
                    try:
                        if not any(dir_path.iterdir()):  # Directory is empty
                            dir_path.rmdir()
                            logging.info(f"🗑️ Removed empty chapter directory: {dir_path}")
                        else:
                            # Directory has non-image files, just log
                            logging.info(f"📁 Chapter directory contains non-image files: {dir_path}")
                    except OSError:
                        # Directory not empty, that's okay
                        logging.info(f"📁 Chapter directory not empty (contains other files): {dir_path}")
                    
                    break  # Found and processed the directory
            
        except Exception as e:
            logging.error(f"❌ Error cleaning up chapter directory: {e}")
        
    def save_temp_images_from_files(self, files: List, manga_id: int, chapter_id: int) -> tuple[str, List[str]]:
        """Save uploaded files to temporary storage"""
        temp_folder = f"manga_{manga_id}_chapter_{chapter_id}_{int(time.time())}"
        temp_folder_path = self.temp_storage_path / temp_folder
        temp_folder_path.mkdir(exist_ok=True)
        
        saved_files = []
        for i, file_obj in enumerate(files, 1):
            if file_obj and file_obj.filename:
                # Generate safe filename
                file_extension = Path(file_obj.filename).suffix
                safe_filename = f"page_{i:03d}{file_extension}"
                file_path = temp_folder_path / safe_filename
                
                # Save file efficiently with streaming
                try:
                    with open(file_path, 'wb') as f:
                        # Stream the file in chunks to avoid memory issues
                        file_obj.seek(0)
                        while True:
                            chunk = file_obj.read(8192)  # 8KB chunks
                            if not chunk:
                                break
                            f.write(chunk)
                    saved_files.append(safe_filename)
                except Exception as save_error:
                    logging.error(f"❌ Failed to save {safe_filename}: {save_error}")
                    continue
                
        logging.info(f"💾 Saved {len(saved_files)} files to temporary storage: {temp_folder}")
        return temp_folder, saved_files
        
    def save_temp_images_from_files_async(self, files: List, manga_id: int, chapter_id: int) -> tuple[str, List[str]]:
        """Start async upload process immediately without waiting for file saving"""
        temp_folder = f"manga_{manga_id}_chapter_{chapter_id}_{int(time.time())}"
        
        # Get expected file list and read file data immediately before files close
        expected_files = []
        file_data_list = []
        for i, file_obj in enumerate(files, 1):
            if file_obj and file_obj.filename:
                file_extension = Path(file_obj.filename).suffix
                safe_filename = f"page_{i:03d}{file_extension}"
                expected_files.append(safe_filename)
                
                # Read file data immediately while file is still open
                file_obj.seek(0)
                file_data = file_obj.read()
                file_data_list.append({
                    'filename': safe_filename,
                    'data': file_data
                })
        
        # Start background process immediately
        upload_task = {
            'manga_id': manga_id,
            'chapter_id': chapter_id,
            'temp_folder': temp_folder,
            'file_data_list': file_data_list,
            'expected_files': expected_files,
            'timestamp': time.time()
        }
        
        # Add to queue and start immediately
        threading.Thread(target=self._async_save_and_upload, args=(upload_task,), daemon=True).start()
        
        logging.info(f"🚀 Started async save and upload for {len(expected_files)} files")
        return temp_folder, expected_files
        
    def _async_save_and_upload(self, task: Dict):
        """Save files and upload in single background thread"""
        manga_id = task['manga_id']
        chapter_id = task['chapter_id']
        temp_folder = task['temp_folder']
        file_data_list = task['file_data_list']
        expected_files = task['expected_files']
        
        temp_folder_path = self.temp_storage_path / temp_folder
        temp_folder_path.mkdir(exist_ok=True)
        
        # Save files quickly in background using pre-read data
        saved_files = []
        for file_info in file_data_list:
            filename = file_info['filename']
            file_data = file_info['data']
            file_path = temp_folder_path / filename
            
            try:
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                saved_files.append(filename)
                logging.info(f"💾 Saved {filename} to temporary storage")
            except Exception as save_error:
                logging.error(f"❌ Failed to save {filename}: {save_error}")
                continue
        
        # Update task for upload
        upload_task = {
            'manga_id': manga_id,
            'chapter_id': chapter_id,
            'temp_folder': temp_folder,
            'image_files': saved_files,
            'timestamp': task['timestamp']
        }
        
        # Upload immediately
        self._upload_task(upload_task)
        
    def save_temp_images_from_zip(self, zip_file, manga_id: int, chapter_id: int) -> tuple[str, List[str]]:
        """Extract ZIP and save to temporary storage"""
        import zipfile
        
        temp_folder = f"manga_{manga_id}_chapter_{chapter_id}_{int(time.time())}"
        temp_folder_path = self.temp_storage_path / temp_folder
        temp_folder_path.mkdir(exist_ok=True)
        
        saved_files = []
        
        # Save ZIP file temporarily
        zip_path = temp_folder_path / "chapter.zip"
        zip_file.save(str(zip_path))
        
        # Extract images
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            image_files = [f for f in zip_ref.namelist() 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
            image_files.sort()
            
            for i, filename in enumerate(image_files, 1):
                file_extension = Path(filename).suffix
                safe_filename = f"page_{i:03d}{file_extension}"
                
                # Extract and save with safe name
                with zip_ref.open(filename) as source:
                    file_path = temp_folder_path / safe_filename
                    with open(file_path, 'wb') as target:
                        target.write(source.read())
                        
                saved_files.append(safe_filename)
                
        # Remove ZIP file
        zip_path.unlink()
        
        logging.info(f"📦 Extracted {len(saved_files)} images from ZIP to temporary storage: {temp_folder}")
        return temp_folder, saved_files
        
    def save_temp_images_from_urls(self, image_urls: List[str], manga_id: int, chapter_id: int, headers: Optional[Dict] = None) -> tuple[str, List[str]]:
        """Download images from URLs and save to temporary storage"""
        import requests
        
        temp_folder = f"manga_{manga_id}_chapter_{chapter_id}_{int(time.time())}"
        temp_folder_path = self.temp_storage_path / temp_folder
        temp_folder_path.mkdir(exist_ok=True)
        
        saved_files = []
        headers = headers or {}
        
        for i, url in enumerate(image_urls, 1):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Determine file extension
                content_type = response.headers.get('content-type', '')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    ext = '.jpg'
                elif 'png' in content_type:
                    ext = '.png'
                elif 'webp' in content_type:
                    ext = '.webp'
                else:
                    ext = '.jpg'  # Default
                    
                safe_filename = f"page_{i:03d}{ext}"
                file_path = temp_folder_path / safe_filename
                
                # Save image
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                    
                saved_files.append(safe_filename)
                logging.info(f"⬇️ Downloaded page {i}/{len(image_urls)}")
                
            except Exception as e:
                logging.error(f"❌ Failed to download page {i}: {e}")
                
        logging.info(f"🕸️ Downloaded {len(saved_files)} images to temporary storage: {temp_folder}")
        return temp_folder, saved_files

# Global background uploader instance
background_uploader = BackgroundUploader()