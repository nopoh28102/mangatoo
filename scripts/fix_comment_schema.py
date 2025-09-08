from app import app, db
from sqlalchemy import text

def fix_comment_schema():
    """Make chapter_id nullable in comments table to allow manga comments"""
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                # Create a new table with the correct schema
                conn.execute(text("""
                    CREATE TABLE comment_new (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        chapter_id INTEGER NULL,
                        manga_id INTEGER NULL,
                        content TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES user(id),
                        FOREIGN KEY(chapter_id) REFERENCES chapter(id),
                        FOREIGN KEY(manga_id) REFERENCES manga(id)
                    )
                """))
                
                # Copy existing data
                conn.execute(text("""
                    INSERT INTO comment_new (id, user_id, chapter_id, manga_id, content, created_at)
                    SELECT id, user_id, chapter_id, manga_id, content, created_at FROM comment
                """))
                
                # Drop old table and rename new one
                conn.execute(text("DROP TABLE comment"))
                conn.execute(text("ALTER TABLE comment_new RENAME TO comment"))
                
                conn.commit()
                print("Successfully fixed comment table schema")
                
        except Exception as e:
            print(f"Error fixing schema: {e}")

if __name__ == '__main__':
    fix_comment_schema()