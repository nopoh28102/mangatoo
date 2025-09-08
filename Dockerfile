# استخدم Python 3.12
FROM python:3.12-slim

# إنشاء مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .

# إنشاء environment افتراضية داخل الحاوية
RUN python -m venv venv && \
    venv/bin/pip install --upgrade pip && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# شغّل Gunicorn على البورت 5000 باستخدام البيئة الافتراضية
CMD ["/venv/bin/gunicorn", "-b", "0.0.0.0:5000", "main:app"]
