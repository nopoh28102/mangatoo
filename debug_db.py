#!/usr/bin/env python3
import os
from app import app, db
from models import Manga, Chapter, PageImage

def check_database():
    with app.app_context():
        print("=== Database Debug ===")
        
        # Check all manga
        all_manga = db.session.query(Manga).all()
        print(f"Total manga in database: {len(all_manga)}")
        
        for manga in all_manga:
            print(f"\nManga: {manga.title}")
            print(f"  ID: {manga.id}")
            print(f"  Slug: {manga.slug}")
            
            chapters = db.session.query(Chapter).filter_by(manga_id=manga.id).all()
            print(f"  Chapters: {len(chapters)}")
            
            for chapter in chapters[:3]:  # Show first 3 chapters
                pages = db.session.query(PageImage).filter_by(chapter_id=chapter.id).all()
                print(f"    Chapter {chapter.chapter_number}: {len(pages)} pages")
                if len(pages) == 0:
                    print(f"      ⚠️  No pages found for chapter {chapter.id}")
                else:
                    print(f"      ✓ Found {len(pages)} pages")

if __name__ == "__main__":
    check_database()