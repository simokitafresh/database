#!/usr/bin/env python3
"""
Dry-run migration validation - parses SQL without executing
"""

import os
import sys
from pathlib import Path
import re

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def extract_sql_operations(file_path):
    """Extract SQL operations from migration file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find op.execute() calls
    sql_operations = []
    
    # Look for op.execute patterns
    execute_patterns = [
        r'op\.execute\(\s*"""(.*?)"""\s*\)',
        r'op\.execute\(\s*"([^"]+)"\s*\)',
        r'op\.execute\(\s*\'([^\']+)\'\s*\)'
    ]
    
    for pattern in execute_patterns:
        matches = re.finditer(pattern, content, re.DOTALL)
        for match in matches:
            sql_operations.append(match.group(1).strip())
    
    # Look for table operations
    table_ops = []
    table_patterns = [
        r'op\.create_table\s*\(\s*[\'"]([^\'"]+)[\'"]',
        r'op\.drop_table\s*\(\s*[\'"]([^\'"]+)[\'"]',
        r'op\.create_index\s*\(',
        r'op\.drop_index\s*\(',
        r'op\.add_column\s*\(',
        r'op\.drop_column\s*\('
    ]
    
    for pattern in table_patterns:
        matches = re.finditer(pattern, content)
        for match in matches:
            table_ops.append(match.group(0))
    
    return sql_operations, table_ops

def check_postgresql_compatibility(sql_content):
    """Check if SQL is PostgreSQL compatible"""
    issues = []
    
    # PostgreSQL specific features
    pg_features = [
        ('CREATE OR REPLACE FUNCTION', 'PostgreSQL function syntax'),
        ('RETURNS TABLE', 'PostgreSQL function returns'),
        ('LANGUAGE sql', 'PostgreSQL function language'),
        ('$$', 'PostgreSQL dollar quoting'),
        ('timestamptz', 'PostgreSQL timestamp with timezone'),
        ('double precision', 'PostgreSQL double precision type'),
        ('bigint', 'PostgreSQL bigint type'),
        ('ARRAY', 'PostgreSQL array type'),
        ('::text', 'PostgreSQL type casting')
    ]
    
    for feature, description in pg_features:
        if feature in sql_content:
            issues.append(f"Uses {description}: {feature}")
    
    return issues

def main():
    migrations_dir = Path('app/migrations/versions')
    
    print("=== Migration SQL Analysis ===\n")
    
    for file_path in sorted(migrations_dir.glob('*.py')):
        print(f"File: {file_path.name}")
        
        try:
            sql_ops, table_ops = extract_sql_operations(file_path)
            
            if sql_ops:
                print(f"  Raw SQL operations: {len(sql_ops)}")
                for i, sql in enumerate(sql_ops[:2], 1):  # Show first 2
                    print(f"    SQL {i} (first 100 chars): {sql[:100]}...")
                    
                    # Check PostgreSQL compatibility
                    pg_issues = check_postgresql_compatibility(sql)
                    if pg_issues:
                        print(f"      PostgreSQL-specific features:")
                        for issue in pg_issues[:3]:  # Show first 3
                            print(f"        - {issue}")
            
            if table_ops:
                print(f"  Table operations: {len(table_ops)}")
                for op in table_ops[:3]:  # Show first 3
                    print(f"    - {op[:80]}...")
            
            if not sql_ops and not table_ops:
                print("  ⚠️  No operations detected")
                
        except Exception as e:
            print(f"  ❌ Error analyzing file: {e}")
        
        print()

if __name__ == '__main__':
    main()
