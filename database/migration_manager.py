"""
Database Migration Manager
Handles migration between SQLite and PostgreSQL
"""

import os
import logging
import json
from datetime import datetime
try:
    from config.database_config import db_config
except ImportError:
    db_config = None
try:
    from app import db
except ImportError:
    db = None
import sqlite3
import psycopg2
from urllib.parse import urlparse

class MigrationManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def can_migrate_to_postgresql(self):
        """Check if PostgreSQL migration is possible"""
        try:
            # Check if PostgreSQL connection details are available
            postgres_url = os.environ.get("DATABASE_URL")
            if not postgres_url or not postgres_url.startswith(('postgresql://', 'postgres://')):
                return False, "PostgreSQL connection URL not found"
            
            # Test PostgreSQL connection
            parsed = urlparse(postgres_url)
            if parsed.scheme == 'postgres':
                postgres_url = postgres_url.replace('postgres://', 'postgresql://', 1)
                
            import psycopg2
            conn = psycopg2.connect(postgres_url)
            conn.close()
            return True, "PostgreSQL connection available"
            
        except ImportError:
            return False, "psycopg2 library not installed"
        except Exception as e:
            return False, f"PostgreSQL connection failed: {str(e)}"
    
    def migrate_sqlite_to_postgresql(self):
        """Migrate data from SQLite to PostgreSQL"""
        try:
            can_migrate, message = self.can_migrate_to_postgresql()
            if not can_migrate:
                return False, message
            
            # Create backup of SQLite
            backup_path = f"backup_sqlite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            os.system(f"cp manga_platform.db {backup_path}")
            
            self.logger.info("Starting migration from SQLite to PostgreSQL...")
            
            # Export data from SQLite
            sqlite_data = self._export_sqlite_data()
            
            # Switch to PostgreSQL configuration
            os.environ['DATABASE_TYPE'] = 'postgresql'
            
            # Import data to PostgreSQL
            success = self._import_postgresql_data(sqlite_data)
            
            if success:
                self.logger.info("Migration completed successfully")
                return True, "Migration completed successfully"
            else:
                return False, "Migration failed during data import"
                
        except Exception as e:
            self.logger.error(f"Migration failed: {str(e)}")
            return False, f"Migration failed: {str(e)}"
    
    def _export_sqlite_data(self):
        """Export all data from SQLite"""
        data = {}
        try:
            conn = sqlite3.connect('manga_platform.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                data[table] = [dict(row) for row in rows]
                self.logger.info(f"Exported {len(rows)} records from {table}")
            
            conn.close()
            return data
            
        except Exception as e:
            self.logger.error(f"Failed to export SQLite data: {str(e)}")
            raise
    
    def _import_postgresql_data(self, data):
        """Import data to PostgreSQL"""
        try:
            from app import app, db
            
            with app.app_context():
                # Create all tables
                db.create_all()
                
                # Import data in correct order (respecting foreign keys)
                table_order = [
                    'users', 'categories', 'manga', 'manga_category', 
                    'chapters', 'page_images', 'bookmarks', 'comments',
                    'ratings', 'reading_progress', 'notifications',
                    'subscriptions', 'payments', 'blog_posts',
                    'announcements', 'advertisements'
                ]
                
                for table in table_order:
                    if table in data and data[table]:
                        self._import_table_data(table, data[table])
                
                # Import remaining tables
                for table, records in data.items():
                    if table not in table_order and records:
                        self._import_table_data(table, records)
                
                db.session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to import PostgreSQL data: {str(e)}")
            if 'db' in locals():
                db.session.rollback()
            return False
    
    def _import_table_data(self, table_name, records):
        """Import data for a specific table"""
        try:
            if not records:
                return
                
            # Get table object
            table = db.metadata.tables.get(table_name)
            if table is None:
                self.logger.warning(f"Table {table_name} not found in metadata")
                return
            
            # Insert records
            db.session.execute(table.insert(), records)
            self.logger.info(f"Imported {len(records)} records to {table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to import {table_name}: {str(e)}")
            raise
    
    def create_migration_report(self):
        """Create migration status report"""
        report = {
            'current_database': db_config.database_type,
            'database_uri': db_config.get_database_uri(),
            'timestamp': datetime.now().isoformat(),
            'can_migrate': False,
            'migration_message': ''
        }
        
        if db_config.is_sqlite():
            can_migrate, message = self.can_migrate_to_postgresql()
            report['can_migrate'] = can_migrate
            report['migration_message'] = message
        
        return report

# Global instance
migration_manager = MigrationManager()