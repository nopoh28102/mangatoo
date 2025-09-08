"""
Database Configuration System
Supports dynamic switching between SQLite, PostgreSQL, and MySQL
"""

import os
import logging
from urllib.parse import urlparse

class DatabaseConfig:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.database_type = self._detect_database_type()
        
    def _detect_database_type(self):
        """Auto-detect database type based on environment"""
        database_url = os.environ.get("DATABASE_URL")
        
        if database_url:
            parsed = urlparse(database_url)
            if parsed.scheme in ['postgresql', 'postgres']:
                return 'postgresql'
            elif parsed.scheme == 'sqlite':
                return 'sqlite'
            elif parsed.scheme in ['mysql', 'mysql+pymysql']:
                return 'mysql'
        
        # Default to SQLite for new deployments
        return 'sqlite'
    
    def get_database_uri(self):
        """Get appropriate database URI"""
        if self.database_type == 'postgresql':
            return self._get_postgresql_uri()
        elif self.database_type == 'mysql':
            return self._get_mysql_uri()
        else:
            return self._get_sqlite_uri()
    
    def _get_postgresql_uri(self):
        """Get PostgreSQL connection URI"""
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            # Handle both postgresql:// and postgres:// schemes
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            return database_url
        
        # Fallback to individual components
        host = os.environ.get('DB_HOST', 'localhost')
        port = os.environ.get('DB_PORT', '5432')
        database = os.environ.get('DB_NAME', 'manga_platform')
        username = os.environ.get('DB_USER', 'postgres')
        password = os.environ.get('DB_PASSWORD', '')
        
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"
    
    def _get_sqlite_uri(self):
        """Get SQLite connection URI"""
        db_path = os.environ.get('SQLITE_PATH', 'manga_platform.db')
        return f"sqlite:///{os.path.abspath(db_path)}"
    
    def _get_mysql_uri(self):
        """Get MySQL connection URI"""
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            # Handle mysql:// and mysql+pymysql:// schemes
            if database_url.startswith('mysql://') and 'pymysql' not in database_url:
                database_url = database_url.replace('mysql://', 'mysql+pymysql://', 1)
            return database_url
        
        # Fallback to individual components
        host = os.environ.get('MYSQL_HOST', 'localhost')
        port = os.environ.get('MYSQL_PORT', '3306')
        database = os.environ.get('MYSQL_DATABASE', 'manga_platform')
        username = os.environ.get('MYSQL_USER', 'root')
        password = os.environ.get('MYSQL_PASSWORD', '')
        
        return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
    
    def get_engine_options(self):
        """Get database engine options"""
        if self.database_type == 'postgresql':
            return {
                "pool_recycle": 300,
                "pool_pre_ping": True,
                "pool_size": 10,
                "max_overflow": 20,
                "echo": False
            }
        elif self.database_type == 'mysql':
            return {
                "pool_recycle": 300,
                "pool_pre_ping": True,
                "pool_size": 10,
                "max_overflow": 20,
                "echo": False,
                "pool_timeout": 20,
                "connect_args": {
                    "charset": "utf8mb4",
                    "use_unicode": True,
                    "autocommit": False
                }
            }
        else:
            return {
                "pool_pre_ping": True,
                "echo": False
            }
    
    def is_postgresql(self):
        """Check if using PostgreSQL"""
        return self.database_type == 'postgresql'
    
    def is_sqlite(self):
        """Check if using SQLite"""
        return self.database_type == 'sqlite'
    
    def is_mysql(self):
        """Check if using MySQL"""
        return self.database_type == 'mysql'
    
    def get_migration_info(self):
        """Get migration information"""
        return {
            'current_db': self.database_type,
            'uri': self.get_database_uri(),
            'can_migrate_to_postgresql': True,
            'can_migrate_to_mysql': True,
            'migration_required': False
        }

# Global instance
db_config = DatabaseConfig()