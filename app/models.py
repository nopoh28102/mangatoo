from datetime import datetime
from .app import db
from flask_login import UserMixin
from sqlalchemy import func
from enum import Enum

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)  # Allow null for OAuth users
    google_id = db.Column(db.String(100), unique=True, nullable=True)  # Google OAuth ID
    oauth_provider = db.Column(db.String(50), nullable=True)  # OAuth provider (google, facebook, etc.)
    is_admin = db.Column(db.Boolean, default=False)
    is_publisher = db.Column(db.Boolean, default=False)
    is_translator = db.Column(db.Boolean, default=False)
    premium_until = db.Column(db.DateTime)  # Premium subscription expiry
    profile_picture = db.Column(db.String(200))
    avatar_url = db.Column(db.String(200))  # Avatar URL for profile
    bio = db.Column(db.Text)
    bio_ar = db.Column(db.Text)
    country = db.Column(db.String(50))
    language_preference = db.Column(db.String(10), default='en')
    notification_settings = db.Column(db.JSON, default=lambda: {'email': True, 'push': True, 'new_chapters': True, 'comments': True})
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    account_active = db.Column(db.Boolean, default=True)  # Account active status
    
    # Relationships
    bookmarks = db.relationship('Bookmark', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    ratings = db.relationship('Rating', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reading_progress = db.relationship('ReadingProgress', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    published_manga = db.relationship('Manga', backref='publisher', foreign_keys='Manga.publisher_id')
    published_chapters = db.relationship('Chapter', backref='chapter_publisher', foreign_keys='Chapter.publisher_id')
    translation_requests = db.relationship('TranslationRequest', backref='translator', foreign_keys='TranslationRequest.translator_id')
    notifications = db.relationship('Notification', backref='user', cascade='all, delete-orphan')
    subscriptions = db.relationship('Subscription', backref='user', cascade='all, delete-orphan')
    
    @property
    def is_premium(self):
        return self.premium_until and self.premium_until > datetime.utcnow()
    
    @property
    def is_active(self):
        """Override UserMixin property to use our account_active field"""
        return self.account_active

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    name_ar = db.Column(db.String(50))  # Arabic name
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)  # Arabic description
    slug = db.Column(db.String(100), unique=True)  # URL slug
    is_active = db.Column(db.Boolean, default=True)  # Active status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Manga(db.Model):
    __tablename__ = 'manga'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))  # Arabic title
    slug = db.Column(db.String(250), unique=True)  # SEO-friendly URL slug
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)  # Arabic description
    author = db.Column(db.String(100))
    artist = db.Column(db.String(100))
    cover_image = db.Column(db.String(200))
    status = db.Column(db.String(20), default='ongoing')  # ongoing, completed, hiatus
    type = db.Column(db.String(20), default='manga')  # manga, manhwa, manhua
    language = db.Column(db.String(10), default='en')
    views = db.Column(db.Integer, default=0)
    is_premium = db.Column(db.Boolean, default=False)  # Premium content
    is_featured = db.Column(db.Boolean, default=False)  # Featured manga
    is_published = db.Column(db.Boolean, default=True)  # Published status
    publication_schedule = db.Column(db.String(50))  # daily, weekly, monthly, irregular
    publisher_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    original_language = db.Column(db.String(10), default='en')
    tags = db.Column(db.JSON, default=list)  # Array of tags
    age_rating = db.Column(db.String(10), default='T')  # G, PG, T, M, A
    license_type = db.Column(db.String(20), default='exclusive')  # exclusive, non-exclusive, creative_commons
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    chapters = db.relationship('Chapter', backref='manga', lazy='dynamic', cascade='all, delete-orphan', order_by='Chapter.chapter_number.asc()')
    bookmarks = db.relationship('Bookmark', backref='manga', lazy='dynamic', cascade='all, delete-orphan')
    ratings = db.relationship('Rating', backref='manga', lazy='dynamic', cascade='all, delete-orphan')
    translation_requests = db.relationship('TranslationRequest', backref='manga', cascade='all, delete-orphan')
    analytics = db.relationship('MangaAnalytics', backref='manga', cascade='all, delete-orphan')
    reading_progress = db.relationship('ReadingProgress', cascade='all, delete-orphan')
    
    # Many-to-many relationship with categories
    categories = db.relationship('Category', secondary='manga_category', backref='manga_items')
    
    # Relationship for comments
    comments = db.relationship('Comment', backref='manga', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def average_rating(self):
        avg = db.session.query(func.avg(Rating.rating)).filter(Rating.manga_id == self.id).scalar()
        return round(avg, 1) if avg else 0.0
    
    @property
    def total_chapters(self):
        return self.chapters.count()
    
    def get_reaction_counts(self):
        """Get count of each reaction type for this manga"""
        from sqlalchemy import func
        reaction_counts = db.session.query(
            MangaReaction.reaction_type,
            func.count(MangaReaction.id)
        ).filter(MangaReaction.manga_id == self.id).group_by(MangaReaction.reaction_type).all()
        
        counts = {
            'surprised': 0,
            'angry': 0, 
            'shocked': 0,
            'love': 0,
            'laugh': 0,
            'thumbs_up': 0
        }
        
        for reaction_type, count in reaction_counts:
            counts[reaction_type] = count
            
        return counts
    
    def get_user_reaction(self, user_id):
        """Get user's reaction to this manga"""
        if not user_id:
            return None
        reaction = MangaReaction.query.filter_by(
            manga_id=self.id,
            user_id=user_id
        ).first()
        return reaction.reaction_type if reaction else None
    
    def generate_slug(self):
        """Generate SEO-friendly slug from title"""
        import re
        import unicodedata
        
        # Use title_ar if available and the site language is Arabic, otherwise use title
        base_title = self.title_ar if self.title_ar else self.title
        if not base_title:
            base_title = self.title
            
        # Normalize unicode characters
        slug = unicodedata.normalize('NFKD', base_title)
        
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-').lower()
        
        # Ensure uniqueness by checking existing slugs
        base_slug = slug
        counter = 1
        
        # Build query to exclude current manga if it has an ID (for updates)
        query = Manga.query.filter_by(slug=slug)
        if hasattr(self, 'id') and self.id:
            query = query.filter(Manga.id != self.id)
            
        while query.first():
            slug = f"{base_slug}-{counter}"
            counter += 1
            # Update query for new slug
            query = Manga.query.filter_by(slug=slug)
            if hasattr(self, 'id') and self.id:
                query = query.filter(Manga.id != self.id)
            
        return slug



# Association table for manga-category many-to-many relationship
manga_category = db.Table('manga_category',
    db.Column('manga_id', db.Integer, db.ForeignKey('manga.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

class Chapter(db.Model):
    
    __tablename__ = 'chapters'
    
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    chapter_number = db.Column(db.Float, nullable=False)
    title = db.Column(db.String(200))
    title_ar = db.Column(db.String(200))  # Arabic title
    slug = db.Column(db.String(300))  # SEO-friendly URL slug (not unique as manga_slug/chapter_slug should be unique together)
    pages = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='published')  # published, draft, scheduled
    is_premium = db.Column(db.Boolean, default=False)  # Premium chapter
    publisher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who published this chapter
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Scheduling fields
    release_date = db.Column(db.DateTime, nullable=True)  # Scheduled release date
    early_access_date = db.Column(db.DateTime, nullable=True)  # Premium early access date
    is_locked = db.Column(db.Boolean, default=False)  # Whether chapter is locked until release
    
    # Additional fields
    page_count = db.Column(db.Integer, default=0)  # Number of pages in chapter
    is_available = db.Column(db.Boolean, default=True)  # Chapter availability status
    
    # Review fields
    is_approved = db.Column(db.Boolean, default=False)  # Chapter approval status
    approved_at = db.Column(db.DateTime)  # When chapter was approved
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Admin who approved
    rejection_reason = db.Column(db.Text)  # Reason for rejection if any
    reviewed_at = db.Column(db.DateTime)  # When chapter was reviewed
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Admin who reviewed
    
    # Relationships
    page_images = db.relationship('PageImage', backref='chapter', lazy='dynamic', cascade='all, delete-orphan', order_by='PageImage.page_number.asc()')
    comments = db.relationship('Comment', backref='chapter', lazy='dynamic', cascade='all, delete-orphan')
    
    def is_available_for_user(self, user=None):
        """Check if chapter is available for a specific user"""
        if not self.is_locked:
            return True
        
        now = datetime.utcnow()
        
        # If release date has passed, chapter is available to everyone
        if self.release_date and now >= self.release_date:
            return True
        
        # If user is premium and early access date has passed
        if user and user.is_premium and self.early_access_date and now >= self.early_access_date:
            return True
        
        return False
    
    def generate_slug(self):
        """Generate SEO-friendly slug for chapter"""
        import re
        import unicodedata
        
        # Create base slug from chapter number
        chapter_slug = f"chapter-{int(self.chapter_number)}"
        
        # Add title if available
        if self.title:
            title = self.title_ar if self.title_ar else self.title
            # Normalize and clean title
            title = unicodedata.normalize('NFKD', title)
            title = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF-]', '', title)
            title = re.sub(r'[-\s]+', '-', title)
            title = title.strip('-').lower()
            if title:
                chapter_slug += f"-{title}"
        
        return chapter_slug

# SQLAlchemy event listeners for automatic slug generation (defined after all models)
from sqlalchemy import event, text

# Auto-generate slugs for new records
@event.listens_for(Manga, 'before_insert')
def manga_before_insert(mapper, connection, target):
    """Auto-generate slug before inserting manga"""
    if not target.slug and target.title:
        # Generate unique slug by checking database directly
        import re
        import unicodedata
        
        base_title = target.title_ar if target.title_ar else target.title
        slug = unicodedata.normalize('NFKD', base_title)
        slug = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-').lower()
        
        # Check for uniqueness using raw SQL to avoid flushing
        base_slug = slug
        counter = 1
        
        while True:
            # Use connection to check if slug exists
            result = connection.execute(
                text("SELECT COUNT(*) FROM manga WHERE slug = :slug"), 
                {"slug": slug}
            )
            count = result.scalar()
            
            if count == 0:
                break
                
            slug = f"{base_slug}-{counter}"
            counter += 1
            
        target.slug = slug

@event.listens_for(Manga, 'before_update')  
def manga_before_update(mapper, connection, target):
    """Auto-generate slug before updating manga if title changed"""
    if target.title and (not target.slug or hasattr(target, '_slug_needs_update')):
        target.slug = target.generate_slug()

@event.listens_for(Chapter, 'before_insert')
def chapter_before_insert(mapper, connection, target):
    """Auto-generate slug before inserting chapter"""
    if not target.slug:
        target.slug = target.generate_slug()

@event.listens_for(Chapter, 'before_update')
def chapter_before_update(mapper, connection, target):
    """Auto-generate slug before updating chapter if needed"""
    if not target.slug or (target.title and hasattr(target, '_slug_needs_update')):
        target.slug = target.generate_slug()

class PageImage(db.Model):
    
    __tablename__ = 'page_images'
    
    __tablename__ = 'page_images'
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    image_path = db.Column(db.String(300), nullable=True)  # Made nullable for Cloudinary-only images
    image_width = db.Column(db.Integer)
    image_height = db.Column(db.Integer)
    file_size = db.Column(db.Integer)  # File size in bytes
    # Cloudinary integration fields
    cloudinary_url = db.Column(db.String(500))  # Cloudinary secure URL
    cloudinary_public_id = db.Column(db.String(300))  # Cloudinary public ID
    is_cloudinary = db.Column(db.Boolean, default=False)  # Whether image is stored in Cloudinary
    
    @property
    def image_url(self):
        """Get the URL for this page image"""
        from flask import url_for
        
        # If using Cloudinary, return Cloudinary URL
        if self.is_cloudinary and self.cloudinary_url:
            return self.cloudinary_url
            
        # If local image path exists, return static URL
        if self.image_path:
            return url_for('static', filename=self.image_path)
            
        # Fallback to placeholder
        return url_for('static', filename='uploads/placeholder.jpg')

class Bookmark(db.Model):
    
    __tablename__ = 'bookmarks'
    
    __tablename__ = 'bookmarks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'manga_id'),)

class ReadingProgress(db.Model):
    
    __tablename__ = 'reading_progress'
    
    __tablename__ = 'reading_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False)
    page_number = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    manga = db.relationship('Manga', overlaps="reading_progress")
    chapter = db.relationship('Chapter')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'manga_id'),)

