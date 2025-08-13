# دليل رفع المشروع على VPS Server

## المتطلبات الأساسية

### 1. متطلبات الخادم
- Ubuntu 20.04+ أو CentOS 8+
- Python 3.11+
- PostgreSQL 13+ (أو SQLite للاختبار)
- Nginx (للإنتاج)
- SSL Certificate (Let's Encrypt مجاني)

## خطوات التثبيت

### 1. إعداد الخادم الأساسي
```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت Python و pip
sudo apt install python3.11 python3.11-venv python3-pip -y

# تثبيت PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# تثبيت Nginx
sudo apt install nginx -y

# تثبيت Git
sudo apt install git -y
```

### 2. إعداد قاعدة البيانات PostgreSQL
```bash
# الدخول كـ postgres user
sudo -u postgres psql

# إنشاء قاعدة البيانات والمستخدم
CREATE DATABASE manga_platform;
CREATE USER manga_user WITH PASSWORD 'كلمة_سر_قوية';
GRANT ALL PRIVILEGES ON DATABASE manga_platform TO manga_user;
\q
```

### 3. رفع ملفات المشروع
```bash
# الذهاب إلى مجلد الويب
cd /var/www/

# استنساخ المشروع (أو رفع الملفات)
sudo git clone https://github.com/your-repo/manga-platform.git
# أو رفع الملفات عبر SCP/SFTP

# تغيير المالك للمجلد
sudo chown -R $USER:$USER /var/www/manga-platform
cd /var/www/manga-platform
```

### 4. إعداد البيئة الافتراضية
```bash
# إنشاء البيئة الافتراضية
python3.11 -m venv venv

# تفعيل البيئة
source venv/bin/activate

# تثبيت المكتبات
pip install --upgrade pip
pip install -r requirements.txt
# أو من pyproject.toml
pip install -e .
```

### 5. إعداد متغيرات البيئة
```bash
# إنشاء ملف .env
nano .env
```

```bash
# محتوى ملف .env
DATABASE_URL=postgresql://manga_user:كلمة_سر_قوية@localhost/manga_platform
SESSION_SECRET=مفتاح_سري_طويل_وقوي_هنا
FLASK_ENV=production
CLOUDINARY_CLOUD_NAME=اسم_cloudinary_account
CLOUDINARY_API_KEY=مفتاح_cloudinary
CLOUDINARY_API_SECRET=سر_cloudinary
```

### 6. إعداد قاعدة البيانات
```bash
# تشغيل إعداد قاعدة البيانات
python database_init.py
```

## إعداد Gunicorn

### 1. إنشاء ملف خدمة systemd
```bash
sudo nano /etc/systemd/system/manga-platform.service
```

```ini
[Unit]
Description=Manga Platform Web Application
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/manga-platform
Environment="PATH=/var/www/manga-platform/venv/bin"
EnvironmentFile=/var/www/manga-platform/.env
ExecStart=/var/www/manga-platform/venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 4 --worker-class gevent --worker-connections 1000 --timeout 120 --keep-alive 2 --max-requests 1000 --max-requests-jitter 50 main:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

### 2. تفعيل وتشغيل الخدمة
```bash
# إعادة تحميل systemd
sudo systemctl daemon-reload

# تفعيل الخدمة للتشغيل التلقائي
sudo systemctl enable manga-platform

# تشغيل الخدمة
sudo systemctl start manga-platform

# التحقق من حالة الخدمة
sudo systemctl status manga-platform
```

## إعداد Nginx

### 1. إنشاء ملف إعدادات الموقع
```bash
sudo nano /etc/nginx/sites-available/manga-platform
```

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static/ {
        alias /var/www/manga-platform/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    client_max_body_size 200M;
}
```

### 2. تفعيل الموقع
```bash
# ربط الملف
sudo ln -s /etc/nginx/sites-available/manga-platform /etc/nginx/sites-enabled/

# اختبار إعدادات Nginx
sudo nginx -t

# إعادة تشغيل Nginx
sudo systemctl restart nginx
```

## إعداد SSL (HTTPS)

### 1. تثبيت Certbot
```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 2. الحصول على شهادة SSL
```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## إعداد Cloudinary (اختياري)

### 1. رفع الملفات الموجودة على Cloudinary
```bash
# تشغيل سكريبت رفع الملفات الموجودة
python background_uploader.py
```

## المراقبة والصيانة

### 1. مراقبة السجلات
```bash
# سجلات التطبيق
sudo journalctl -u manga-platform -f

# سجلات Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 2. إعادة تشغيل الخدمات
```bash
# إعادة تشغيل التطبيق
sudo systemctl restart manga-platform

# إعادة تشغيل Nginx
sudo systemctl restart nginx

# إعادة تشغيل PostgreSQL
sudo systemctl restart postgresql
```

## النسخ الاحتياطي

### 1. نسخ احتياطي لقاعدة البيانات
```bash
# إنشاء نسخة احتياطية يومية
pg_dump -U manga_user -h localhost manga_platform > backup_$(date +%Y%m%d).sql
```

### 2. نسخ احتياطي للملفات المرفوعة
```bash
# نسخ مجلد الملفات المرفوعة
tar -czf uploads_backup_$(date +%Y%m%d).tar.gz static/uploads/
```

## نصائح الأمان

1. **تغيير كلمات السر الافتراضية**
2. **تفعيل Firewall**
3. **تحديث النظام بانتظام**
4. **مراقبة استخدام الموارد**
5. **إعداد نسخ احتياطية تلقائية**

## اختبار المشروع

بعد التثبيت، يمكنك زيارة الموقع على:
- HTTP: `http://your-domain.com`
- HTTPS: `https://your-domain.com`

المشروع سيعمل بنفس الطريقة كما يعمل على Replit، مع أداء أفضل وتحكم كامل في الخادم!

## استكشاف الأخطاء

### مشاكل شائعة:
- **Database Connection**: تحقق من إعدادات PostgreSQL
- **Permission Errors**: تأكد من صلاحيات المجلدات
- **Port Issues**: تأكد من أن المنافذ غير مستخدمة
- **Memory Issues**: راقب استخدام الذاكرة