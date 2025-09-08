# Google OAuth Authentication Module
import json
import os
import requests
import logging
from flask import Blueprint, redirect, request, url_for, flash, jsonify
from urllib.parse import urlparse
from flask_login import login_user, logout_user, current_user, login_required
from oauthlib.oauth2 import WebApplicationClient

# Try to get settings manager (lazy initialization)
def get_settings_manager():
    """Get settings manager with lazy initialization"""
    try:
        from .utils_settings import SettingsManager
        return SettingsManager
    except ImportError:
        try:
            from app.utils_settings import SettingsManager
            return SettingsManager
        except ImportError:
            # Fallback if settings manager fails
            class FallbackSettings:
                @staticmethod
                def get(key, default=None):
                    return os.environ.get(key, default)
            return FallbackSettings()

# Google OAuth Discovery URL
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Create Blueprint
google_auth = Blueprint("google_auth", __name__)

class GoogleOAuth:
    def __init__(self):
        self.client_id = None
        self.client_secret = None
        self.client = None
        self.is_enabled = False
        self._initialize()
    
    def _initialize(self):
        """Initialize Google OAuth configuration"""
        try:
            # Get settings manager instance
            settings_manager = get_settings_manager()
            
            # Get settings from environment variables or settings manager
            self.client_id = (settings_manager.get('google_oauth_client_id') or 
                            os.environ.get('GOOGLE_OAUTH_CLIENT_ID'))
            
            self.client_secret = (settings_manager.get('google_oauth_client_secret') or 
                                os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET'))
            
            # Check if OAuth is enabled
            oauth_enabled = settings_manager.get('google_oauth_enabled', 'false')
            # Handle both string and boolean values
            if isinstance(oauth_enabled, bool):
                oauth_enabled_str = 'true' if oauth_enabled else 'false'
            else:
                oauth_enabled_str = str(oauth_enabled).lower()
            
            self.is_enabled = oauth_enabled_str == 'true' and self.client_id and self.client_secret
            
            if self.is_enabled:
                self.client = WebApplicationClient(self.client_id)
                logging.info("🔑 Google OAuth initialized successfully")
            else:
                logging.warning("⚠️ Google OAuth not configured or disabled")
                
        except Exception as e:
            logging.error(f"❌ Error initializing Google OAuth: {e}")
            self.is_enabled = False
    
    def get_redirect_uri(self, request):
        """Get the redirect URI for current request"""
        if hasattr(request, 'url_root'):
            return request.url_root.rstrip('/') + '/auth/google/callback'
        # Get domain from environment or use localhost for development
        domain = os.environ.get('REPLIT_DEV_DOMAIN') or os.environ.get('REPLIT_URL', 'http://localhost:5000')
        if not domain.startswith('http'):
            domain = 'https://' + domain
        return domain.rstrip('/') + '/auth/google/callback'
    
    def is_configured(self):
        """Check if Google OAuth is properly configured"""
        return self.is_enabled
    
    def get_authorization_url(self, request):
        """Get Google authorization URL"""
        if not self.is_configured() or self.client is None:
            return None
        
        try:
            # Get Google's authorization endpoint
            google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
            authorization_endpoint = google_provider_cfg["authorization_endpoint"]
            
            # Get redirect URI
            redirect_uri = self.get_redirect_uri(request)
            
            # Build authorization URL
            request_uri = self.client.prepare_request_uri(
                authorization_endpoint,
                redirect_uri=redirect_uri,
                scope=["openid", "email", "profile"],
            )
            return request_uri
            
        except Exception as e:
            logging.error(f"❌ Error getting authorization URL: {e}")
            return None
    
    def handle_callback(self, request):
        """Handle OAuth callback and get user info"""
        if not self.is_configured() or self.client is None:
            return None, "Google OAuth not configured"
        
        try:
            # Get authorization code from callback
            code = request.args.get("code")
            if not code:
                return None, "No authorization code received"
            
            # Ensure client credentials are available
            if not self.client_id or not self.client_secret:
                return None, "OAuth credentials not available"
            
            # Get Google's token endpoint
            google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
            token_endpoint = google_provider_cfg["token_endpoint"]
            
            # Get redirect URI
            redirect_uri = self.get_redirect_uri(request)
            
            # Exchange code for tokens
            token_url, headers, body = self.client.prepare_token_request(
                token_endpoint,
                authorization_response=request.url,
                redirect_url=redirect_uri,
                code=code,
            )
            
            token_response = requests.post(
                token_url,
                headers=headers,
                data=body,
                auth=(self.client_id, self.client_secret),
            )
            
            # Parse tokens
            self.client.parse_request_body_response(json.dumps(token_response.json()))
            
            # Get user info
            userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
            uri, headers, body = self.client.add_token(userinfo_endpoint)
            userinfo_response = requests.get(uri, headers=headers, data=body)
            
            userinfo = userinfo_response.json()
            
            # Validate email verification
            if not userinfo.get("email_verified"):
                return None, "Email not verified by Google"
            
            return userinfo, None
            
        except Exception as e:
            logging.error(f"❌ Error in OAuth callback: {e}")
            return None, f"OAuth authentication failed: {str(e)}"

# Global OAuth instance (lazy initialization)
google_oauth = None

def get_google_oauth():
    """Get Google OAuth instance with lazy initialization"""
    global google_oauth
    if google_oauth is None:
        google_oauth = GoogleOAuth()
    return google_oauth

@google_auth.route("/auth/google/login")
def google_login():
    """Initiate Google OAuth login"""
    oauth_instance = get_google_oauth()
    if not oauth_instance.is_configured():
        flash('Google authentication is not configured', 'error')
        return redirect(url_for('login'))
    
    authorization_url = oauth_instance.get_authorization_url(request)
    if not authorization_url:
        flash('Failed to initialize Google authentication', 'error')
        return redirect(url_for('login'))
    
    return redirect(authorization_url)

@google_auth.route("/auth/google/callback")
def google_callback():
    """Handle Google OAuth callback"""
    oauth_instance = get_google_oauth()
    if not oauth_instance.is_configured():
        flash('Google authentication is not configured', 'error')
        return redirect(url_for('login'))
    
    # Get user info from Google
    userinfo, error = oauth_instance.handle_callback(request)
    if error:
        flash(f'Google authentication failed: {error}', 'error')
        return redirect(url_for('login'))
    
    # Import here to avoid circular imports
    try:
        from app.models import User
        from app import db
    except ImportError:
        flash('System error: Unable to access user database', 'error')
        return redirect(url_for('login'))
    
    try:
        google_id = userinfo.get("sub") if userinfo else None  # Google user ID
        email = userinfo.get("email") if userinfo else None
        name = userinfo.get("given_name", "") if userinfo else ""
        full_name = userinfo.get("name", "") if userinfo else ""
        picture = userinfo.get("picture", "") if userinfo else ""
        
        if not google_id or not email:
            return None, "Invalid user information from Google"
        
        # Check if user exists by Google ID
        user = User.query.filter_by(google_id=google_id).first()
        
        if not user:
            # Check if user exists by email
            user = User.query.filter_by(email=email).first()
            
            if user:
                # Link existing account with Google
                user.google_id = google_id
                user.oauth_provider = 'google'
                if picture:
                    user.avatar_url = picture
            else:
                # Create new user
                settings_manager = get_settings_manager()
                auto_register_setting = settings_manager.get('google_oauth_auto_register', 'true')
                auto_register = str(auto_register_setting).lower() == 'true'
                
                if not auto_register:
                    flash('New user registration via Google is disabled', 'error')
                    return redirect(url_for('register'))
                
                # Generate unique username from email or name
                username = email.split('@')[0]
                counter = 1
                original_username = username
                while User.query.filter_by(username=username).first():
                    username = f"{original_username}{counter}"
                    counter += 1
                
                user = User()
                user.username = username
                user.email = email
                user.google_id = google_id
                user.oauth_provider = 'google'
                user.avatar_url = picture or '/static/img/default-avatar.svg'
                user.language_preference = get_settings_manager().get('google_oauth_default_language', 'en')
        
        # Save to database
        db.session.add(user)
        db.session.commit()
        
        # Log in user
        login_user(user, remember=True)
        
        flash('Successfully signed in with Google!', 'success')
        next_page = request.args.get('next')
        
        # Validate next_page to prevent open redirect attacks
        if next_page:
            parsed_url = urlparse(next_page)
            # Only allow relative URLs or URLs with the same netloc as current request
            if parsed_url.netloc and parsed_url.netloc != request.host:
                next_page = None
        
        return redirect(next_page) if next_page else redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"❌ Error processing Google OAuth user: {e}")
        flash('Authentication successful, but failed to create user account', 'error')
        return redirect(url_for('login'))