class Comment(db.Model):
    
    __tablename__ = 'comments'
    
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=True)
    is_edited = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True)
    
    # Relationships
    reactions = db.relationship('CommentReaction', backref='comment', lazy='dynamic', cascade='all, delete-orphan')
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    
    def get_reaction_counts(self):
        """Get count of each reaction type"""
        from sqlalchemy import func
        reaction_counts = db.session.query(
            CommentReaction.reaction_type,
            func.count(CommentReaction.id)
        ).filter(CommentReaction.comment_id == self.id).group_by(CommentReaction.reaction_type).all()
        
        counts = {
            'surprised': 0,
            'angry': 0, 
            'shocked': 0,
            'love': 0,
            'laugh': 0,
            'thumbs_up': 0
        }
        
        for reaction_type, count in reaction_counts:
            counts[reaction_type] = count
            
        return counts
    
    def get_user_reaction(self, user_id):
        """Get user's reaction to this comment"""
        if not user_id:
            return None
        reaction = CommentReaction.query.filter_by(
            comment_id=self.id,
            user_id=user_id
        ).first()
        return reaction.reaction_type if reaction else None
    
    @property
    def reports_count(self):
        """Get count of reports for this comment"""
        return Report.query.filter_by(
            content_type='comment',
            content_id=self.id
        ).count()
    
    @property
    def likes_count(self):
        """Get count of thumbs up reactions"""
        return self.reactions.filter_by(reaction_type='thumbs_up').count()
    
    @property
    def dislikes_count(self):
        """Get count of angry reactions (used as dislikes)"""
        return self.reactions.filter_by(reaction_type='angry').count()
    
    @property
    def replies_count(self):
        """Get count of replies to this comment"""
        return self.replies.count()
    
    @property
    def status(self):
        """Get comment status based on approval and reports"""
        if self.reports_count > 0:
            return 'flagged'
        elif not self.is_approved:
            return 'pending'
        else:
            return 'approved'

