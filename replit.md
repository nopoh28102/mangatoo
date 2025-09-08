# Manga Platform

## Overview

This is a comprehensive manga reading platform built with Flask, designed for Arabic-speaking users. The platform allows users to read manga online with features including user authentication, chapter management, image hosting via Cloudinary, content scraping, payment processing, and admin controls. The application supports multiple upload methods (direct images, ZIP files, web scraping) and includes advanced features like SEO optimization and email notifications.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask with SQLAlchemy ORM for database operations
- **Database**: Dynamic configuration supporting both SQLite (development) and PostgreSQL (production) with automatic switching based on environment
- **Application Structure**: Modular design with separate modules for different functionalities (models, utilities, middleware)
- **Server**: Gunicorn WSGI server with optimized configuration for file uploads and long-running operations

### Frontend Architecture  
- **Templates**: Server-side rendered HTML templates with Arabic RTL support
- **Static Assets**: JavaScript and CSS for interactive features like manga reader, file uploads, and progress tracking
- **User Interface**: Responsive design with Arabic language support and manga-specific reading interfaces

### Image Storage and Management
- **Primary Storage**: Cloudinary integration with multi-account support and automatic load balancing
- **Local Storage**: Temporary file storage for processing before cloud upload
- **Background Processing**: Asynchronous image upload system to handle large file operations without blocking user requests
- **Image Optimization**: Automatic image compression and format conversion for web optimization

### Content Management
- **Upload Methods**: Three distinct upload approaches - direct image files, ZIP/CBZ archives, and web scraping from external manga sites
- **Scraping System**: Automated content extraction from manga websites with smart URL detection and image downloading
- **Chapter Processing**: Automatic page ordering, metadata extraction, and database storage

### Authentication and Authorization
- **User Management**: Multi-role system supporting regular users, publishers, translators, and administrators
- **OAuth Integration**: Google OAuth support with fallback to traditional username/password authentication
- **Session Management**: Flask-Login integration with secure session handling
- **Permission System**: Role-based access control for different platform features

### Payment and Licensing
- **Payment Processing**: Multi-gateway support including Stripe and PayPal with currency conversion
- **Premium Features**: Subscription-based premium content access with expiration tracking

### Communication and Notifications
- **Email System**: Bravo Mail API integration for transactional emails and notifications
- **Notification System**: In-app notification system for user updates and admin alerts
- **SEO Optimization**: Dynamic meta tag generation, sitemap creation, and search engine optimization

### Security and Rate Limiting
- **API Security**: Rate limiting, request validation, and CSRF protection
- **File Upload Security**: File type validation, size limits, and malware prevention

## External Dependencies

### Cloud Services
- **Cloudinary**: Primary image hosting and CDN service with automatic optimization and transformations
- **Bravo Mail API**: Email delivery service for notifications and user communications

### Payment Gateways
- **Stripe**: Credit card processing and subscription management
- **PayPal**: Alternative payment processing with REST SDK integration

### Authentication Providers
- **Google OAuth**: Social login integration using OAuth 2.0

### Content Sources
- **Manga Scrapers**: Automated content extraction from external manga websites including OlympusStaff and other platforms

### Development and Deployment
- **Replit**: Primary deployment platform with automatic environment detection
- **Gunicorn**: Production WSGI server with optimized configuration for large file handling
- **SQLite/PostgreSQL**: Database flexibility with automatic environment-based selection

### Monitoring and Licensing  
- **Logging**: Comprehensive error tracking and performance monitoring

### Python Libraries
- **Core Framework**: Flask, SQLAlchemy, Flask-Login for web application foundation
- **Image Processing**: Pillow for image manipulation and optimization
- **Web Scraping**: BeautifulSoup, requests, selenium for content extraction
- **File Processing**: Stream-unzip for efficient archive handling
- **Security**: Various libraries for rate limiting, input validation, and secure file handling