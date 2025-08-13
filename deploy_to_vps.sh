#!/bin/bash
# VPS Deployment Script for Manga Platform

echo "🚀 Starting VPS deployment..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "❌ Please don't run this script as root"
    exit 1
fi

# Variables (customize these)
PROJECT_DIR="/var/www/manga-platform"
PYTHON_VERSION="3.11"
SERVICE_NAME="manga-platform"
DOMAIN="your-domain.com"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

echo_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

echo_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command_exists python3.11; then
    echo_error "Python 3.11 is not installed"
    exit 1
fi

if ! command_exists pip3; then
    echo_error "pip3 is not installed"
    exit 1
fi

echo_success "All prerequisites met"

# Create project directory if it doesn't exist
if [ ! -d "$PROJECT_DIR" ]; then
    echo_warning "Creating project directory at $PROJECT_DIR"
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown -R $USER:$USER "$PROJECT_DIR"
fi

# Navigate to project directory
cd "$PROJECT_DIR" || exit

# Create virtual environment
echo "🐍 Setting up Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing Python dependencies..."
if [ -f "vps_requirements.txt" ]; then
    pip install -r vps_requirements.txt
else
    echo_error "vps_requirements.txt not found!"
    exit 1
fi

echo_success "Dependencies installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file..."
    cat > .env << EOF
DATABASE_URL=postgresql://manga_user:CHANGE_PASSWORD@localhost/manga_platform
SESSION_SECRET=CHANGE_THIS_TO_A_LONG_RANDOM_STRING
FLASK_ENV=production
CLOUDINARY_CLOUD_NAME=your_cloudinary_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
EOF
    echo_warning "Please edit .env file with your actual credentials"
fi

# Initialize database
echo "🗄️ Initializing database..."
python database_init.py

# Create systemd service file
echo "🔧 Creating systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Manga Platform Web Application
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 4 --worker-class gevent --worker-connections 1000 --timeout 120 --keep-alive 2 --max-requests 1000 --max-requests-jitter 50 main:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
sudo chown -R www-data:www-data "$PROJECT_DIR"
sudo chmod -R 755 "$PROJECT_DIR"

# Reload systemd and start service
echo "🚀 Starting service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

# Check service status
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    echo_success "Service is running!"
else
    echo_error "Service failed to start. Check logs with: sudo journalctl -u $SERVICE_NAME -f"
    exit 1
fi

# Create Nginx configuration if nginx is installed
if command_exists nginx; then
    echo "🌐 Configuring Nginx..."
    sudo tee /etc/nginx/sites-available/$SERVICE_NAME > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static/ {
        alias $PROJECT_DIR/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    client_max_body_size 200M;
}
EOF

    # Enable site
    sudo ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    
    echo_success "Nginx configured"
else
    echo_warning "Nginx not found. Please install and configure manually"
fi

echo ""
echo_success "🎉 Deployment completed!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your actual credentials"
echo "2. Configure your domain DNS to point to this server"
echo "3. Install SSL certificate with: sudo certbot --nginx -d $DOMAIN"
echo "4. Monitor logs with: sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Your app should be available at: http://$DOMAIN"