class CommentReaction(db.Model):
    
    __tablename__ = 'comment_reactions'
    
    __tablename__ = 'comment_reactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    reaction_type = db.Column(db.String(20), nullable=False)  # surprised, angry, shocked, love, laugh, thumbs_up
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='comment_reactions')
    
    # Unique constraint to prevent multiple reactions from same user on same comment
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='unique_user_comment_reaction'),)

class MangaReaction(db.Model):
    
    __tablename__ = 'manga_reactions'
    
    __tablename__ = 'manga_reactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    reaction_type = db.Column(db.String(20), nullable=False)  # surprised, angry, shocked, love, laugh, thumbs_up
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='manga_reactions')
    manga = db.relationship('Manga', backref='manga_reactions')
    
    # Unique constraint to prevent multiple reactions from same user on same manga
    __table_args__ = (db.UniqueConstraint('user_id', 'manga_id', name='unique_user_manga_reaction'),)

class Rating(db.Model):
    
    __tablename__ = 'ratings'
    
    __tablename__ = 'ratings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    review = db.Column(db.Text)  # Optional detailed review
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'manga_id'),)

# New models for enhanced functionality
class PublisherRequest(db.Model):
    __tablename__ = 'publisher_requests'
    """Requests to become a publisher"""
    __tablename__ = 'publisher_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    portfolio_url = db.Column(db.String(500))
    description = db.Column(db.Text, nullable=False)
    sample_work = db.Column(db.String(500))  # Path to uploaded sample
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref='publisher_requests')

