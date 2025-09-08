"""
Utility functions for handling manga-category relationships
"""
from app import db
from models import Manga, Category


def add_category_to_manga(manga_id, category_id):
    """
    Safely add a category to a manga, avoiding duplicate entries
    """
    try:
        manga = Manga.query.get(manga_id)
        category = Category.query.get(category_id)
        
        if not manga or not category:
            return False, "المانجا أو الفئة غير موجودة"
        
        # Check if the relationship already exists
        if category in manga.categories:
            return True, "الفئة مرتبطة بالمانجا بالفعل"
        
        # Add the category to the manga
        manga.categories.append(category)
        db.session.commit()
        
        return True, "تم ربط الفئة بالمانجا بنجاح"
    
    except Exception as e:
        db.session.rollback()
        return False, f"خطأ في ربط الفئة: {str(e)}"


def remove_category_from_manga(manga_id, category_id):
    """
    Remove a category from a manga
    """
    try:
        manga = Manga.query.get(manga_id)
        category = Category.query.get(category_id)
        
        if not manga or not category:
            return False, "المانجا أو الفئة غير موجودة"
        
        # Check if the relationship exists
        if category not in manga.categories:
            return True, "الفئة غير مرتبطة بالمانجا"
        
        # Remove the category from the manga
        manga.categories.remove(category)
        db.session.commit()
        
        return True, "تم إلغاء ربط الفئة من المانجا بنجاح"
    
    except Exception as e:
        db.session.rollback()
        return False, f"خطأ في إلغاء ربط الفئة: {str(e)}"


def set_manga_categories(manga_id, category_ids):
    """
    Set all categories for a manga at once, replacing existing ones
    """
    try:
        manga = Manga.query.get(manga_id)
        if not manga:
            return False, "المانجا غير موجودة"
        
        # Get all valid categories
        categories = Category.query.filter(Category.id.in_(category_ids)).all()
        
        # Clear existing categories and set new ones
        manga.categories.clear()
        manga.categories.extend(categories)
        db.session.commit()
        
        return True, f"تم تحديث فئات المانجا بنجاح ({len(categories)} فئة)"
    
    except Exception as e:
        db.session.rollback()
        return False, f"خطأ في تحديث الفئات: {str(e)}"


def get_manga_categories(manga_id):
    """
    Get all categories for a specific manga
    """
    try:
        manga = Manga.query.get(manga_id)
        if not manga:
            return []
        
        return [{'id': cat.id, 'name': cat.name, 'name_ar': cat.name_ar} 
                for cat in manga.categories]
    
    except Exception as e:
        return []