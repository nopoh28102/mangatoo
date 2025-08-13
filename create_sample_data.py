#!/usr/bin/env python3
"""Create sample data for testing the manga platform"""

from app import app, db
from models import User, Manga, Chapter, Comment, CommentReaction, Category, manga_category
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

def create_sample_data():
    with app.app_context():
        print("Creating sample data...")
        
        # Create sample categories
        categories = [
            {"name": "Action", "name_ar": "أكشن"},
            {"name": "Romance", "name_ar": "رومانسي"},
            {"name": "Adventure", "name_ar": "مغامرة"},
            {"name": "Fantasy", "name_ar": "خيال"}
        ]
        
        category_objects = []
        for cat_data in categories:
            existing = Category.query.filter_by(name=cat_data["name"]).first()
            if not existing:
                category = Category(
                    name=cat_data["name"],
                    name_ar=cat_data["name_ar"],
                    is_active=True
                )
                db.session.add(category)
                category_objects.append(category)
            else:
                category_objects.append(existing)
        
        db.session.commit()
        
        # Create sample users if they don't exist
        users_data = [
            {"username": "أحمد_القارئ", "email": "ahmed@example.com"},
            {"username": "فاطمة_المعلقة", "email": "fatima@example.com"},
            {"username": "محمد_المحلل", "email": "mohammed@example.com"},
            {"username": "عائشة_المناقشة", "email": "aisha@example.com"}
        ]
        
        sample_users = []
        for user_data in users_data:
            existing = User.query.filter_by(username=user_data["username"]).first()
            if not existing:
                user = User(
                    username=user_data["username"],
                    email=user_data["email"],
                    password_hash=generate_password_hash("password123")
                )
                db.session.add(user)
                sample_users.append(user)
            else:
                sample_users.append(existing)
        
        db.session.commit()
        
        # Create sample manga
        manga_data = {
            "title": "مغامرات تنين الأسطورة",
            "title_ar": "مغامرات تنين الأسطورة",
            "slug": "مغامرات-تنين-الأسطورة",
            "description": "An epic adventure following a young hero who discovers their connection to ancient dragons. In a world where magic and technology collide, our protagonist must master their powers to save both worlds.",
            "description_ar": "مغامرة ملحمية تتبع بطلاً شاباً يكتشف ارتباطه بالتنانين القديمة. في عالم يتصادم فيه السحر والتكنولوجيا، يجب على بطلنا إتقان قواه لإنقاذ العالمين.",
            "author": "Dragon Master",
            "artist": "Epic Artist",
            "status": "ongoing",
            "type": "manhwa",
            "language": "ar",
            "views": random.randint(1000, 10000),
            "is_published": True
        }
        
        # Check if manga already exists
        existing_manga = Manga.query.filter_by(slug=manga_data["slug"]).first()
        if not existing_manga:
            manga = Manga(**manga_data)
            db.session.add(manga)
            db.session.commit()
            
            # Add categories to manga
            for category in category_objects[:2]:  # Add first 2 categories
                manga.categories.append(category)
            
            db.session.commit()
            
            # Create sample chapters
            for i in range(1, 6):
                chapter = Chapter(
                    title=f"الفصل {i}: {'البداية' if i == 1 else 'المغامرة تبدأ' if i == 2 else 'التحدي الأول' if i == 3 else 'القوة الجديدة' if i == 4 else 'المعركة الحاسمة'}",
                    title_ar=f"الفصل {i}",
                    chapter_number=float(i),
                    manga_id=manga.id,
                    pages=random.randint(15, 25),
                    status='published',
                    created_at=datetime.utcnow() - timedelta(days=30-i*5)
                )
                db.session.add(chapter)
            
            db.session.commit()
            
            # Create sample comments
            comment_texts = [
                "هذا المانهوا رائع جداً! أحب القصة والرسم 😍",
                "الفصل الأخير كان مذهلاً، متحمس للمزيد!",
                "البطل شخصية قوية ومحبوبة، أتطلع لرؤية تطوره",
                "الرسم جميل والألوان زاهية، يستحق المتابعة",
                "قصة مثيرة ومليئة بالمفاجآت، أنصح الجميع بقراءتها",
                "التنانين في هذا العمل مصممة بشكل رائع!",
                "أحب كيف يتطور البطل مع كل فصل",
                "النهاية المفتوحة للفصل الأخير جعلتني أريد المزيد!"
            ]
            
            # Create comments with different timestamps
            for i, text in enumerate(comment_texts):
                comment = Comment(
                    content=text,
                    user_id=sample_users[i % len(sample_users)].id,
                    manga_id=manga.id,
                    created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72))
                )
                db.session.add(comment)
                db.session.commit()
                
                # Add some reactions to comments
                for j in range(random.randint(1, 4)):
                    user = sample_users[j % len(sample_users)]
                    if user.id != comment.user_id:  # Don't react to own comment
                        reaction_types = ['love', 'thumbs_up', 'laugh', 'surprised', 'shocked']
                        reaction = CommentReaction(
                            user_id=user.id,
                            comment_id=comment.id,
                            reaction_type=random.choice(reaction_types)
                        )
                        try:
                            db.session.add(reaction)
                            db.session.commit()
                        except:
                            db.session.rollback()  # Skip if duplicate
                
                # Add some replies
                if random.choice([True, False]):
                    reply_texts = [
                        "أوافقك الرأي تماماً!",
                        "نعم، أنا أيضاً أحب هذه السلسلة",
                        "هذا صحيح، الرسم مذهل فعلاً",
                        "لا أستطيع الانتظار للفصل القادم!"
                    ]
                    
                    reply = Comment(
                        content=random.choice(reply_texts),
                        user_id=sample_users[(i + 1) % len(sample_users)].id,
                        manga_id=manga.id,
                        parent_id=comment.id,
                        created_at=comment.created_at + timedelta(minutes=random.randint(5, 120))
                    )
                    db.session.add(reply)
                    db.session.commit()
            
            print(f"Created manga: {manga.title}")
            print(f"Created {Chapter.query.filter_by(manga_id=manga.id).count()} chapters")
            print(f"Created {Comment.query.filter_by(manga_id=manga.id).count()} comments and replies")
            print(f"Created {CommentReaction.query.count()} reactions")
            
        else:
            print(f"Manga '{manga_data['title']}' already exists")
        
        print("Sample data creation completed!")

if __name__ == "__main__":
    create_sample_data()