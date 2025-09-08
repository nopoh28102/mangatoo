from app import app, db
from sqlalchemy import text

def update_comments_database():
    """Update comments table to add new fields and create reactions table"""
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                # First, backup existing comments
                existing_comments = conn.execute(text("SELECT * FROM comment")).fetchall()
                print(f"Found {len(existing_comments)} existing comments")
                
                # Drop existing comment table
                conn.execute(text("DROP TABLE IF EXISTS comment"))
                
                # Create new comment table with all fields
                conn.execute(text("""
                    CREATE TABLE comment (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        chapter_id INTEGER NULL,
                        manga_id INTEGER NULL,
                        content TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_approved BOOLEAN DEFAULT 1,
                        is_edited BOOLEAN DEFAULT 0,
                        parent_id INTEGER NULL,
                        FOREIGN KEY(user_id) REFERENCES user(id),
                        FOREIGN KEY(chapter_id) REFERENCES chapter(id),
                        FOREIGN KEY(manga_id) REFERENCES manga(id),
                        FOREIGN KEY(parent_id) REFERENCES comment(id)
                    )
                """))
                print("Created new comment table with all fields")
                
                # Restore existing comments
                for comment in existing_comments:
                    conn.execute(text("""
                        INSERT INTO comment (id, user_id, chapter_id, manga_id, content, created_at, updated_at, is_approved, is_edited, parent_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, NULL)
                    """), (comment[0], comment[1], comment[2], comment[3], comment[4], comment[5], comment[5]))
                
                print(f"Restored {len(existing_comments)} comments")
                
                # Create comment_reaction table if it doesn't exist
                try:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS comment_reaction (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            comment_id INTEGER NOT NULL,
                            reaction_type VARCHAR(20) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(user_id) REFERENCES user(id),
                            FOREIGN KEY(comment_id) REFERENCES comment(id),
                            UNIQUE(user_id, comment_id)
                        )
                    """))
                    print("Created/verified comment_reaction table")
                except Exception as e:
                    print(f"Error with comment_reaction table: {e}")
                
                conn.commit()
                print("Successfully updated comments database schema")
                
        except Exception as e:
            print(f"Error updating database schema: {e}")

if __name__ == '__main__':
    update_comments_database()