class TranslationRequest(db.Model):
    __tablename__ = 'translation_requests'
    """Translation requests and assignments"""
    __tablename__ = 'translation_requests'
    id = db.Column(db.Integer, primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'))
    from_language = db.Column(db.String(10), nullable=False)
    to_language = db.Column(db.String(10), nullable=False)
    translator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(20), default='open')  # open, assigned, in_progress, completed, published
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, urgent
    deadline = db.Column(db.DateTime)
    reward = db.Column(db.Float, default=0.0)  # Payment/points for translation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    chapter = db.relationship('Chapter', backref='translation_requests')

class Notification(db.Model):
    __tablename__ = 'notifications'
    """User notifications system"""
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # new_chapter, comment, rating, translation_request, etc.
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    link = db.Column(db.String(500))  # Link to relevant content
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Announcement(db.Model):
    __tablename__ = 'announcements'
    """Site-wide announcements system"""
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))  # Arabic title
    content = db.Column(db.Text, nullable=False)
    content_ar = db.Column(db.Text)  # Arabic content
    type = db.Column(db.String(50), default='info')  # info, warning, success, error
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)  # Show prominently
    target_audience = db.Column(db.String(50), default='all')  # all, premium, publishers, translators
    display_until = db.Column(db.DateTime)  # Auto-hide after this date
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    creator = db.relationship('User', backref='announcements')

