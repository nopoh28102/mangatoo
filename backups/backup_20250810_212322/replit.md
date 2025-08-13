# Overview

This is a comprehensive manga reading platform built with Flask that provides a multi-language (Arabic/English) interface for reading manga, manhwa, and manhua. The platform features a complete content management system with user authentication, publisher tools, premium subscriptions, automated content scraping capabilities, and an admin dashboard. It's designed to handle large-scale manga distribution with advanced reading features, social interactions, and monetization options.

## Recent Updates (August 10, 2025)
- ✅ CRITICAL: Fixed UNIQUE constraint error in manga_category table 
- ✅ Resolved all 10 constructor issues in database models
- ✅ Reduced LSP diagnostics from 31 to 0 errors
- ✅ Created utils_manga_category.py for safe relationship management
- ✅ Added missing fields: avatar_url, is_premium for chapters
- ✅ Fixed is_active property conflict with UserMixin
- ✅ Database schema fully operational with all new fields

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: Flask with SQLAlchemy ORM for database operations
- **Database**: SQLite for development (designed to work with PostgreSQL in production)
- **Authentication**: Flask-Login for session management with role-based access control (admin, publisher, translator, premium users)
- **File Storage**: Local filesystem with optimized image handling using Pillow
- **Content Management**: Comprehensive manga/chapter upload system with support for ZIP archives and individual image files

## Frontend Architecture
- **Template Engine**: Jinja2 with multi-language support (Arabic/English)
- **Styling**: Bootstrap 5 with custom CSS implementing a unified dark theme
- **JavaScript**: Modular approach with separate managers for different features (Theme, Language, Reader, Admin)
- **Reading Interface**: Advanced manga reader with multiple viewing modes (vertical, horizontal, webtoon), zoom controls, and touch gesture support

## Data Architecture
The application uses a complex relational database schema with over 25 models including:
- **Content Models**: Manga, Chapter, PageImage with metadata and relationships
- **User Models**: User accounts with roles, subscriptions, reading progress, bookmarks
- **Social Features**: Comments, ratings, reactions, notifications
- **Commerce**: Payment plans, gateways, subscriptions with multi-currency support
- **Automation**: Auto-scraping system for external manga sources

## Content Scraping System
- **Automated Scraping**: Scheduled scraping from external manga sites (specifically OlympusStaff)
- **Queue Management**: Background processing system for scraping tasks
- **Image Processing**: Automatic image optimization and format conversion
- **Error Handling**: Comprehensive logging and retry mechanisms for failed scraping attempts

## SEO and Performance
- **SEO Optimization**: Meta tags, Open Graph, Twitter Cards, structured data (JSON-LD)
- **Sitemap Generation**: Dynamic sitemap creation for search engines
- **Image Optimization**: Automatic image compression and format conversion
- **Caching Strategy**: Settings management with caching layer

## Security and Permissions
- **Role-Based Access**: Admin, publisher, translator, and premium user roles
- **Content Moderation**: Comment approval system and content reporting
- **File Upload Security**: Secure filename handling and file type validation
- **CSRF Protection**: Built-in Flask security features

# External Dependencies

## Core Python Libraries
- **Flask Ecosystem**: Flask, Flask-SQLAlchemy, Flask-Login for web framework and ORM
- **Image Processing**: Pillow (PIL) for image manipulation and optimization
- **Web Scraping**: BeautifulSoup4, requests for content extraction from external sites
- **Database**: SQLAlchemy with support for SQLite/PostgreSQL migration

## Frontend Libraries
- **Bootstrap 5**: UI framework for responsive design
- **Font Awesome**: Icon library for consistent iconography
- **Custom JavaScript**: Modular JavaScript for reader functionality and UI interactions

## Payment Integration
- **Multi-Gateway Support**: Stripe, PayPal, and regional payment processors
- **Currency Conversion**: Real-time exchange rate support for international users
- **Subscription Management**: Recurring payment handling and premium feature gating

## Content Delivery
- **Image Storage**: Local filesystem with provisions for CDN integration
- **Archive Support**: ZIP/CBZ file processing for batch chapter uploads
- **Format Support**: JPEG, PNG, WebP, GIF image formats

## Third-Party Services
- **Manga Sources**: OlympusStaff and other manga websites for automated content scraping
- **Analytics**: Built-in analytics system for tracking user engagement and content performance
- **Notifications**: In-app notification system with email integration capabilities

## Development Tools
- **Database Migration**: SQLAlchemy migration support for schema updates
- **Logging**: Comprehensive logging system for debugging and monitoring
- **Configuration Management**: Environment-based configuration with development/production settings