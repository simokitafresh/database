#!/usr/bin/env python3
"""
Analyze migration file contents for potential issues
"""

import ast
import os
import sys
from pathlib import Path

def analyze_migration_file(file_path):
    """Analyze a single migration file for issues"""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse AST
        tree = ast.parse(content)
        
        # Find revision and down_revision assignments
        revision = None
        down_revision = None
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == 'revision':
                            if isinstance(node.value, ast.Constant):
                                revision = node.value.value
                        elif target.id == 'down_revision':
                            if isinstance(node.value, ast.Constant):
                                down_revision = node.value.value
        
        if revision is None:
            issues.append("No revision ID found")
        
        # Check for upgrade function
        has_upgrade = False
        has_downgrade = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == 'upgrade':
                    has_upgrade = True
                elif node.name == 'downgrade':
                    has_downgrade = True
        
        if not has_upgrade:
            issues.append("No upgrade() function found")
        
        return {
            'file': file_path.name,
            'revision': revision,
            'down_revision': down_revision,
            'has_upgrade': has_upgrade,
            'has_downgrade': has_downgrade,
            'issues': issues
        }
        
    except Exception as e:
        return {
            'file': file_path.name,
            'error': str(e),
            'issues': [f"Failed to parse file: {e}"]
        }

def main():
    migrations_dir = Path('app/migrations/versions')
    
    if not migrations_dir.exists():
        print("❌ Migrations directory not found")
        return
    
    print("=== Migration File Content Analysis ===\n")
    
    migration_files = sorted(migrations_dir.glob('*.py'))
    all_results = []
    
    for file_path in migration_files:
        result = analyze_migration_file(file_path)
        all_results.append(result)
        
        print(f"File: {result['file']}")
        if 'error' in result:
            print(f"  ❌ Error: {result['error']}")
        else:
            print(f"  Revision: {result['revision']}")
            print(f"  Down revision: {result['down_revision']}")
            print(f"  Has upgrade(): {result['has_upgrade']}")
            print(f"  Has downgrade(): {result['has_downgrade']}")
        
        if result['issues']:
            print(f"  ❌ Issues:")
            for issue in result['issues']:
                print(f"    - {issue}")
        else:
            print(f"  ✅ No issues found")
        print()
    
    # Check revision chain
    print("=== Chain Validation ===")
    revision_map = {r['revision']: r for r in all_results if 'revision' in r}
    
    chain_issues = []
    for result in all_results:
        if 'revision' not in result:
            continue
        
        down_rev = result['down_revision']
        if down_rev is not None and down_rev not in revision_map:
            chain_issues.append(f"Revision {result['revision']} references unknown down_revision: {down_rev}")
    
    if chain_issues:
        print("❌ Chain issues found:")
        for issue in chain_issues:
            print(f"  - {issue}")
    else:
        print("✅ Migration chain is valid")

if __name__ == '__main__':
    main()