class Advertisement(db.Model):
    __tablename__ = 'advertisements'
    """Advertisement system for free users in manga reader"""
    __tablename__ = 'advertisements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    ad_type = db.Column(db.String(20), nullable=False)  # banner, image, text, video, code
    placement = db.Column(db.String(50), nullable=False)  # reader_top, reader_bottom, reader_side, between_pages, chapter_end
    content = db.Column(db.Text)  # HTML content for the ad
    image_url = db.Column(db.String(500))
    target_url = db.Column(db.String(500))
    open_new_tab = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=1)  # 1-10, higher number = higher priority
    impressions = db.Column(db.Integer, default=0)  # Total views
    clicks = db.Column(db.Integer, default=0)  # Total clicks
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    creator = db.relationship('User', backref='advertisements')
    
    @property
    def is_expired(self):
        if self.end_date:
            return datetime.utcnow() > self.end_date
        return False
    
    @property
    def is_scheduled(self):
        if self.start_date:
            return datetime.utcnow() < self.start_date
        return False
    
    @property
    def should_display(self):
        if not self.is_active:
            return False
        if self.is_expired:
            return False
        if self.is_scheduled:
            return False
        return True
    
class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    """User subscriptions to manga for notifications"""
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    notify_new_chapters = db.Column(db.Boolean, default=True)
    notify_comments = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    manga = db.relationship('Manga', backref='subscribers')
    __table_args__ = (db.UniqueConstraint('user_id', 'manga_id'),)

class MangaAnalytics(db.Model):
    __tablename__ = 'manga_analytics'
    """Analytics data for manga"""
    __tablename__ = 'manga_analytics'
    id = db.Column(db.Integer, primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    unique_visitors = db.Column(db.Integer, default=0)
    reading_time = db.Column(db.Integer, default=0)  # Total reading time in minutes
    bookmarks_added = db.Column(db.Integer, default=0)
    ratings_added = db.Column(db.Integer, default=0)
    comments_added = db.Column(db.Integer, default=0)
    
    __table_args__ = (db.UniqueConstraint('manga_id', 'date'),)

class Translation(db.Model):
    
    __tablename__ = 'translations'
    
    """Store translations for text content"""
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(50), nullable=False)  # manga_title, manga_description, chapter_title, etc.
    content_id = db.Column(db.Integer, nullable=False)  # ID of the content being translated
    language = db.Column(db.String(10), nullable=False)
    original_text = db.Column(db.Text)
    translated_text = db.Column(db.Text, nullable=False)
    translator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(20), default='draft')  # draft, published, needs_review
    quality_score = db.Column(db.Float, default=0.0)  # Community rating of translation quality
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    translator = db.relationship('User', backref='translations')
    __table_args__ = (db.UniqueConstraint('content_type', 'content_id', 'language'),)

