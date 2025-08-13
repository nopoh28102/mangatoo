# Overview

This project is a multi-language (Arabic/English) manga reading platform built with Flask. Its main purpose is to provide a comprehensive system for users to read manga, manhwa, and manhua, featuring a complete content management system, user authentication, publisher tools, premium subscriptions, automated content scraping, and an admin dashboard. The platform is designed for large-scale manga distribution, offering advanced reading features, social interactions, and monetization options. The business vision aims to capture a significant share in the online manga reading market by offering a superior user experience and robust content management capabilities.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: Flask with SQLAlchemy ORM.
- **Database**: Designed for PostgreSQL in production, SQLite for development.
- **Authentication**: Flask-Login with role-based access control (admin, publisher, translator, premium users).
- **File Storage**: Local filesystem with optimized image handling, integrated with Cloudinary for cloud storage.
- **Content Management**: Comprehensive manga/chapter upload system supporting ZIP archives and individual image files, with a revolutionary background upload system to handle large files and eliminate timeouts.

## Frontend Architecture
- **Template Engine**: Jinja2 with multi-language support.
- **Styling**: Bootstrap 5 with custom CSS, implementing a unified dark theme. UI/UX emphasizes vibrant, saturated gradients, subtle sparkle effects, and dynamic golden crystal halos.
- **JavaScript**: Modular approach with separate managers for Theme, Language, Reader, and Admin functionalities.
- **Reading Interface**: Advanced reader with multiple viewing modes (vertical, horizontal, webtoon), zoom controls, and touch gesture support.

## Data Architecture
- **Schema**: Complex relational database schema with over 25 models, including Manga, Chapter, PageImage, User Accounts (with roles, subscriptions, reading progress, bookmarks), Social Features (comments, ratings, reactions, notifications), and Commerce (payment plans, gateways, subscriptions).

## Content Scraping System
- **Automated Scraping**: Scheduled scraping from external manga sites with background processing and automatic image optimization.

## SEO and Performance
- **SEO Optimization**: Comprehensive SEO management via an admin interface controlling meta tags, Open Graph, Twitter Cards, Schema.org Markup, dynamic sitemap.xml, custom robots.txt, Google Analytics/GTM integration, custom HTML, `hreflang` for multi-language content, and `Canonical URLs`.
- **Favicon Management**: Dynamic favicon upload and management system supporting ICO, PNG, JPG, SVG with automatic resizing.
- **Image Optimization**: Automatic image compression and format conversion via Cloudinary.
- **Caching Strategy**: Settings management with a caching layer.
- **Dynamic URLs**: Automated domain detection and dynamic URL generation for both backend and frontend.

## Security and Permissions
- **Role-Based Access**: Admin, publisher, translator, and premium user roles.
- **Content Moderation**: Comment approval system and content reporting.
- **File Upload Security**: Secure filename handling and file type validation.
- **CSRF Protection**: Built-in Flask security features.
- **XML Security**: Secure XML imports for sitemap generation.

# Deployment Compatibility

## Production Environment Adaptations
- **Read-Only File Systems**: The application now handles deployment environments with read-only file systems (like leapcell.io) by gracefully skipping directory creation attempts and logging appropriate messages.
- **Error Handling**: Improved error handling for OSError 30 (Read-only file system) to ensure successful deployment on various cloud platforms.
- **Background Uploader**: Modified to use temporary directories or in-memory storage when running on read-only file systems.
- **Update System**: Enhanced to skip static file operations when filesystem is read-only.
- **Deployment Files**: Added Procfile and runtime.txt for better compatibility with various hosting platforms.
- **Platform Detection**: Created deployment_config.py to automatically detect and configure for different hosting environments (Railway, Heroku, Vercel, generic read-only systems).

# External Dependencies

## Core Python Libraries
- **Flask Ecosystem**: Flask, Flask-SQLAlchemy, Flask-Login.
- **Image Processing**: Pillow (PIL).
- **Web Scraping**: BeautifulSoup4, requests.
- **Database**: SQLAlchemy.
- **XML Security**: defusedxml.

## Frontend Libraries
- **Bootstrap 5**: UI framework.
- **Font Awesome**: Icon library.
- **Custom JavaScript**: For reader functionality and UI interactions.

## Payment Integration
- **Multi-Gateway Support**: Stripe, PayPal, and regional payment processors.
- **Currency Conversion**: Real-time exchange rate support.
- **Subscription Management**: Recurring payment handling and premium feature gating.

## Content Delivery
- **Image Storage**: Cloudinary cloud storage with global CDN distribution and automatic account switching for seamless storage management.
- **Archive Support**: ZIP/CBZ file processing with background upload system using stream-unzip library for memory efficiency.
- **Format Support**: JPEG, PNG, WebP, GIF with automatic optimization.

## Third-Party Services
- **Manga Sources**: OlympusStaff and other manga websites for automated content scraping.
- **Analytics**: Google Analytics, Google Tag Manager.