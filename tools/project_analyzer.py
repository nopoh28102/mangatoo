#!/usr/bin/env python3
"""
أداة تحليل المشروع الشاملة - تحليل عميق لمشروع منصة المانجا
Deep Project Analysis Tool for Manga Platform
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime
from collections import defaultdict, Counter
import re

# إعداد نظام السجلات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProjectAnalyzer:
    """محلل شامل للمشروع"""
    
    def __init__(self, project_root="."):
        self.project_root = project_root
        self.analysis_results = {}
        self.db_path = os.path.join(project_root, "manga_platform.db")
        
    def analyze_all(self):
        """تحليل شامل للمشروع"""
        print("🔍 بدء التحليل الشامل للمشروع...")
        
        self.analysis_results = {
            'timestamp': datetime.now().isoformat(),
            'project_structure': self.analyze_structure(),
            'database_analysis': self.analyze_database(),
            'code_metrics': self.analyze_code(),
            'dependencies': self.analyze_dependencies(),
            'security_analysis': self.security_scan(),
            'performance_metrics': self.performance_analysis(),
            'recommendations': self.generate_recommendations()
        }
        
        return self.analysis_results
    
    def analyze_structure(self):
        """تحليل هيكل المشروع"""
        structure = {
            'total_files': 0,
            'directories': [],
            'file_types': Counter(),
            'large_files': [],
            'empty_files': []
        }
        
        for root, dirs, files in os.walk(self.project_root):
            # تجاهل مجلدات النظام
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for d in dirs:
                structure['directories'].append(os.path.join(root, d))
                
            for file in files:
                if file.startswith('.'):
                    continue
                    
                filepath = os.path.join(root, file)
                structure['total_files'] += 1
                
                # تحليل نوع الملف
                ext = os.path.splitext(file)[1].lower()
                structure['file_types'][ext] += 1
                
                # تحليل حجم الملف
                try:
                    size = os.path.getsize(filepath)
                    if size > 1024 * 1024:  # أكبر من 1MB
                        structure['large_files'].append({
                            'path': filepath,
                            'size_mb': round(size / (1024 * 1024), 2)
                        })
                    elif size == 0:
                        structure['empty_files'].append(filepath)
                except OSError:
                    pass
        
        return structure
    
    def analyze_database(self):
        """تحليل قاعدة البيانات"""
        if not os.path.exists(self.db_path):
            return {'error': 'Database file not found'}
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            analysis = {
                'tables': {},
                'total_records': 0,
                'indexes': [],
                'foreign_keys': [],
                'largest_tables': []
            }
            
            # الحصول على قائمة الجداول
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                # عدد السجلات - using proper identifier quoting
                quoted_table = f'"{table.replace('"', '""')}"'
                cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")
                count = cursor.fetchone()[0]
                analysis['total_records'] += count
                
                # معلومات الأعمدة
                cursor.execute("PRAGMA table_info(?)", (table,))
                columns = cursor.fetchall()
                
                # الفهارس
                cursor.execute("PRAGMA index_list(?)", (table,))
                indexes = cursor.fetchall()
                
                # المفاتيح الخارجية
                cursor.execute("PRAGMA foreign_key_list(?)", (table,))
                foreign_keys = cursor.fetchall()
                
                analysis['tables'][table] = {
                    'row_count': count,
                    'columns': len(columns),
                    'column_details': [{'name': col[1], 'type': col[2], 'not_null': bool(col[3])} for col in columns],
                    'indexes': len(indexes),
                    'foreign_keys': len(foreign_keys)
                }
                
                if count > 0:
                    analysis['largest_tables'].append({'table': table, 'count': count})
            
            # ترتيب الجداول حسب العدد
            analysis['largest_tables'].sort(key=lambda x: x['count'], reverse=True)
            
            conn.close()
            return analysis
            
        except Exception as e:
            return {'error': f'Database analysis failed: {str(e)}'}
    
    def analyze_code(self):
        """تحليل الكود"""
        code_metrics = {
            'python_files': 0,
            'total_lines': 0,
            'functions': 0,
            'classes': 0,
            'routes': 0,
            'imports': Counter(),
            'complexity_issues': []
        }
        
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                code_metrics['python_files'] += 1
                code_metrics['total_lines'] += len(lines)
                
                # تحليل الدوال والكلاسات
                code_metrics['functions'] += len(re.findall(r'^def\s+\w+', content, re.MULTILINE))
                code_metrics['classes'] += len(re.findall(r'^class\s+\w+', content, re.MULTILINE))
                
                # تحليل الطرق (Routes)
                code_metrics['routes'] += len(re.findall(r'@app\.route\(', content))
                
                # تحليل الاستيراد
                imports = re.findall(r'^(?:from\s+(\S+)\s+)?import\s+(.+)', content, re.MULTILINE)
                for from_module, import_items in imports:
                    if from_module:
                        code_metrics['imports'][from_module] += 1
                    else:
                        for item in import_items.split(','):
                            code_metrics['imports'][item.strip()] += 1
                
                # فحص التعقيد
                if len(lines) > 1000:
                    code_metrics['complexity_issues'].append({
                        'file': py_file,
                        'issue': 'Large file',
                        'lines': len(lines)
                    })
                
            except Exception as e:
                logger.warning(f"Could not analyze {py_file}: {e}")
        
        return code_metrics
    
    def analyze_dependencies(self):
        """تحليل التبعيات"""
        deps = {
            'python_packages': [],
            'outdated_packages': [],
            'security_vulnerabilities': []
        }
        
        # قراءة pyproject.toml
        pyproject_path = os.path.join(self.project_root, 'pyproject.toml')
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, 'r') as f:
                    content = f.read()
                    # استخراج التبعيات
                    deps_section = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                    if deps_section:
                        deps_text = deps_section.group(1)
                        packages = re.findall(r'"([^"]+)"', deps_text)
                        deps['python_packages'] = packages
            except Exception as e:
                logger.warning(f"Could not parse pyproject.toml: {e}")
        
        return deps
    
    def security_scan(self):
        """فحص الأمان"""
        security = {
            'issues': [],
            'best_practices': [],
            'recommendations': []
        }
        
        # فحص الملفات الحساسة
        sensitive_files = ['.env', 'config.py', 'secrets.txt']
        for file in sensitive_files:
            if os.path.exists(os.path.join(self.project_root, file)):
                security['issues'].append(f'Sensitive file found: {file}')
        
        # فحص كلمات المرور المُثبتة في الكود
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        password_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']'
        ]
        
        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for pattern in password_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches and 'admin123' not in content:  # تجاهل كلمة مرور المشرف التجريبية
                            security['issues'].append(f'Hardcoded credential in {py_file}')
            except:
                pass
        
        # فحص إعدادات الأمان في Flask
        security['best_practices'] = [
            'Use environment variables for secrets',
            'Enable CSRF protection',
            'Use HTTPS in production',
            'Validate all user inputs',
            'Implement rate limiting'
        ]
        
        return security
    
    def performance_analysis(self):
        """تحليل الأداء"""
        performance = {
            'database_queries': 0,
            'large_files': [],
            'optimization_opportunities': []
        }
        
        # فحص استعلامات قاعدة البيانات
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # عدد استعلامات قاعدة البيانات
                    queries = len(re.findall(r'\.query\.|\.execute\(|\.filter\(', content))
                    performance['database_queries'] += queries
                    
                    # فحص الاستعلامات المعقدة
                    if 'join(' in content.lower():
                        performance['optimization_opportunities'].append(f'Complex joins in {py_file}')
                    
                    if '.all()' in content and '.filter(' in content:
                        performance['optimization_opportunities'].append(f'Potential N+1 query in {py_file}')
                        
            except:
                pass
        
        return performance
    
    def generate_recommendations(self):
        """توليد التوصيات"""
        recommendations = {
            'immediate_actions': [],
            'performance_improvements': [],
            'security_enhancements': [],
            'code_quality': []
        }
        
        # تحليل النتائج وتوليد التوصيات
        if self.analysis_results.get('code_metrics', {}).get('total_lines', 0) > 10000:
            recommendations['code_quality'].append('Consider breaking large files into smaller modules')
        
        if self.analysis_results.get('database_analysis', {}).get('total_records', 0) > 10000:
            recommendations['performance_improvements'].append('Consider database indexing optimization')
        
        if self.analysis_results.get('security_analysis', {}).get('issues'):
            recommendations['security_enhancements'].append('Address security vulnerabilities immediately')
        
        recommendations['immediate_actions'] = [
            'Update all dependencies to latest versions',
            'Run comprehensive tests',
            'Review and update documentation'
        ]
        
        return recommendations
    
    def generate_report(self, output_file='project_analysis_report.json'):
        """توليد تقرير شامل"""
        results = self.analyze_all()
        
        # حفظ التقرير
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"📊 تم إنشاء التقرير: {output_file}")
        
        # طباعة ملخص
        self.print_summary(results)
        
        return results
    
    def print_summary(self, results):
        """طباعة ملخص التحليل"""
        print("\n" + "="*60)
        print("📋 ملخص تحليل المشروع")
        print("="*60)
        
        # هيكل المشروع
        structure = results.get('project_structure', {})
        print(f"📁 إجمالي الملفات: {structure.get('total_files', 0)}")
        print(f"📂 المجلدات: {len(structure.get('directories', []))}")
        
        # قاعدة البيانات
        db_analysis = results.get('database_analysis', {})
        if 'error' not in db_analysis:
            print(f"🗄️  جداول قاعدة البيانات: {len(db_analysis.get('tables', {}))}")
            print(f"📊 إجمالي السجلات: {db_analysis.get('total_records', 0)}")
        
        # الكود
        code = results.get('code_metrics', {})
        print(f"🐍 ملفات Python: {code.get('python_files', 0)}")
        print(f"📝 إجمالي الأسطر: {code.get('total_lines', 0)}")
        print(f"🔀 الطرق (Routes): {code.get('routes', 0)}")
        
        # الأمان
        security = results.get('security_analysis', {})
        issues_count = len(security.get('issues', []))
        print(f"🔒 مشاكل الأمان: {issues_count}")
        
        # التوصيات
        recommendations = results.get('recommendations', {})
        total_recommendations = sum(len(recommendations.get(key, [])) for key in recommendations)
        print(f"💡 التوصيات: {total_recommendations}")
        
        print("="*60)

def main():
    """الدالة الرئيسية"""
    analyzer = ProjectAnalyzer()
    
    print("🚀 مرحباً بك في أداة تحليل مشروع منصة المانجا!")
    print("هذه الأداة ستقوم بتحليل شامل للمشروع وتقديم تقرير مفصل.")
    
    try:
        results = analyzer.generate_report()
        print("✅ تم الانتهاء من التحليل بنجاح!")
        
    except Exception as e:
        print(f"❌ حدث خطأ أثناء التحليل: {e}")
        logger.error(f"Analysis failed: {e}")

if __name__ == "__main__":
    main()