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
from PIL import Image
import requests
from io import BytesIO

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

class CloudinaryUploader:
    """Handles all Cloudinary operations for manga images"""
    
    def __init__(self):
        self.folder_prefix = "manga_chapters"
        self.quality = "auto:best"
        
    def upload_image_file(self, file_obj, manga_id: int, chapter_id: int, page_number: int) -> Dict:
        """
        Upload a single image file to Cloudinary
        
        Args:
            file_obj: File object or file path
            manga_id: Manga ID
            chapter_id: Chapter ID  
            page_number: Page number for ordering
            
        Returns:
            Dict with success status, URL, and metadata
        """
        try:
            public_id = f"{self.folder_prefix}/manga_{manga_id}/chapter_{chapter_id}/page_{page_number:03d}"
            
            # Upload configuration
            upload_options = {
                'public_id': public_id,
                'folder': f"{self.folder_prefix}/manga_{manga_id}",
                'quality': self.quality,
                'tags': [f'manga_{manga_id}', f'chapter_{chapter_id}', 'manga_page'],
                'context': {
                    'manga_id': str(manga_id),
                    'chapter_id': str(chapter_id),
                    'page_number': str(page_number)
                }
            }
            
            # Upload the image
            result = cloudinary.uploader.upload(file_obj, **upload_options)
            
            return {
                'success': True,
                'url': result['secure_url'],
                'public_id': result['public_id'],
                'width': result.get('width'),
                'height': result.get('height'),
                'format': result.get('format'),
                'bytes': result.get('bytes')
            }
            
        except Exception as e:
            logging.error(f"Cloudinary upload failed: {e}")
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
                    result['page_number'] = i
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
                    result['page_number'] = i
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
    
    def upload_scraped_images(self, image_urls: List[str], manga_id: int, chapter_id: int, headers: Dict = None) -> List[Dict]:
        """
        Download and upload scraped images to Cloudinary
        
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
        
        for i, url in enumerate(image_urls, 1):
            try:
                # Download image from URL
                response = requests.get(url, headers=headers, stream=True, timeout=30)
                response.raise_for_status()
                
                # Upload to Cloudinary directly from memory
                result = self.upload_image_file(BytesIO(response.content), manga_id, chapter_id, i)
                result['page_number'] = i
                results.append(result)
                
                if result['success']:
                    logging.info(f"Uploaded scraped page {i}: {result['url']}")
                else:
                    logging.error(f"Failed to upload scraped page {i}: {result.get('error')}")
                    
            except Exception as e:
                logging.error(f"Error processing scraped image {i}: {e}")
                results.append({
                    'success': False,
                    'error': str(e),
                    'page_number': i
                })
        
        return results
    
    def get_chapter_images_urls(self, manga_id: int, chapter_id: int) -> List[str]:
        """
        Get list of Cloudinary URLs for a chapter's images
        
        Args:
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            List of Cloudinary URLs in order
        """
        try:
            # Search for images in Cloudinary by tags
            result = cloudinary.api.resources_by_tag(
                f'chapter_{chapter_id}',
                type='upload',
                resource_type='image',
                max_results=500
            )
            
            # Sort by page number and return URLs
            images = result.get('resources', [])
            images.sort(key=lambda x: int(x.get('context', {}).get('page_number', 0)))
            
            return [img['secure_url'] for img in images]
            
        except Exception as e:
            logging.error(f"Failed to get chapter images: {e}")
            return []
    
# Create global uploader instance
cloudinary_uploader = CloudinaryUploader()
            page_number: Page number
            headers: Optional headers for the request
            
        Returns:
            Dict with success status, URL, and metadata
        """
        try:
            # Download image first
            response = requests.get(image_url, headers=headers if headers is not None else {}, stream=True, timeout=30)
            response.raise_for_status()
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_path = temp_file.name
            
            try:
                # Upload to Cloudinary
                result = self.upload_image_file(temp_path, manga_id, chapter_id, page_number)
                return result
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except Exception as e:
            logging.error(f"Failed to upload from URL {image_url}: {e}")
            return {
                'success': False,
                'error': str(e),
                'url': None
            }
    
    def upload_multiple_files(self, file_list: List, manga_id: int, chapter_id: int) -> List[Dict]:
        """
        Upload multiple image files to Cloudinary
        
        Args:
            file_list: List of file objects or paths
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            List of upload results
        """
        results = []
        
        for i, file_obj in enumerate(file_list, 1):
            if file_obj and hasattr(file_obj, 'filename') and file_obj.filename:
                result = self.upload_image_file(file_obj, manga_id, chapter_id, i)
                results.append({
                    'page_number': i,
                    'filename': file_obj.filename,
                    **result
                })
            elif isinstance(file_obj, str):  # File path
                result = self.upload_image_file(file_obj, manga_id, chapter_id, i)
                results.append({
                    'page_number': i,
                    'filename': os.path.basename(file_obj),
                    **result
                })
                
        return results
    
    def upload_from_zip(self, zip_file, manga_id: int, chapter_id: int) -> List[Dict]:
        """
        Extract ZIP file and upload images to Cloudinary
        
        Args:
            zip_file: ZIP file object
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            List of upload results
        """
        import zipfile
        
        results = []
        temp_dir = None
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            
            # Save ZIP file temporarily
            zip_path = os.path.join(temp_dir, 'chapter.zip')
            zip_file.save(zip_path)
            
            # Extract images
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get image files
                image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
                image_files = [f for f in zip_ref.namelist() 
                              if f.lower().endswith(image_extensions) 
                              and not f.startswith('__MACOSX/')]
                
                # Sort files naturally
                image_files.sort(key=self._natural_sort_key)
                
                # Extract and upload each image
                for i, image_file in enumerate(image_files, 1):
                    try:
                        # Extract image
                        extracted_path = zip_ref.extract(image_file, temp_dir)
                        
                        # Upload to Cloudinary
                        result = self.upload_image_file(extracted_path, manga_id, chapter_id, i)
                        results.append({
                            'page_number': i,
                            'filename': os.path.basename(image_file),
                            **result
                        })
                        
                        # Clean up extracted file
                        if os.path.exists(extracted_path):
                            os.unlink(extracted_path)
                            
                    except Exception as e:
                        logging.error(f"Failed to process image {image_file}: {e}")
                        continue
                        
        except Exception as e:
            logging.error(f"ZIP processing failed: {e}")
            
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        return results
    
    def upload_scraped_images(self, image_urls: List[str], manga_id: int, chapter_id: int, headers: Dict = None) -> List[Dict]:
        """
        Upload scraped images from URLs to Cloudinary
        
        Args:
            image_urls: List of image URLs
            manga_id: Manga ID  
            chapter_id: Chapter ID
            headers: Optional headers for requests
            
        Returns:
            List of upload results
        """
        results = []
        
        for i, img_url in enumerate(image_urls, 1):
            result = self.upload_from_url(img_url, manga_id, chapter_id, i, headers if headers is not None else {})
            results.append({
                'page_number': i,
                'source_url': img_url,
                **result
            })
            
        return results
    
    def delete_chapter_images(self, manga_id: int, chapter_id: int) -> bool:
        """
        Delete all images for a specific chapter from Cloudinary
        
        Args:
            manga_id: Manga ID
            chapter_id: Chapter ID
            
        Returns:
            Success status
        """
        try:
            # Delete by prefix
            import cloudinary.api
            prefix = f"{self.folder_prefix}/manga_{manga_id}/chapter_{chapter_id}"
            result = cloudinary.api.delete_resources_by_prefix(prefix)
            
            logging.info(f"Deleted {len(result.get('deleted', []))} images for chapter {chapter_id}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to delete chapter images: {e}")
            return False
    
    def get_optimized_url(self, public_id: str, width: int = None, height: int = None, quality: str = "auto") -> str:
        """
        Generate optimized image URL with transformations
        
        Args:
            public_id: Cloudinary public ID
            width: Target width
            height: Target height
            quality: Quality setting
            
        Returns:
            Optimized image URL
        """
        transformations = {
            'quality': quality,
            'fetch_format': 'auto'
        }
        
        if width:
            transformations['width'] = str(width)
            
        if height:
            transformations['height'] = str(height)
            
        if width or height:
            transformations['crop'] = 'scale'
            
        return cloudinary.utils.cloudinary_url(public_id, **transformations)[0]
    
    def _natural_sort_key(self, text: str):
        """Natural sorting for filenames with numbers"""
        import re
        def convert(text):
            return int(text) if text.isdigit() else text.lower()
        return [convert(c) for c in re.split('([0-9]+)', text)]

# Global instance
cloudinary_uploader = CloudinaryUploader()