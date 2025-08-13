# دليل النشر - Manga Platform Deployment Guide

## إصلاح مشاكل النشر المعروفة

تم إصلاح المشاكل التالية في النسخة الحالية:

### 1. مشكلة قاعدة البيانات للقراءة فقط
- **المشكلة**: `attempt to write a readonly database`
- **الحل**: تحديث `SettingsManager.set()` للتعامل مع قواعد البيانات للقراءة فقط
- **التفاصيل**: يستخدم التطبيق الآن التخزين المؤقت (cache) عند فشل الكتابة في قاعدة البيانات

### 2. مشكلة PendingRollbackError
- **المشكلة**: `Session's transaction has been rolled back`
- **الحل**: إضافة معالجة أخطاء في جميع database queries
- **التفاصيل**: تم تحديث `routes.py` لاستخدام `db.session.rollback()` عند حدوث أخطاء

### 3. مشاكل Health Check
- **المشكلة**: منصات النشر لا تجد endpoint صحي للتطبيق
- **الحل**: إضافة multiple health check endpoints:
  - `/health`
  - `/healthcheck`
  - `/kaithheathcheck`

## متطلبات النشر

### 1. متغيرات البيئة المطلوبة

```bash
# Database (Required in Production)
DATABASE_URL=postgresql://user:password@host:port/database

# Security (Required)
SESSION_SECRET=your-secure-session-secret-here

# Cloudinary (Optional but recommended)
CLOUDINARY_CLOUD_NAME=your-cloudinary-cloud-name
CLOUDINARY_API_KEY=your-cloudinary-api-key
CLOUDINARY_API_SECRET=your-cloudinary-api-secret

# Environment
FLASK_ENV=production
```

### 2. ملفات النشر

- `Procfile`: محدث لإعدادات gunicorn محسنة
- `runtime.txt`: يحدد Python 3.11
- `production_config.py`: إعدادات الإنتاج
- Health check endpoints في `app.py`

## منصات النشر المدعومة

### Leapcell
1. ارفع الملفات إلى repository
2. اربط repository بـ Leapcell
3. تأكد من إعداد متغيرات البيئة
4. سيستخدم النظام `Procfile` تلقائياً

### Heroku
1. إنشاء تطبيق جديد: `heroku create app-name`
2. إضافة PostgreSQL: `heroku addons:create heroku-postgresql:hobby-dev`
3. إعداد متغيرات البيئة: `heroku config:set SESSION_SECRET=your-secret`
4. النشر: `git push heroku main`

### Railway
1. اربط GitHub repository
2. أضف متغيرات البيئة في dashboard
3. النظام سيكتشف `Procfile` تلقائياً

### Docker (اختياري)
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
```

## اختبار النشر

بعد النشر، تأكد من:

1. **Health Check**: زر `your-domain.com/health`
2. **قاعدة البيانات**: تأكد من عمل الصفحة الرئيسية
3. **الصور**: تأكد من عمل رفع وعرض الصور
4. **تسجيل الدخول**: اختبر نظام المستخدمين

## استكشاف الأخطاء

### مشكلة البورت
إذا ظهر خطأ timeout للبورت:
- تأكد من أن التطبيق يستمع على `0.0.0.0:$PORT`
- تحقق من `Procfile` يستخدم `$PORT` variable

### مشكلة قاعدة البيانات
إذا لم تعمل قاعدة البيانات:
- تحقق من `DATABASE_URL` في متغيرات البيئة
- تأكد من إنشاء جداول قاعدة البيانات
- راجع logs للأخطاء التفصيلية

### مشاكل الصور
إذا لم تظهر الصور:
- تحقق من إعداد Cloudinary
- تأكد من صحة API keys
- اختبر رفع صورة جديدة

## الأداء والتحسين

### إعدادات gunicorn المحسنة
```bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --keep-alive 2 --max-requests 1000 --max-requests-jitter 100 main:app
```

### نصائح الأداء
- استخدم CDN للصور الثابتة
- فعل caching في الإنتاج
- راقب استخدام الذاكرة
- استخدم قاعدة بيانات منفصلة للإنتاج

## الأمان

### إعدادات الأمان المطلوبة
- `SESSION_SECRET`: مفتاح جلسة قوي
- `FLASK_ENV=production`: لإخفاء تفاصيل الأخطاء
- HTTPS: يجب استخدام SSL certificate
- قاعدة بيانات آمنة: استخدم connection string آمن

### نصائح الأمان
- غير أسرار الأمان بانتظام
- راقب logs للأنشطة المشبوهة
- حدد أذونات المستخدمين بعناية
- استخدم firewall لحماية قاعدة البيانات

## الدعم

إذا واجهت مشاكل في النشر:
1. راجع logs المنصة المستخدمة
2. تحقق من جميع متغيرات البيئة
3. اختبر التطبيق محلياً أولاً
4. تأكد من تحديث جميع التبعيات

---

تم إعداد هذا الدليل بناءً على حل المشاكل التي واجهتها في النشر السابق.