@google_auth.route("/auth/google/disconnect", methods=['POST'])
@login_required
def google_disconnect():
    """Disconnect Google account from current user"""
    try:
        if current_user.oauth_provider == 'google' and not current_user.password_hash:
            return jsonify({'success': False, 'message': 'Cannot disconnect Google account without setting a password first'})
        
        current_user.google_id = None
        current_user.oauth_provider = None
        
        from app import db
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Google account disconnected successfully'})
        
    except Exception as e:
        logging.error(f"❌ Error disconnecting Google account: {e}")
        return jsonify({'success': False, 'message': 'Failed to disconnect Google account'})

def is_google_oauth_enabled():
    """Check if Google OAuth is enabled and configured"""
    return get_google_oauth().is_configured()

# Display setup instructions
def print_setup_instructions():
    """Print Google OAuth setup instructions"""
    redirect_url = f'https://{os.environ.get("REPLIT_DEV_DOMAIN", "your-domain.com")}/auth/google/callback'
    
    setup_message = f"""
🔑 Google OAuth Setup Instructions:

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a new OAuth 2.0 Client ID
3. Add the following to Authorized redirect URIs:
   {redirect_url}
4. Copy your Client ID and Client Secret to the admin settings

For detailed instructions, see:
https://docs.replit.com/additional-resources/google-auth-in-flask#set-up-your-oauth-app--client

Current Status: {'✅ Configured' if get_google_oauth().is_configured() else '❌ Not Configured'}
"""
    
    print(setup_message)
    logging.info(setup_message)

# Print setup instructions on module load (deferred)
def initialize_oauth_setup():
    """Initialize OAuth setup instructions"""
    try:
        print_setup_instructions()
    except Exception as e:
        logging.warning(f"Could not print OAuth setup instructions: {e}")

# Call setup instructions in a safe context
if __name__ != "__main__":
    # Defer printing until Flask app context is available
    pass