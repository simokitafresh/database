#!/usr/bin/env python3
"""
API Debug Analysis Report for app/api
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

def analyze_python_file(file_path: Path) -> Dict[str, Any]:
    """Analyze a Python file for API endpoint information"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Find decorators and functions
        endpoints = []
        imports = []
        classes = []
        functions = []
        
        for node in ast.walk(tree):
            # Import analysis
            if isinstance(node, ast.Import):
                imports.extend([alias.name for alias in node.names])
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend([f"{module}.{alias.name}" for alias in node.names])
            
            # Class analysis
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            
            # Function analysis with decorators
            elif isinstance(node, ast.FunctionDef):
                func_info = {
                    "name": node.name,
                    "decorators": [],
                    "is_async": isinstance(node, ast.AsyncFunctionDef)
                }
                
                # Check decorators for FastAPI endpoints
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute):
                        if isinstance(decorator.value, ast.Name):
                            method_call = f"{decorator.value.id}.{decorator.attr}"
                            func_info["decorators"].append(method_call)
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            if isinstance(decorator.func.value, ast.Name):
                                method_call = f"{decorator.func.value.id}.{decorator.func.attr}"
                                # Extract path from arguments
                                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                    path = decorator.args[0].value
                                    func_info["path"] = path
                                    func_info["decorators"].append(f"{method_call}('{path}')")
                                else:
                                    func_info["decorators"].append(method_call)
                
                functions.append(func_info)
                
                # If this is an API endpoint, add to endpoints
                for decorator in func_info["decorators"]:
                    if any(method in decorator for method in ["router.get", "router.post", "router.put", "router.delete", "router.patch"]):
                        endpoints.append(func_info)
                        break
        
        return {
            "file": file_path.name,
            "path": str(file_path),
            "imports": imports,
            "classes": classes,
            "functions": [f["name"] for f in functions],
            "endpoints": endpoints,
            "async_functions": [f["name"] for f in functions if f["is_async"]],
            "line_count": len(content.splitlines()),
            "char_count": len(content)
        }
        
    except Exception as e:
        return {
            "file": file_path.name,
            "path": str(file_path),
            "error": str(e),
            "imports": [],
            "classes": [],
            "functions": [],
            "endpoints": [],
            "async_functions": []
        }

def main():
    api_dir = Path("app/api")
    
    print("=== API Directory Debug Analysis ===\n")
    
    if not api_dir.exists():
        print("❌ API directory not found")
        return
    
    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(api_dir):
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                python_files.append(Path(root) / file)
    
    print(f"Found {len(python_files)} Python files in app/api\n")
    
    total_endpoints = 0
    all_results = []
    
    for file_path in sorted(python_files):
        result = analyze_python_file(file_path)
        all_results.append(result)
        
        print(f"📁 {result['file']} ({result.get('line_count', 0)} lines)")
        
        if result.get('error'):
            print(f"  ❌ Error: {result['error']}")
            continue
        
        if result['endpoints']:
            print(f"  🌐 API Endpoints ({len(result['endpoints'])})")
            total_endpoints += len(result['endpoints'])
            for endpoint in result['endpoints']:
                decorators = ', '.join(endpoint['decorators'])
                async_marker = " (async)" if endpoint['is_async'] else ""
                print(f"    - {endpoint['name']}{async_marker}")
                print(f"      {decorators}")
        
        if result['classes']:
            print(f"  📦 Classes: {', '.join(result['classes'])}")
        
        if result['functions']:
            async_count = len(result['async_functions'])
            sync_count = len(result['functions']) - async_count
            print(f"  ⚙️  Functions: {len(result['functions'])} total ({async_count} async, {sync_count} sync)")
        
        # Check for potential issues
        issues = []
        
        # Missing session dependency
        endpoint_names = [ep['name'] for ep in result['endpoints']]
        if endpoint_names and 'get_session' not in str(result['imports']):
            issues.append("Missing get_session import")
        
        # Check for error handling
        if endpoint_names and 'HTTPException' not in str(result['imports']):
            issues.append("Missing HTTPException import")
        
        if issues:
            print(f"  ⚠️  Potential Issues: {', '.join(issues)}")
        
        print()
    
    # Summary
    print("=== Summary ===")
    print(f"Total Python files analyzed: {len(all_results)}")
    print(f"Total API endpoints found: {total_endpoints}")
    print(f"Files with endpoints: {sum(1 for r in all_results if r.get('endpoints'))}")
    print(f"Files with errors: {sum(1 for r in all_results if r.get('error'))}")
    
    # Endpoint overview
    print("\n=== All Endpoints Overview ===")
    endpoint_summary = []
    for result in all_results:
        for endpoint in result.get('endpoints', []):
            for decorator in endpoint['decorators']:
                if any(method in decorator for method in ['get', 'post', 'put', 'delete', 'patch']):
                    method = None
                    path = "/"
                    
                    # Extract method
                    for m in ['get', 'post', 'put', 'delete', 'patch']:
                        if f"router.{m}" in decorator:
                            method = m.upper()
                            break
                    
                    # Extract path
                    if "(" in decorator and "'" in decorator:
                        path_start = decorator.find("'") + 1
                        path_end = decorator.find("'", path_start)
                        if path_end > path_start:
                            path = decorator[path_start:path_end]
                    
                    endpoint_summary.append({
                        'file': result['file'],
                        'method': method or 'UNKNOWN',
                        'path': path,
                        'function': endpoint['name']
                    })
    
    # Group by file
    for result in all_results:
        file_endpoints = [ep for ep in endpoint_summary if ep['file'] == result['file']]
        if file_endpoints:
            print(f"\n{result['file']}:")
            for ep in file_endpoints:
                print(f"  {ep['method']:6} {ep['path']} → {ep['function']}()")

if __name__ == '__main__':
    main()