class Report(db.Model):
    
    __tablename__ = 'reports'
    
    """Content reporting system"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content_type = db.Column(db.String(50), nullable=False)  # manga, chapter, comment
    content_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(100), nullable=False)  # inappropriate, copyright, spam, etc.
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='open')  # open, investigating, resolved, dismissed
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    reporter = db.relationship('User', backref='reports')

class PaymentPlan(db.Model):
    
    __tablename__ = 'payment_plans'
    
    """Premium subscription plans"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))  # Arabic name
    price = db.Column(db.Float, nullable=False)
    duration_months = db.Column(db.Integer, nullable=False)
    features = db.Column(db.JSON, default=list)  # List of features included
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PaymentGateway(db.Model):
    
    __tablename__ = 'payment_gateways'
    
    """Payment gateway configurations"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # PayPal, Stripe, PayTabs, etc.
    display_name = db.Column(db.String(100), nullable=False)
    display_name_ar = db.Column(db.String(100))  # Arabic display name
    gateway_type = db.Column(db.String(50), nullable=False)  # paypal, stripe, paytabs, fawry, bank_transfer, apple_pay, google_pay, razorpay, paymob, visa_direct, mastercard, etc.
    is_active = db.Column(db.Boolean, default=True)
    is_sandbox = db.Column(db.Boolean, default=True)
    
    # Configuration settings (stored as JSON)
    config_data = db.Column(db.JSON, default=dict)
    
    # Display and processing settings
    logo_url = db.Column(db.String(500))
    icon_class = db.Column(db.String(100))  # Font Awesome or other icon classes
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)
    supported_currencies = db.Column(db.JSON, default=list)
    processing_fee = db.Column(db.Float, default=0.0)  # Processing fee percentage
    min_amount = db.Column(db.Float, default=1.0)  # Minimum transaction amount
    max_amount = db.Column(db.Float, default=10000.0)  # Maximum transaction amount
    display_order = db.Column(db.Integer, default=0)  # Order on payment page
    
    # Regional and feature settings
    supported_countries = db.Column(db.JSON, default=list)  # ISO country codes
    requires_verification = db.Column(db.Boolean, default=False)  # Requires user verification
    supports_recurring = db.Column(db.Boolean, default=False)  # Supports subscription billing
    processing_time = db.Column(db.String(100))  # e.g., "Instant", "1-3 business days"
    processing_time_ar = db.Column(db.String(100))  # Arabic processing time
    
    # Default gateway setting
    is_default = db.Column(db.Boolean, default=False)  # Default payment gateway
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Payment(db.Model):
    
    __tablename__ = 'payments'
    
    """Payment records"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('payment_plans.id'), nullable=False)
    gateway_id = db.Column(db.Integer, db.ForeignKey('payment_gateways.id'), nullable=False)
    
    # Payment details
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed, cancelled, refunded
    
    # Gateway specific IDs
    gateway_payment_id = db.Column(db.String(255))  # Payment ID from the gateway
    gateway_transaction_id = db.Column(db.String(255))  # Transaction ID from the gateway
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    refunded_at = db.Column(db.DateTime)
    
    # Refund information
    refund_reason = db.Column(db.Text)
    gateway_response = db.Column(db.Text)  # Store gateway response JSON
    
    # Relationships
    user = db.relationship('User', backref='payments')
    plan = db.relationship('PaymentPlan', backref='payments')
    gateway = db.relationship('PaymentGateway', backref='payments')

class SiteSetting(db.Model):
    
    __tablename__ = 'site_settings'
    
    """Site-wide settings and configurations"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    data_type = db.Column(db.String(20), default='string')  # string, integer, float, boolean, json
    category = db.Column(db.String(50), default='general')  # general, appearance, reading, content, advanced
    description = db.Column(db.String(500))
    description_ar = db.Column(db.String(500))
    is_public = db.Column(db.Boolean, default=False)  # Whether setting is visible to non-admins
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def parsed_value(self):
        """Parse value based on data_type"""
        if not self.value:
            return None
        
        if self.data_type == 'boolean':
            return self.value.lower() in ['true', '1', 'yes', 'on']
        elif self.data_type == 'integer':
            try:
                return int(self.value)
            except (ValueError, TypeError):
                return 0
        elif self.data_type == 'float':
            try:
                return float(self.value)
            except (ValueError, TypeError):
                return 0.0
        elif self.data_type == 'json':
            try:
                import json
                return json.loads(self.value)
            except (ValueError, TypeError):
                return {}
        else:
            return self.value

class UserSubscription(db.Model):
    
    __tablename__ = 'user_subscriptions'
    
    """User subscription records"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('payment_plans.id'), nullable=False)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=False)
    
    # Subscription details
    status = db.Column(db.String(20), default='active')  # active, expired, cancelled, suspended
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=False)
    auto_renew = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='user_subscriptions')
    plan = db.relationship('PaymentPlan', backref='plan_subscriptions')
    payment = db.relationship('Payment', backref='subscription')

