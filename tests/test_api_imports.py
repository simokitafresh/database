#!/usr/bin/env python3
"""
API Import Chain Validation
"""

import sys
from pathlib import Path

def validate_api_imports():
    """Validate the API import chain"""
    
    print("=== API Import Chain Validation ===\n")
    
    # Test imports individually
    test_cases = [
        ("app.api.deps", "get_session"),
        ("app.api.errors", "HTTPException"),
        ("app.api.v1.router", "router"),
        ("app.api.v1.health", "router"),
        ("app.api.v1.symbols", "router"),
        ("app.api.v1.prices", "router"),
        ("app.api.v1.coverage", "router"),
        ("app.api.v1.fetch", "router"),
        ("app.main", "app")
    ]
    
    success_count = 0
    
    for module_name, item in test_cases:
        try:
            # Import the module
            module = __import__(module_name, fromlist=[item] if item else [])
            
            # Check if the item exists
            if hasattr(module, item):
                print(f"✅ {module_name}.{item}")
                success_count += 1
            else:
                print(f"❌ {module_name}.{item} (import succeeded but item not found)")
        
        except ImportError as e:
            print(f"❌ {module_name}.{item} (ImportError: {e})")
        except Exception as e:
            print(f"❌ {module_name}.{item} (Error: {e})")
    
    print(f"\nImport Success Rate: {success_count}/{len(test_cases)} ({success_count/len(test_cases)*100:.1f}%)")
    
    # Test the full application startup
    print("\n=== Full Application Import Test ===")
    
    try:
        from app.main import app
        print("✅ Main application imported successfully")
        
        # Check routes
        if hasattr(app, 'routes'):
            route_count = len(app.routes)
            print(f"✅ Application has {route_count} routes registered")
            
            # List some routes
            print("🛣️  Sample Routes:")
            for i, route in enumerate(app.routes[:10]):  # Show first 10
                if hasattr(route, 'path') and hasattr(route, 'methods'):
                    methods = list(route.methods) if hasattr(route.methods, '__iter__') else []
                    print(f"  {', '.join(methods):15} {route.path}")
            
            if len(app.routes) > 10:
                print(f"  ... and {len(app.routes) - 10} more routes")
        
    except Exception as e:
        print(f"❌ Failed to import main application: {e}")
        import traceback
        traceback.print_exc()
    
    # Check specific API endpoints are accessible
    print("\n=== API Router Integration Test ===")
    
    try:
        from app.api.v1.router import router as v1_router
        
        if hasattr(v1_router, 'routes'):
            v1_routes = len(v1_router.routes)
            print(f"✅ v1 router has {v1_routes} routes")
        
        # Test individual routers
        routers_to_test = [
            ("health", "app.api.v1.health"),
            ("symbols", "app.api.v1.symbols"),
            ("prices", "app.api.v1.prices"),
            ("coverage", "app.api.v1.coverage"),
            ("fetch", "app.api.v1.fetch")
        ]
        
        for name, module_path in routers_to_test:
            try:
                module = __import__(module_path, fromlist=['router'])
                if hasattr(module, 'router'):
                    if hasattr(module.router, 'routes'):
                        route_count = len(module.router.routes)
                        print(f"  ✅ {name} router: {route_count} routes")
                    else:
                        print(f"  ✅ {name} router imported (no routes counted)")
                else:
                    print(f"  ❌ {name} router: no 'router' attribute")
            except Exception as e:
                print(f"  ❌ {name} router: {e}")
    
    except Exception as e:
        print(f"❌ Failed to test v1 router: {e}")

if __name__ == '__main__':
    # Add current directory to Python path
    sys.path.insert(0, str(Path.cwd()))
    validate_api_imports()
