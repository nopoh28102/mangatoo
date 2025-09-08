# مثال لتكوين PostgreSQL بطرق مختلفة

## الطريقة 1: متغير البيئة (الأفضل والأكثر أماناً)
import os
DATABASE_URL = os.environ.get("DATABASE_URL")

## الطريقة 2: كتابة البيانات مباشرة (للاختبار فقط)
# DATABASE_URL = "postgresql://username:password@host:port/database_name"

## أمثلة لصيغ اتصال PostgreSQL مختلفة:

# مثال 1: خادم محلي
# DATABASE_URL = "postgresql://postgres:password@localhost:5432/manga_db"

# مثال 2: خادم خارجي
# DATABASE_URL = "postgresql://user:pass@external-host.com:5432/manga_platform"

# مثال 3: خدمة سحابية (مثل Heroku)
# DATABASE_URL = "postgres://user:pass@host:5432/dbname"

# مثال 4: Supabase
# DATABASE_URL = "postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres"

# مثال 5: Railway
# DATABASE_URL = "postgresql://postgres:password@containers-us-west-xxx.railway.app:7XXX/railway"

## تطبيق الإعدادات في Flask
def configure_database(app):
    DATABASE_URL = os.environ.get("DATABASE_URL") or "sqlite:///manga_platform.db"
    
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        # PostgreSQL إعدادات
        app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 300,        # إعادة تدوير الاتصالات كل 5 دقائق
            "pool_pre_ping": True,      # فحص الاتصال قبل الاستخدام
            "pool_size": 10,            # عدد الاتصالات النشطة
            "max_overflow": 20,         # الحد الأقصى للاتصالات الإضافية
            "pool_timeout": 30,         # مهلة انتظار الاتصال (ثانية)
            "pool_reset_on_return": 'commit'  # تأكيد التغييرات عند الإرجاع
        }
        print("✅ تم تكوين PostgreSQL")
    else:
        # SQLite إعدادات (للتطوير المحلي)
        app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
        }
        print("✅ تم تكوين SQLite")

## أماكن وضع بيانات الاتصال:

# 1. في متغيرات البيئة
#    DATABASE_URL=postgresql://user:pass@host:port/db

# 2. في ملف .env (للتطوير المحلي)
#    DATABASE_URL=postgresql://user:pass@host:port/db

# 3. في إعدادات المنصة السحابية
#    leapcell.io -> Environment Variables -> DATABASE_URL

# 4. مباشرة في الكود (غير آمن)
#    DATABASE_URL = "postgresql://..."