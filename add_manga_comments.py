from app import app, db
from sqlalchemy import text

def add_manga_comments_column():
    """Add manga_id column to comments table for manga-level comments"""
    with app.app_context():
        try:
            # Check if column already exists
            with db.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(comment)"))
                columns = [row[1] for row in result]
                
                if 'manga_id' not in columns:
                    # Add the manga_id column
                    conn.execute(text("ALTER TABLE comment ADD COLUMN manga_id INTEGER"))
                    conn.commit()
                    print("Successfully added manga_id column to comment table")
                else:
                    print("manga_id column already exists in comment table")
                    
        except Exception as e:
            print(f"Error adding manga_id column: {e}")

if __name__ == '__main__':
    add_manga_comments_column()