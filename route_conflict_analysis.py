#!/usr/bin/env python3
"""
تحليل التضارب الحقيقي في المسارات
"""
import re

def analyze_real_conflicts():
    """تحليل التضارب الحقيقي في المسارات"""
    print("🔍 تحليل التضارب الحقيقي في المسارات")
    
    with open('routes.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # البحث عن جميع المسارات مع تفاصيلها
    route_pattern = r"@app\.route\(['\"]([^'\"]+)['\"](?:,\s*methods=(\[[^\]]+\]))?\)\s*\n(?:@[\w_]+\s*\n)*def\s+(\w+)"
    matches = re.finditer(route_pattern, content, re.MULTILINE)
    
    routes = []
    for match in matches:
        route = match.group(1)
        methods = match.group(2) or "['GET']"
        function_name = match.group(3)
        routes.append({
            'route': route,
            'methods': methods,
            'function': function_name
        })
    
    print(f"إجمالي المسارات: {len(routes)}")
    
    # فحص التضارب الحقيقي
    real_conflicts = []
    for i, route1 in enumerate(routes):
        for route2 in routes[i+1:]:
            if would_conflict(route1, route2):
                real_conflicts.append((route1, route2))
    
    if real_conflicts:
        print(f"\n🚨 تضارب حقيقي في المسارات: {len(real_conflicts)}")
        for route1, route2 in real_conflicts:
            print(f"  ❌ {route1['route']} ({route1['function']}) <-> {route2['route']} ({route2['function']})")
            print(f"     الطرق: {route1['methods']} vs {route2['methods']}")
    else:
        print("\n✅ لا يوجد تضارب حقيقي في المسارات")
    
    # تحليل المسارات بناءً على النوع
    analyze_by_type(routes)
    
    return real_conflicts

def would_conflict(route1, route2):
    """فحص ما إذا كان مساران سيتضاربان فعلياً"""
    # إذا كانت المسارات متطابقة تماماً
    if route1['route'] == route2['route']:
        # فحص الطرق المختلفة
        methods1 = set(eval(route1['methods']))
        methods2 = set(eval(route2['methods']))
        # إذا كانت الطرق متداخلة، فهناك تضارب
        return bool(methods1.intersection(methods2))
    
    # فحص التضارب في النمط
    pattern1 = route_to_pattern(route1['route'])
    pattern2 = route_to_pattern(route2['route'])
    
    # إذا كان أحد الأنماط يطابق الآخر
    if re.fullmatch(pattern1, route2['route']) or re.fullmatch(pattern2, route1['route']):
        # فحص الطرق
        methods1 = set(eval(route1['methods']))
        methods2 = set(eval(route2['methods']))
        return bool(methods1.intersection(methods2))
    
    return False

def route_to_pattern(route):
    """تحويل المسار إلى نمط regex"""
    # تحويل Flask variable rules إلى regex
    pattern = route
    pattern = re.sub(r'<int:([^>]+)>', r'(?P<\1>\\d+)', pattern)
    pattern = re.sub(r'<float:([^>]+)>', r'(?P<\1>\\d+\\.\\d+)', pattern)
    pattern = re.sub(r'<([^>]+)>', r'(?P<\1>[^/]+)', pattern)
    pattern = f"^{pattern}$"
    return pattern

def analyze_by_type(routes):
    """تحليل المسارات بناءً على النوع"""
    print("\n📊 تحليل المسارات بناءً على النوع:")
    
    types = {
        'static': [],
        'manga': [],
        'admin': [],
        'api': [],
        'auth': [],
        'user': [],
        'publisher': []
    }
    
    for route in routes:
        path = route['route']
        if path.startswith('/admin'):
            types['admin'].append(route)
        elif path.startswith('/api'):
            types['api'].append(route)
        elif path.startswith('/publisher'):
            types['publisher'].append(route)
        elif path.startswith('/user'):
            types['user'].append(route)
        elif path in ['/login', '/register', '/logout']:
            types['auth'].append(route)
        elif path.startswith('/manga') or path.startswith('/read'):
            types['manga'].append(route)
        else:
            types['static'].append(route)
    
    for type_name, routes_list in types.items():
        if routes_list:
            print(f"  {type_name}: {len(routes_list)} مسار")

def check_template_conflicts():
    """فحص تضارب القوالب"""
    print("\n📄 تحليل تضارب القوالب:")
    
    import os
    template_usage = {}
    
    # البحث عن استخدام القوالب في routes.py
    with open('routes.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    template_pattern = r"render_template\(['\"]([^'\"]+)['\"]"
    matches = re.findall(template_pattern, content)
    
    for template in matches:
        if template not in template_usage:
            template_usage[template] = 0
        template_usage[template] += 1
    
    print(f"إجمالي القوالب المستخدمة: {len(template_usage)}")
    
    # فحص القوالب المكررة في أسماء الملفات
    template_files = {}
    for root, dirs, files in os.walk('templates'):
        for file in files:
            if file.endswith('.html'):
                full_path = os.path.join(root, file)
                if file not in template_files:
                    template_files[file] = []
                template_files[file].append(full_path)
    
    duplicates = {name: paths for name, paths in template_files.items() if len(paths) > 1}
    if duplicates:
        print(f"\n⚠️ ملفات قوالب بنفس الاسم: {len(duplicates)}")
        for name, paths in duplicates.items():
            print(f"  {name}:")
            for path in paths:
                print(f"    - {path}")
            
            # فحص الاستخدام
            if name in template_usage:
                print(f"    📊 مستخدم {template_usage[name]} مرة في الكود")
            else:
                print(f"    ⚠️ غير مستخدم في الكود")

if __name__ == "__main__":
    conflicts = analyze_real_conflicts()
    check_template_conflicts()
    
    if not conflicts:
        print("\n✅ المشروع آمن - لا يوجد تضارب حقيقي في المسارات")
    else:
        print(f"\n🚨 يحتاج إصلاح: {len(conflicts)} تضارب حقيقي")