# Auto-scraping models
class AutoScrapingSource(db.Model):
    
    __tablename__ = 'auto_scraping_sources'
    
    """Sources for automatic chapter scraping"""
    id = db.Column(db.Integer, primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    website_type = db.Column(db.String(50), nullable=False)  # mangadx, manganelo, mangakakalot, generic
    source_url = db.Column(db.String(500), nullable=False)  # Base URL for the manga on source site
    last_chapter_scraped = db.Column(db.Float, default=0.0)  # Last chapter number scraped
    last_check = db.Column(db.DateTime)
    check_interval = db.Column(db.Integer, default=3600)  # Check interval in seconds (default 1 hour)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional settings
    auto_publish = db.Column(db.Boolean, default=False)  # Automatically publish scraped chapters
    quality_check = db.Column(db.Boolean, default=True)  # Enable quality checks before publishing
    notification_enabled = db.Column(db.Boolean, default=True)  # Send notifications when new chapters found
    
    manga = db.relationship('Manga', backref='scraping_sources')

class ScrapingLog(db.Model):
    
    __tablename__ = 'scraping_logs'
    
    """Log of scraping activities"""
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('auto_scraping_sources.id'), nullable=False)
    check_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False)  # success, failed, no_new_chapters
    chapters_found = db.Column(db.Integer, default=0)
    chapters_scraped = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    execution_time = db.Column(db.Float)  # Time taken in seconds
    
    source = db.relationship('AutoScrapingSource', backref='scraping_logs')

class ScrapingQueue(db.Model):
    
    __tablename__ = 'scraping_queue'
    
    """Queue for chapters to be scraped"""
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('auto_scraping_sources.id'), nullable=False)
    chapter_number = db.Column(db.Float, nullable=False)
    chapter_url = db.Column(db.String(500), nullable=False)
    chapter_title = db.Column(db.String(200))
    priority = db.Column(db.Integer, default=0)  # Higher number = higher priority
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    
    source = db.relationship('AutoScrapingSource', backref='scraping_queue')

class ScrapingSettings(db.Model):
    
    __tablename__ = 'scraping_settings'
    
    """Global scraping settings"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class StaticPage(db.Model):
    
    __tablename__ = 'static_pages'
    
    """Static pages for the website"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))  # Arabic title
    slug = db.Column(db.String(100), unique=True, nullable=False)  # Custom URL
    content = db.Column(db.Text, nullable=False)
    content_ar = db.Column(db.Text)  # Arabic content
    meta_description = db.Column(db.String(500))  # SEO meta description
    meta_description_ar = db.Column(db.String(500))  # Arabic SEO meta description
    meta_keywords = db.Column(db.String(300))  # SEO keywords
    is_published = db.Column(db.Boolean, default=False)
    show_in_menu = db.Column(db.Boolean, default=False)  # Show in navigation menu
    menu_order = db.Column(db.Integer, default=0)  # Menu display order
    template_name = db.Column(db.String(100), default='static_page.html')  # Template to use
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    created_by = db.relationship('User', backref='created_pages')

class BlogPost(db.Model):
    
    __tablename__ = 'blog_posts'
    
    """Blog posts for the website"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))  # Arabic title
    slug = db.Column(db.String(100), unique=True, nullable=False)  # Custom URL
    excerpt = db.Column(db.Text)  # Short description/excerpt
    excerpt_ar = db.Column(db.Text)  # Arabic excerpt
    content = db.Column(db.Text, nullable=False)
    content_ar = db.Column(db.Text)  # Arabic content
    featured_image = db.Column(db.String(200))  # Featured image URL
    meta_description = db.Column(db.String(500))  # SEO meta description
    meta_description_ar = db.Column(db.String(500))  # Arabic SEO meta description
    meta_keywords = db.Column(db.String(300))  # SEO keywords
    tags = db.Column(db.String(500))  # Comma-separated tags
    tags_ar = db.Column(db.String(500))  # Arabic tags
    is_published = db.Column(db.Boolean, default=False)
    is_featured = db.Column(db.Boolean, default=False)  # Featured post
    views = db.Column(db.Integer, default=0)  # View count
    reading_time = db.Column(db.Integer, default=0)  # Estimated reading time in minutes
    category = db.Column(db.String(50))  # Blog category
    category_ar = db.Column(db.String(50))  # Arabic category
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)  # When the post was published
    
    # Relationship
    author = db.relationship('User', backref='blog_posts')
    
    def get_reading_time(self):
        """Calculate estimated reading time based on content length"""
        if not self.content:
            return 0
        word_count = len(self.content.split())
        return max(1, round(word_count / 200))  # Average reading speed: 200 words per minute
    
    def get_tags_list(self):
        """Get tags as a list"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []
    
    def get_tags_ar_list(self):
        """Get Arabic tags as a list"""
        if self.tags_ar:
            return [tag.strip() for tag in self.tags_ar.split(',') if tag.strip()]
        return []




