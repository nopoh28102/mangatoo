"""
Commercial Features Configuration
تكوين الميزات التجارية للمنصة
"""

# Commercial Feature Flags
COMMERCIAL_FEATURES = {
    # Premium Subscriptions
    'premium_subscriptions': True,
    'subscription_plans': {
        'basic': {
            'name': 'الأساسي',
            'name_en': 'Basic',
            'price_monthly': 9.99,
            'price_yearly': 99.99,
            'features': [
                'قراءة بلا إعلانات',
                'تحميل الفصول',
                'جودة صور عالية',
                'دعم فني أولوية'
            ]
        },
        'premium': {
            'name': 'المميز',
            'name_en': 'Premium', 
            'price_monthly': 19.99,
            'price_yearly': 199.99,
            'features': [
                'جميع ميزات الأساسي',
                'وصول مبكر للفصول الجديدة',
                'مكتبة حفظ غير محدودة',
                'قراءة أوفلاين',
                'إحصائيات قراءة مفصلة'
            ]
        },
        'vip': {
            'name': 'VIP',
            'name_en': 'VIP',
            'price_monthly': 29.99,
            'price_yearly': 299.99,
            'features': [
                'جميع ميزات المميز',
                'محتوى حصري VIP',
                'دعم مباشر 24/7',
                'شارات خاصة',
                'تخصيص واجهة المستخدم'
            ]
        }
    },
    
    # Publisher Tools (Revenue Sharing)
    'publisher_program': True,
    'publisher_commission': 0.70,  # 70% للناشر، 30% للمنصة
    'minimum_payout': 50.00,  # حد أدنى 50 دولار للسحب
    
    # Advertising System
    'advertising': True,
    'ad_revenue_share': 0.60,  # 60% للمؤلف/ناشر
    'ad_types': ['banner', 'interstitial', 'native'],
    
    # Content Monetization
    'paid_chapters': True,
    'chapter_pricing': {
        'min_price': 0.99,
        'max_price': 4.99,
        'recommended_price': 1.99
    },
    
    # White Label Solutions
    'white_label': True,
    'white_label_pricing': {
        'startup': 199,     # شهرياً
        'business': 499,    # شهرياً  
        'enterprise': 999   # شهرياً
    },
    
    # API Access
    'api_access': True,
    'api_pricing': {
        'free_tier': 1000,      # 1000 طلب شهرياً
        'basic_tier': 10000,    # 10000 طلب بـ $29/شهر
        'pro_tier': 100000,     # 100000 طلب بـ $99/شهر
        'enterprise': 'unlimited'  # بلا حدود مع العقد
    },
    
    # Analytics and Insights
    'advanced_analytics': True,
    'analytics_features': [
        'تقارير قراءة مفصلة',
        'إحصائيات الجمهور',
        'تحليل الإيرادات',
        'توقعات النمو',
        'A/B testing tools'
    ],
    
    # Multi-language Support
    'translation_services': True,
    'supported_languages': [
        'العربية', 'English', 'Español', 'Français', 
        '中文', '日本語', '한국어', 'Русский'
    ],
    
    # Mobile Apps
    'mobile_apps': True,
    'app_store_ready': True,
    
    # Security Features
    'enterprise_security': True,
    'security_features': [
        'SSO integration',
        'Advanced user roles',
        'Content DRM',
        'IP blocking',
        'Rate limiting'
    ]
}

# Revenue Streams
REVENUE_STREAMS = {
    'subscriptions': 'النموذج الأساسي للإيرادات',
    'advertising': 'إعلانات مستهدفة للمستخدمين المجانيين',
    'paid_content': 'فصول مدفوعة ومحتوى حصري',
    'publisher_fees': 'عمولة من الناشرين والمؤلفين',
    'white_label': 'ترخيص المنصة للشركات الأخرى',
    'api_access': 'بيع API للمطورين',
    'merchandise': 'بيع منتجات مرتبطة بالمانجا',
    'events': 'فعاليات ومؤتمرات مدفوعة'
}

# Target Markets
TARGET_MARKETS = {
    'primary': {
        'region': 'الشرق الأوسط وشمال أفريقيا',
        'languages': ['العربية'],
        'market_size': 'متنامي بسرعة',
        'competition': 'محدود'
    },
    'secondary': {
        'region': 'آسيا والمحيط الهادئ',
        'languages': ['English', '中文', '日本語'],
        'market_size': 'ضخم ومُشبع جزئياً',
        'competition': 'عالي'
    },
    'expansion': {
        'region': 'أوروبا وأمريكا',
        'languages': ['English', 'Español', 'Français'],
        'market_size': 'متوسط لكن مربح',
        'competition': 'متوسط'
    }
}

# Business Model Validation
BUSINESS_VALIDATION = {
    'mvp_ready': True,
    'scalability': 'High',
    'technical_debt': 'Low',
    'security_audit': 'Required',
    'legal_compliance': 'In Progress',
    'market_research': 'Completed',
    'funding_ready': True
}