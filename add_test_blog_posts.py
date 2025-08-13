#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime, timedelta

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import BlogPost, User

def add_test_blog_posts():
    """Add 4 test blog posts to the database"""
    
    with app.app_context():
        # Get admin user (assuming ID 1 exists)
        admin_user = User.query.filter_by(id=1).first()
        if not admin_user:
            print("Admin user not found. Please create an admin user first.")
            return
        
        # Check if test posts already exist
        existing_posts = BlogPost.query.filter(BlogPost.slug.like('%-test-%')).count()
        if existing_posts > 0:
            print(f"Found {existing_posts} existing test posts. Removing them first...")
            BlogPost.query.filter(BlogPost.slug.like('%-test-%')).delete()
            db.session.commit()
        
        # Test blog posts data
        test_posts = [
            {
                'title': 'New Manga Releases Coming This Month',
                'title_ar': 'إصدارات مانجا جديدة قادمة هذا الشهر',
                'slug': 'new-manga-releases-test-1',
                'content': '''<h2>Exciting New Manga Series to Watch</h2>
<p>This month brings us several exciting new manga releases that are sure to captivate readers worldwide. From action-packed adventures to heartwarming slice-of-life stories, there's something for everyone.</p>

<h3>Top Picks</h3>
<ul>
<li><strong>Dragon Master Chronicles</strong> - An epic fantasy adventure following a young warrior's journey to master ancient dragon magic</li>
<li><strong>Tokyo High School Stories</strong> - A romantic comedy series about friendship and love in modern Japan</li>
<li><strong>Cyber Warriors 2077</strong> - A futuristic action thriller set in a cyberpunk world</li>
<li><strong>Mystic Gardens</strong> - A beautiful slice-of-life series about a magical botanical garden</li>
</ul>

<p>Each of these series brings something unique to the table, whether it's stunning artwork, compelling storytelling, or innovative concepts that push the boundaries of the medium.</p>''',
                'content_ar': '''<h2>سلاسل مانجا جديدة ومثيرة للمتابعة</h2>
<p>يجلب لنا هذا الشهر عدة إصدارات مانجا جديدة ومثيرة من المؤكد أنها ستجذب القراء حول العالم. من المغامرات المليئة بالحركة إلى قصص الحياة اليومية المؤثرة، هناك شيء للجميع.</p>

<h3>أفضل الاختيارات</h3>
<ul>
<li><strong>سجلات سيد التنين</strong> - مغامرة خيالية ملحمية تتبع رحلة محارب شاب لإتقان سحر التنين القديم</li>
<li><strong>قصص مدرسة طوكيو الثانوية</strong> - سلسلة كوميدية رومانسية عن الصداقة والحب في اليابان الحديثة</li>
<li><strong>محاربو السايبر 2077</strong> - إثارة مستقبلية مليئة بالحركة في عالم السايبربانك</li>
<li><strong>الحدائق السحرية</strong> - سلسلة جميلة عن الحياة اليومية حول حديقة نباتية سحرية</li>
</ul>

<p>كل من هذه السلاسل تجلب شيئاً فريداً، سواء كان فناً مذهلاً أو سرداً مقنعاً أو مفاهيم مبتكرة تدفع حدود الوسط.</p>''',
                'excerpt': 'Discover the most anticipated manga releases coming this month with our comprehensive guide to new series.',
                'excerpt_ar': 'اكتشف أكثر إصدارات المانجا المنتظرة هذا الشهر مع دليلنا الشامل للسلاسل الجديدة.',
                'category': 'News',
                'category_ar': 'أخبار',
                'tags': 'manga, new releases, monthly, recommendations',
                'tags_ar': 'مانجا, إصدارات جديدة, شهرية, توصيات',
                'meta_description': 'New manga releases this month including Dragon Master Chronicles, Tokyo High School Stories, and Cyber Warriors 2077.',
                'meta_description_ar': 'إصدارات مانجا جديدة هذا الشهر تشمل سجلات سيد التنين وقصص مدرسة طوكيو الثانوية ومحاربو السايبر 2077.',
                'meta_keywords': 'manga, new, releases, dragon master, tokyo, cyber warriors',
                'featured_image': 'https://images.unsplash.com/photo-1578662996442-48f60103fc96?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80',
                'is_published': True,
                'is_featured': True,
                'views': 156,
                'reading_time': 3,
                'created_days_ago': 0,
            },
            {
                'title': 'Platform Update: Enhanced Reading Experience',
                'title_ar': 'تحديث المنصة: تجربة قراءة محسنة',
                'slug': 'platform-update-enhanced-reading-test-2',
                'content': '''<h2>Major Platform Improvements</h2>
<p>We're excited to announce significant improvements to our manga reading platform. These updates focus on providing a smoother, faster, and more enjoyable reading experience for all our users.</p>

<h3>New Features</h3>
<ul>
<li><strong>Improved page loading speed</strong> - Pages now load 40% faster thanks to optimized image compression</li>
<li><strong>Better mobile responsiveness</strong> - Enhanced touch controls and gesture support</li>
<li><strong>Enhanced bookmark system</strong> - Never lose your place with our improved progress tracking</li>
<li><strong>New reading modes</strong> - Choose from vertical scroll, page-by-page, or webtoon modes</li>
<li><strong>Dark mode improvements</strong> - Better contrast and eye comfort for night reading</li>
</ul>

<h3>Performance Metrics</h3>
<p>Since implementing these changes, we've seen:</p>
<ul>
<li>40% faster page load times</li>
<li>25% increase in user engagement</li>
<li>50% reduction in reading interruptions</li>
</ul>

<p>These improvements are based on extensive user feedback and our commitment to providing the best manga reading experience possible.</p>''',
                'content_ar': '''<h2>تحسينات كبيرة على المنصة</h2>
<p>نحن متحمسون للإعلان عن تحسينات كبيرة على منصة قراءة المانجا الخاصة بنا. تركز هذه التحديثات على توفير تجربة قراءة أكثر سلاسة وسرعة ومتعة لجميع مستخدمينا.</p>

<h3>ميزات جديدة</h3>
<ul>
<li><strong>تحسين سرعة تحميل الصفحات</strong> - الصفحات تحمل الآن بسرعة أكبر بنسبة 40% بفضل ضغط الصور المحسن</li>
<li><strong>استجابة أفضل للهواتف المحمولة</strong> - عناصر تحكم باللمس محسنة ودعم الإيماءات</li>
<li><strong>نظام إشارات مرجعية محسن</strong> - لن تفقد مكانك أبداً مع تتبع التقدم المحسن</li>
<li><strong>أوضاع قراءة جديدة</strong> - اختر من التمرير العمودي أو صفحة بصفحة أو أوضاع الويبتون</li>
<li><strong>تحسينات الوضع المظلم</strong> - تباين أفضل وراحة للعين للقراءة الليلية</li>
</ul>

<h3>مقاييس الأداء</h3>
<p>منذ تطبيق هذه التغييرات، رأينا:</p>
<ul>
<li>أوقات تحميل أسرع بنسبة 40%</li>
<li>زيادة في مشاركة المستخدمين بنسبة 25%</li>
<li>تقليل انقطاعات القراءة بنسبة 50%</li>
</ul>

<p>هذه التحسينات مبنية على ملاحظات المستخدمين المكثفة والتزامنا بتوفير أفضل تجربة قراءة مانجا ممكنة.</p>''',
                'excerpt': 'Major platform updates including improved speed, mobile responsiveness, and new reading features.',
                'excerpt_ar': 'تحديثات كبيرة للمنصة تشمل تحسين السرعة والاستجابة للهواتف المحمولة وميزات قراءة جديدة.',
                'category': 'Updates',
                'category_ar': 'تحديثات',
                'tags': 'platform, update, reading, improvements, features',
                'tags_ar': 'منصة, تحديث, قراءة, تحسينات, ميزات',
                'meta_description': 'Platform updates with enhanced reading experience, improved speed, and new features for manga readers.',
                'meta_description_ar': 'تحديثات المنصة مع تجربة قراءة محسنة وسرعة مطورة وميزات جديدة لقراء المانجا.',
                'meta_keywords': 'platform, update, reading, speed, mobile, features',
                'featured_image': 'https://images.unsplash.com/photo-1551650975-87deedd944c3?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80',
                'is_published': True,
                'is_featured': False,
                'views': 89,
                'reading_time': 2,
                'created_days_ago': 1,
            },
            {
                'title': 'Artist Spotlight: Meet the Creator of Dragon Chronicles',
                'title_ar': 'تسليط الضوء على الفنان: تعرف على منشئ سجلات التنين',
                'slug': 'artist-spotlight-dragon-chronicles-test-3',
                'content': '''<h2>Behind the Art</h2>
<p>In this exclusive interview, we sit down with the talented artist behind the popular Dragon Chronicles series. Learn about their creative process, inspiration, and what drives their passion for manga.</p>

<h3>The Journey</h3>
<p>Starting from humble beginnings as a self-taught artist, they've grown to become one of the most recognized names in the industry. Their unique art style combines traditional techniques with modern digital tools, creating a visual experience that's both nostalgic and cutting-edge.</p>

<blockquote>
<p>"I believe that every panel should tell a story, even without words. The art should speak to the reader's emotions and draw them into the world I'm creating." - Artist Interview</p>
</blockquote>

<h3>Creative Process</h3>
<p>The artist's workflow is meticulous and thoughtful:</p>
<ol>
<li><strong>Story Planning</strong> - Each chapter begins with detailed storyboards</li>
<li><strong>Character Design</strong> - Sketching and refining character expressions and poses</li>
<li><strong>Background Creation</strong> - Building immersive worlds that enhance the narrative</li>
<li><strong>Digital Finishing</strong> - Adding colors, effects, and final touches</li>
</ol>

<h3>Upcoming Projects</h3>
<p>Get a sneak peek into their upcoming projects and what fans can expect in the future chapters of Dragon Chronicles. The next arc promises to delve deeper into the mythology and introduce new characters that will change everything readers thought they knew about the series.</p>''',
                'content_ar': '''<h2>وراء الفن</h2>
<p>في هذه المقابلة الحصرية، نجلس مع الفنان الموهوب وراء سلسلة سجلات التنين الشهيرة. تعرف على عمليتهم الإبداعية والإلهام وما يحرك شغفهم بالمانجا.</p>

<h3>الرحلة</h3>
<p>بدءاً من بدايات متواضعة كفنان علم نفسه، نما ليصبح أحد أكثر الأسماء شهرة في الصناعة. يجمع أسلوبهم الفني الفريد بين التقنيات التقليدية والأدوات الرقمية الحديثة، مما يخلق تجربة بصرية حنينية ومتطورة في آن واحد.</p>

<blockquote>
<p>"أعتقد أن كل لوحة يجب أن تحكي قصة، حتى بدون كلمات. يجب أن يتحدث الفن إلى مشاعر القارئ ويجذبه إلى العالم الذي أخلقه." - مقابلة الفنان</p>
</blockquote>

<h3>العملية الإبداعية</h3>
<p>سير عمل الفنان دقيق ومدروس:</p>
<ol>
<li><strong>تخطيط القصة</strong> - كل فصل يبدأ بلوحات قصة مفصلة</li>
<li><strong>تصميم الشخصيات</strong> - رسم وتحسين تعابير ومواضع الشخصيات</li>
<li><strong>إنشاء الخلفيات</strong> - بناء عوالم غامرة تعزز السرد</li>
<li><strong>اللمسات الرقمية النهائية</strong> - إضافة الألوان والتأثيرات واللمسات الأخيرة</li>
</ol>

<h3>المشاريع القادمة</h3>
<p>احصل على نظرة خاطفة على مشاريعهم القادمة وما يمكن للمعجبين توقعه في الفصول المستقبلية من سجلات التنين. القوس التالي يعد بالتعمق أكثر في الأساطير وتقديم شخصيات جديدة ستغير كل ما ظن القراء أنهم يعرفونه عن السلسلة.</p>''',
                'excerpt': 'Exclusive interview with the artist behind Dragon Chronicles, discussing their creative process and upcoming projects.',
                'excerpt_ar': 'مقابلة حصرية مع الفنان وراء سجلات التنين، مناقشة عمليتهم الإبداعية والمشاريع القادمة.',
                'category': 'Interviews',
                'category_ar': 'مقابلات',
                'tags': 'artist, interview, dragon chronicles, creative process',
                'tags_ar': 'فنان, مقابلة, سجلات التنين, عملية إبداعية',
                'meta_description': 'Exclusive artist interview revealing the creative process behind Dragon Chronicles manga series.',
                'meta_description_ar': 'مقابلة فنان حصرية تكشف العملية الإبداعية وراء سلسلة مانجا سجلات التنين.',
                'meta_keywords': 'artist, interview, dragon chronicles, manga, creative',
                'featured_image': 'https://images.unsplash.com/photo-1541961017774-22349e4a1262?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80',
                'is_published': True,
                'is_featured': False,
                'views': 234,
                'reading_time': 4,
                'created_days_ago': 2,
            },
            {
                'title': 'Community Event: Manga Art Contest Results',
                'title_ar': 'فعالية المجتمع: نتائج مسابقة فن المانجا',
                'slug': 'manga-art-contest-results-test-4',
                'content': '''<h2>Amazing Talent on Display</h2>
<p>Our first annual Manga Art Contest has concluded, and we're thrilled to showcase the incredible talent within our community. Over 500 artists participated, submitting stunning original artwork that showcased creativity, technical skill, and passion for the medium.</p>

<h3>Contest Categories</h3>
<p>The contest featured four main categories:</p>
<ul>
<li><strong>Character Design</strong> - Original character creations</li>
<li><strong>Scene Illustration</strong> - Detailed environmental artwork</li>
<li><strong>Digital Art</strong> - Modern digital techniques</li>
<li><strong>Traditional Art</strong> - Hand-drawn and painted pieces</li>
</ul>

<h3>Contest Winners</h3>
<ol>
<li><strong>First Place:</strong> "Mystic Warriors" by ArtistUser123 - A breathtaking piece featuring ethereal warriors in a fantasy setting</li>
<li><strong>Second Place:</strong> "School Days Romance" by MangaFan456 - A heartwarming slice-of-life illustration</li>
<li><strong>Third Place:</strong> "Future City" by DigitalArt789 - An impressive cyberpunk cityscape</li>
</ol>

<h3>Special Mentions</h3>
<p>Several other submissions deserve recognition for their creativity and technical skill:</p>
<ul>
<li>"Dragon's Dawn" by CreativeArtist - Stunning use of light and shadow</li>
<li>"Friendship Forever" by MangaLover - Emotional character interaction</li>
<li>"Neon Dreams" by FutureVision - Innovative digital effects</li>
</ul>

<h3>Prizes and Recognition</h3>
<p>All participants receive a digital certificate of participation, and winners get special platform badges, featured artwork displays, and exclusive merchandise. The winning pieces will be featured in our upcoming digital art gallery.</p>

<p>Thank you to everyone who participated! Stay tuned for our next contest announcement.</p>''',
                'content_ar': '''<h2>موهبة مذهلة معروضة</h2>
<p>انتهت مسابقة فن المانجا السنوية الأولى، ونحن متحمسون لعرض الموهبة المذهلة داخل مجتمعنا. شارك أكثر من 500 فنان، مقدمين أعمالاً فنية أصلية مذهلة أظهرت الإبداع والمهارة التقنية والشغف بالوسط.</p>

<h3>فئات المسابقة</h3>
<p>تضمنت المسابقة أربع فئات رئيسية:</p>
<ul>
<li><strong>تصميم الشخصيات</strong> - إبداعات شخصيات أصلية</li>
<li><strong>رسم المشاهد</strong> - أعمال فنية بيئية مفصلة</li>
<li><strong>الفن الرقمي</strong> - تقنيات رقمية حديثة</li>
<li><strong>الفن التقليدي</strong> - قطع مرسومة ومصبوغة يدوياً</li>
</ul>

<h3>الفائزون في المسابقة</h3>
<ol>
<li><strong>المركز الأول:</strong> "المحاربون الصوفيون" بواسطة ArtistUser123 - قطعة خلابة تضم محاربين أثيريين في بيئة خيالية</li>
<li><strong>المركز الثاني:</strong> "رومانسية أيام المدرسة" بواسطة MangaFan456 - رسم توضيحي مؤثر للحياة اليومية</li>
<li><strong>المركز الثالث:</strong> "مدينة المستقبل" بواسطة DigitalArt789 - منظر مدينة سايبربانك مثير للإعجاب</li>
</ol>

<h3>إشادات خاصة</h3>
<p>عدة مشاركات أخرى تستحق التقدير لإبداعها ومهارتها التقنية:</p>
<ul>
<li>"فجر التنين" بواسطة CreativeArtist - استخدام مذهل للضوء والظل</li>
<li>"صداقة إلى الأبد" بواسطة MangaLover - تفاعل شخصيات عاطفي</li>
<li>"أحلام النيون" بواسطة FutureVision - تأثيرات رقمية مبتكرة</li>
</ul>

<h3>الجوائز والتقدير</h3>
<p>جميع المشاركين يحصلون على شهادة مشاركة رقمية، والفائزون يحصلون على شارات منصة خاصة وعروض أعمال فنية مميزة وبضائع حصرية. القطع الفائزة ستعرض في معرض الفن الرقمي القادم.</p>

<p>شكراً لكل من شارك! ترقبوا إعلان مسابقتنا القادمة.</p>''',
                'excerpt': 'Results from our first annual Manga Art Contest featuring over 500 submissions and amazing community talent.',
                'excerpt_ar': 'نتائج مسابقة فن المانجا السنوية الأولى التي تضم أكثر من 500 مشاركة ومواهب مجتمعية مذهلة.',
                'category': 'Community',
                'category_ar': 'المجتمع',
                'tags': 'contest, art, community, winners, manga art',
                'tags_ar': 'مسابقة, فن, مجتمع, فائزون, فن المانجا',
                'meta_description': 'First annual Manga Art Contest results with over 500 submissions and talented community artists.',
                'meta_description_ar': 'نتائج مسابقة فن المانجا السنوية الأولى مع أكثر من 500 مشاركة وفنانين موهوبين من المجتمع.',
                'meta_keywords': 'contest, art, community, manga, winners, creative',
                'featured_image': 'https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80',
                'is_published': True,
                'is_featured': True,
                'views': 312,
                'reading_time': 3,
                'created_days_ago': 3,
            }
        ]
        
        # Add the test posts
        for i, post_data in enumerate(test_posts):
            # Calculate dates
            created_at = datetime.now() - timedelta(days=post_data['created_days_ago'])
            published_at = created_at
            
            # Create new blog post
            blog_post = BlogPost(
                title=post_data['title'],
                title_ar=post_data['title_ar'],
                slug=post_data['slug'],
                content=post_data['content'],
                content_ar=post_data['content_ar'],
                excerpt=post_data['excerpt'],
                excerpt_ar=post_data['excerpt_ar'],
                category=post_data['category'],
                category_ar=post_data['category_ar'],
                tags=post_data['tags'],
                tags_ar=post_data['tags_ar'],
                meta_description=post_data['meta_description'],
                meta_description_ar=post_data['meta_description_ar'],
                meta_keywords=post_data['meta_keywords'],
                featured_image=post_data['featured_image'],
                is_published=post_data['is_published'],
                is_featured=post_data['is_featured'],
                author_id=admin_user.id,
                views=post_data['views'],
                reading_time=post_data['reading_time'],
                created_at=created_at,
                published_at=published_at
            )
            
            db.session.add(blog_post)
            print(f"Added blog post {i+1}: {post_data['title']}")
        
        # Commit all changes
        db.session.commit()
        print("\n✓ Successfully added 4 test blog posts!")
        print("✓ Posts are published and should appear in the latest news section")
        print("✓ You can view them at /blog or in the admin panel at /admin/blog")

if __name__ == '__main__':
    add_test_blog_posts()