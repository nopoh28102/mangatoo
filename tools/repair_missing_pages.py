#!/usr/bin/env python3
"""
Repair script to fix missing PageImage records for chapters that have images on filesystem
but no database records.
"""
import os
import re
from app import app, db
from app.models import Manga, Chapter, PageImage
from app.utils import optimize_image

def repair_missing_pages():
    """Find and repair chapters with missing PageImage records"""
    with app.app_context():
        print("=== Repairing Missing Page Records ===")
        
        # Get all chapters
        chapters = db.session.query(Chapter).all()
        print(f"Found {len(chapters)} chapters to check")
        
        for chapter in chapters:
            # Check if chapter has any page records
            existing_pages = db.session.query(PageImage).filter_by(chapter_id=chapter.id).count()
            
            # Build expected directory path
            chapter_dir = os.path.join('static/uploads/manga', str(chapter.manga_id), str(chapter.id))
            
            if os.path.exists(chapter_dir):
                # Find all image files in directory
                image_files = []
                for filename in os.listdir(chapter_dir):
                    if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                        full_path = os.path.join(chapter_dir, filename)
                        if os.path.isfile(full_path):
                            image_files.append(filename)
                
                # Sort files to maintain proper page order
                image_files.sort(key=lambda x: int(match.group(1)) if (match := re.search(r'(\d+)', x)) else 0)
                
                if image_files and existing_pages == 0:
                    print(f"\n📖 Chapter {chapter.chapter_number} (ID: {chapter.id})")
                    print(f"   Found {len(image_files)} image files but {existing_pages} database records")
                    print(f"   Creating missing PageImage records...")
                    
                    # Create PageImage records for each file
                    for i, filename in enumerate(image_files, 1):
                        image_path = os.path.join(chapter_dir, filename)
                        relative_path = f"uploads/manga/{chapter.manga_id}/{chapter.id}/{filename}"
                        
                        # Try to get image dimensions
                        try:
                            from PIL import Image
                            with Image.open(image_path) as img:
                                width, height = img.size
                        except Exception:
                            width, height = None, None
                        
                        # Create PageImage record
                        page = PageImage(
                            chapter_id=chapter.id,
                            page_number=i,
                            image_path=relative_path,
                            image_width=width,
                            image_height=height
                        )
                        db.session.add(page)
                        print(f"     Page {i}: {filename}")
                    
                    # Update chapter pages count
                    chapter.pages = len(image_files)
                    print(f"   ✅ Created {len(image_files)} page records")
                    
                elif existing_pages > 0:
                    print(f"✅ Chapter {chapter.chapter_number}: {existing_pages} pages already in database")
                elif not image_files:
                    print(f"⚠️  Chapter {chapter.chapter_number}: No image files found in {chapter_dir}")
            else:
                print(f"⚠️  Chapter {chapter.chapter_number}: Directory not found: {chapter_dir}")
        
        # Commit all changes
        try:
            db.session.commit()
            print("\n🎉 Repair completed successfully!")
            
            # Verify the fix
            print("\n=== Verification ===")
            manga = db.session.query(Manga).filter_by(slug='مغامرات-تنين-الأسطورة').first()
            if manga:
                chapters = db.session.query(Chapter).filter_by(manga_id=manga.id).all()
                for chapter in chapters:
                    page_count = db.session.query(PageImage).filter_by(chapter_id=chapter.id).count()
                    print(f"Chapter {chapter.chapter_number}: {page_count} pages")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during commit: {e}")
            raise

if __name__ == "__main__":
    repair_missing_pages()