#!/usr/bin/env python3
"""
تحليل شامل للمشروع للعثور على التكرار والتضارب في الصفحات والمسارات
"""
import os
import re
from collections import defaultdict

def analyze_routes():
    """تحليل المسارات المكررة"""
    print("=== تحليل المسارات في routes.py ===")
    
    routes = {}
    duplicate_routes = defaultdict(list)
    
    with open('routes.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # البحث عن جميع المسارات
    route_pattern = r"@app\.route\(['\"]([^'\"]+)['\"](?:,\s*methods=\[[^\]]+\])?\)\s*\n(?:@[\w_]+\s*\n)*def\s+(\w+)"
    matches = re.finditer(route_pattern, content, re.MULTILINE)
    
    for match in matches:
        route = match.group(1)
        function_name = match.group(2)
        
        if route in routes:
            duplicate_routes[route].append({
                'existing': routes[route],
                'new': function_name
            })
        else:
            routes[route] = function_name
            
    print(f"إجمالي المسارات: {len(routes)}")
    
    if duplicate_routes:
        print("\n⚠️ مسارات مكررة محتملة:")
        for route, duplicates in duplicate_routes.items():
            print(f"  {route}:")
            for dup in duplicates:
                print(f"    - {dup['existing']} / {dup['new']}")
    
    # البحث عن مسارات متشابهة
    similar_routes = []
    route_list = list(routes.keys())
    for i, route1 in enumerate(route_list):
        for route2 in route_list[i+1:]:
            if routes_are_similar(route1, route2):
                similar_routes.append((route1, route2, routes[route1], routes[route2]))
    
    if similar_routes:
        print("\n⚠️ مسارات متشابهة قد تسبب تضارب:")
        for route1, route2, func1, func2 in similar_routes:
            print(f"  {route1} ({func1}) <-> {route2} ({func2})")
    
    return routes, duplicate_routes, similar_routes

def routes_are_similar(route1, route2):
    """فحص إذا كانت المسارات متشابهة بشكل قد يسبب تضارب"""
    # إزالة أنواع البيانات من المتغيرات
    clean1 = re.sub(r'<[^>]+>', '<var>', route1)
    clean2 = re.sub(r'<[^>]+>', '<var>', route2)
    
    # مقارنة النمط العام
    pattern1 = clean1.replace('<var>', '.*')
    pattern2 = clean2.replace('<var>', '.*')
    
    return (re.match(pattern1, route2) or re.match(pattern2, route1)) and route1 != route2

def analyze_templates():
    """تحليل القوالب المكررة"""
    print("\n=== تحليل القوالب ===")
    
    template_files = []
    template_names = defaultdict(list)
    
    # جمع جميع ملفات HTML
    for root, dirs, files in os.walk('templates'):
        for file in files:
            if file.endswith('.html'):
                full_path = os.path.join(root, file)
                template_files.append(full_path)
                template_names[file].append(full_path)
    
    print(f"إجمالي ملفات القوالب: {len(template_files)}")
    
    # البحث عن أسماء مكررة
    duplicates = {name: paths for name, paths in template_names.items() if len(paths) > 1}
    
    if duplicates:
        print("\n⚠️ أسماء قوالب مكررة:")
        for name, paths in duplicates.items():
            print(f"  {name}:")
            for path in paths:
                print(f"    - {path}")
    
    return template_files, duplicates

def analyze_template_content():
    """تحليل محتوى القوالب للعثور على تكرار"""
    print("\n=== تحليل محتوى القوالب ===")
    
    template_content = {}
    content_hashes = defaultdict(list)
    
    for root, dirs, files in os.walk('templates'):
        for file in files:
            if file.endswith('.html'):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        template_content[full_path] = content
                        
                        # حساب hash للمحتوى (تجاهل المسافات)
                        normalized = re.sub(r'\s+', ' ', content.strip())
                        content_hash = hash(normalized)
                        content_hashes[content_hash].append(full_path)
                except Exception as e:
                    print(f"خطأ في قراءة {full_path}: {e}")
    
    # البحث عن محتوى مطابق تماماً
    exact_duplicates = {h: paths for h, paths in content_hashes.items() if len(paths) > 1}
    
    if exact_duplicates:
        print("\n⚠️ قوالب بمحتوى مطابق:")
        for content_hash, paths in exact_duplicates.items():
            print(f"  المحتوى متطابق:")
            for path in paths:
                print(f"    - {path}")
    
    return exact_duplicates

def analyze_function_names():
    """تحليل أسماء الدوال المكررة"""
    print("\n=== تحليل أسماء الدوال ===")
    
    with open('routes.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # البحث عن جميع تعريفات الدوال
    function_pattern = r"def\s+(\w+)\s*\("
    matches = re.findall(function_pattern, content)
    
    function_counts = defaultdict(int)
    for func in matches:
        function_counts[func] += 1
    
    duplicates = {name: count for name, count in function_counts.items() if count > 1}
    
    if duplicates:
        print("\n⚠️ أسماء دوال مكررة:")
        for name, count in duplicates.items():
            print(f"  {name}: {count} مرة")
    
    return duplicates

def check_route_function_mapping():
    """فحص تطابق المسارات مع الدوال"""
    print("\n=== فحص تطابق المسارات مع الدوال ===")
    
    with open('routes.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # البحث عن المسارات والدوال المرتبطة
    route_function_pattern = r"@app\.route\(['\"]([^'\"]+)['\"](?:[^)]+)?\)\s*(?:@[\w_]+\s*)*\ndef\s+(\w+)"
    matches = re.findall(route_function_pattern, content, re.MULTILINE | re.DOTALL)
    
    route_to_functions = defaultdict(list)
    function_to_routes = defaultdict(list)
    
    for route, function in matches:
        route_to_functions[route].append(function)
        function_to_routes[function].append(route)
    
    # البحث عن مسارات مع دوال متعددة
    multi_function_routes = {route: funcs for route, funcs in route_to_functions.items() if len(funcs) > 1}
    
    if multi_function_routes:
        print("\n⚠️ مسارات مع دوال متعددة:")
        for route, functions in multi_function_routes.items():
            print(f"  {route}: {', '.join(functions)}")
    
    # البحث عن دوال مع مسارات متعددة
    multi_route_functions = {func: routes for func, routes in function_to_routes.items() if len(routes) > 1}
    
    if multi_route_functions:
        print("\n⚠️ دوال مع مسارات متعددة:")
        for function, routes in multi_route_functions.items():
            print(f"  {function}: {', '.join(routes)}")
    
    return multi_function_routes, multi_route_functions

def main():
    print("🔍 فحص المشروع للعثور على التكرار والتضارب\n")
    
    # تحليل المسارات
    routes, duplicate_routes, similar_routes = analyze_routes()
    
    # تحليل القوالب
    template_files, template_duplicates = analyze_templates()
    
    # تحليل محتوى القوالب
    content_duplicates = analyze_template_content()
    
    # تحليل أسماء الدوال
    function_duplicates = analyze_function_names()
    
    # فحص تطابق المسارات والدوال
    multi_function_routes, multi_route_functions = check_route_function_mapping()
    
    # ملخص النتائج
    print("\n" + "="*50)
    print("📊 ملخص التحليل:")
    
    issues_found = 0
    
    if duplicate_routes:
        print(f"⚠️ {len(duplicate_routes)} مسار مكرر")
        issues_found += len(duplicate_routes)
    
    if similar_routes:
        print(f"⚠️ {len(similar_routes)} مسار متشابه")
        issues_found += len(similar_routes)
    
    if template_duplicates:
        print(f"⚠️ {len(template_duplicates)} اسم قالب مكرر")
        issues_found += len(template_duplicates)
    
    if content_duplicates:
        print(f"⚠️ {len(content_duplicates)} قالب بمحتوى مطابق")
        issues_found += len(content_duplicates)
    
    if function_duplicates:
        print(f"⚠️ {len(function_duplicates)} اسم دالة مكرر")
        issues_found += len(function_duplicates)
    
    if multi_function_routes:
        print(f"⚠️ {len(multi_function_routes)} مسار مع دوال متعددة")
        issues_found += len(multi_function_routes)
    
    if multi_route_functions:
        print(f"⚠️ {len(multi_route_functions)} دالة مع مسارات متعددة")
        issues_found += len(multi_route_functions)
    
    if issues_found == 0:
        print("✅ لم يتم العثور على مشاكل تكرار واضحة")
    else:
        print(f"\n🚨 إجمالي المشاكل المحتملة: {issues_found}")
        print("يُنصح بمراجعة هذه النقاط لتجنب التضارب")

if __name__ == "__main__":
    main()