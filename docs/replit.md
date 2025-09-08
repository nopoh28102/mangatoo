# Overview

This is a comprehensive manga platform built with Flask that provides a complete reading experience for manga and manhwa content. The platform supports both Arabic and English languages with features including user management, chapter uploading, image optimization, content scraping, payment processing, and administrative tools. The system is designed to handle large-scale manga hosting with support for multiple storage backends and deployment environments.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
The application is built on Flask with SQLAlchemy as the ORM, supporting multiple database backends (SQLite, PostgreSQL, MySQL) through a dynamic configuration system. The architecture follows a modular pattern with separate modules for different functionalities:

- **Database Layer**: Dynamic database configuration supporting SQLite (development), PostgreSQL (production), and MySQL
- **Model Layer**: Comprehensive data models including User, Manga, Chapter, PageImage, Category, Comment, Payment, and many others
- **Route Layer**: Extensive routing system handling web interface, API endpoints, and admin functionality
- **Utils Layer**: Utility modules for image processing, settings management, SEO, payments, and cloud storage

## Frontend Architecture
The system uses server-side rendering with Flask templates, supporting bilingual content (Arabic/English) with dynamic URL generation and SEO optimization.

## Data Storage Solutions
- **Primary Storage**: SQLite for development, PostgreSQL/MySQL for production
- **File Storage**: Local filesystem with optional Cloudinary integration for image hosting
- **Image Processing**: PIL-based optimization with support for multiple formats (JPEG, PNG, WebP, GIF)
- **Background Processing**: Queue-based system for handling large uploads and image processing

## Authentication and Authorization
- **User Management**: Flask-Login with support for multiple user roles (admin, publisher, translator)
- **OAuth Integration**: Google OAuth support with fallback to traditional password authentication
- **Premium System**: Subscription-based premium features with payment processing
- **Security**: CSRF protection, secure sessions, and input validation

## Key Features
- **Content Management**: ZIP-based chapter uploads, automatic image optimization, and content scraping
- **Multi-language Support**: Arabic/English interface with RTL support
- **SEO Optimization**: Dynamic sitemap generation, meta tags, and URL optimization
- **Payment Processing**: Multiple gateway support with currency conversion
- **Admin Panel**: Comprehensive administration interface for content and user management
- **Background Tasks**: Automated scraping, image processing, and maintenance tasks

# External Dependencies

## Core Framework Dependencies
- **Flask**: Web framework with extensions for SQLAlchemy, Login, and CSRF protection
- **SQLAlchemy**: Database ORM with support for multiple database backends
- **Werkzeug**: WSGI utilities and security functions

## Image Processing
- **Pillow (PIL)**: Image processing, optimization, and format conversion
- **Cloudinary**: Optional cloud-based image storage and optimization service

## Web Scraping and Content
- **BeautifulSoup4**: HTML parsing for content scraping
- **Requests**: HTTP client for external API calls and content fetching
- **Trafilatura**: Text extraction and content parsing

## Database Support
- **psycopg2**: PostgreSQL database adapter (production)
- **PyMySQL**: MySQL database adapter (optional)
- **SQLite**: Built-in database support (development)

## Payment Processing
- **Stripe**: Payment gateway integration (configurable)
- Multiple payment gateway support through modular design

## Development and Deployment
- **Gunicorn**: WSGI HTTP server for production deployment
- **Schedule**: Task scheduling for background processes
- Environment-specific configuration for Replit, Railway, Heroku, and other platforms

## Optional Services
- **Google OAuth**: Social authentication
- **Cloudinary**: Cloud image storage and CDN
- **External APIs**: Currency conversion, content scraping from various manga sites