class CloudinaryAccount(db.Model):
    """Cloudinary account model for managing multiple accounts"""
    __tablename__ = 'cloudinary_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cloud_name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(100), nullable=False)
    api_secret = db.Column(db.String(100), nullable=False)
    
    # Storage limits and usage
    storage_limit_mb = db.Column(db.Float, default=25600.0)  # 25GB default for free plan
    storage_used_mb = db.Column(db.Float, default=0.0)
    
    # Account settings
    is_primary = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    priority_order = db.Column(db.Integer, default=1)
    plan_type = db.Column(db.String(50), default='free')  # free, plus, advanced, etc.
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    
    # Additional fields
    notes = db.Column(db.Text)  # Admin notes for this account
    
    @property
    def storage_usage_percentage(self):
        """Calculate storage usage percentage"""
        if self.storage_limit_mb <= 0:
            return 0
        return (self.storage_used_mb / self.storage_limit_mb) * 100
    
    @property
    def is_near_storage_limit(self):
        """Check if account is near storage limit (>90%)"""
        return self.storage_usage_percentage > 90
    
    @property
    def is_storage_full(self):
        """Check if account storage is full (>95%)"""
        return self.storage_usage_percentage > 95
    
    @property
    def is_usable(self):
        """Check if account can be used for uploads"""
        return self.is_active and not self.is_storage_full
    
    def mark_as_used(self):
        """Mark account as recently used"""
        self.last_used_at = datetime.utcnow()
        db.session.commit()
    
    def update_usage_stats(self, used_mb):
        """Update storage usage statistics"""
        self.storage_used_mb = used_mb
        self.last_used_at = datetime.utcnow()
        db.session.commit()


class CloudinaryUsageLog(db.Model):
    """Log of Cloudinary usage for monitoring and analytics"""
    __tablename__ = 'cloudinary_usage_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('cloudinary_accounts.id'), nullable=False)
    
    # Usage data
    operation_type = db.Column(db.String(50), nullable=False)  # upload, delete, transform
    resource_count = db.Column(db.Integer, default=1)  # Number of resources affected
    data_size_mb = db.Column(db.Float, default=0.0)  # Size of data processed
    
    # Context information
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'))
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    
    # Relationships
    account = db.relationship('CloudinaryAccount', backref='usage_logs')
    manga = db.relationship('Manga', backref='cloudinary_logs')
    chapter = db.relationship('Chapter', backref='cloudinary_logs')

class NewsletterSubscription(db.Model):
    """Newsletter email subscription model"""
    __tablename__ = 'newsletter_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Optional link to user account
    is_active = db.Column(db.Boolean, default=True)
    preferences = db.Column(db.JSON, default=lambda: {
        'new_chapters': True,
        'new_manga': True,
        'announcements': True,
        'weekly_digest': True
    })
    language_preference = db.Column(db.String(10), default='ar')
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_email_sent = db.Column(db.DateTime)
    unsubscribe_token = db.Column(db.String(64), unique=True, nullable=False)
    
    # Relationship
    user = db.relationship('User', backref='newsletter_subscription')
    
    def __init__(self, **kwargs):
        super(NewsletterSubscription, self).__init__(**kwargs)
        if not self.unsubscribe_token:
            import secrets
            self.unsubscribe_token = secrets.token_urlsafe(32)
    
    def __repr__(self):
        return f'<NewsletterSubscription {self.email}>'
