# تعليمات تشغيل المشروع على Windows

## المشكلة المحلولة
تم حل مشكلة الـ Circular Import التي كانت تظهر عند تشغيل المشروع على Windows.

## طريقة التشغيل الصحيحة

### الطريقة الأولى: استخدام ملف التشغيل الجديد (الأفضل)
```bash
# في البيئة الافتراضية
python run_local.py
```

### الطريقة الثانية: استخدام main.py
```bash
python main.py
```

### ⚠️ لا تستخدم هذا:
```bash
python app.py  # ❌ هذا يسبب مشكلة Circular Import
```

## الملفات الجديدة المضافة

1. **run_local.py**: ملف تشغيل خاص بالبيئة المحلية
2. **database_init.py**: ملف منفصل لإعداد قاعدة البيانات
3. **تعليمات_التشغيل_على_Windows.md**: هذا الملف

## الحلول المطبقة

✅ فصل إعداد قاعدة البيانات عن ملف app.py  
✅ إنشاء ملف تشغيل منفصل للبيئة المحلية  
✅ تجنب المشكلة الدائرية في الـ imports  
✅ إزالة مكتبة zipfile-deflate64 المسببة لمشاكل التثبيت  

## إذا واجهت أي مشاكل

1. تأكد من تفعيل البيئة الافتراضية:
   ```bash
   venv\Scripts\activate
   ```

2. تأكد من تثبيت جميع المكتبات:
   ```bash
   pip install -r pyproject.toml
   ```

3. استخدم ملف التشغيل المخصص:
   ```bash
   python run_local.py
   ```

## رسائل النجاح المتوقعة
```
INFO:root:✅ Cloudinary models imported successfully
INFO:root:Database tables created successfully
INFO:root:Admin user already exists
Starting Flask development server on Windows...
Access the application at: http://127.0.0.1:5000
```

المشروع سيعمل الآن على Windows بدون أي مشاكل في الـ imports!