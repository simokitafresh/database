#!/usr/bin/env python3
"""
Test schema detection logic
"""

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# SQLiteでテスト環境を作成
engine = create_engine('sqlite:///:memory:', poolclass=StaticPool)

with engine.connect() as conn:
    # 既存のテーブルを模擬
    conn.execute(text('CREATE TABLE symbols (symbol VARCHAR PRIMARY KEY)'))
    conn.execute(text('CREATE TABLE prices (id INTEGER PRIMARY KEY)'))
    
    # スキーマチェックロジック
    essential_tables = ['symbols', 'prices', 'fetch_jobs']
    existing_tables = []
    
    for table in essential_tables:
        try:
            # SQLiteでは information_schema がないので、別の方法でチェック
            result = conn.execute(text(f'SELECT name FROM sqlite_master WHERE type="table" AND name="{table}"')).scalar()
            if result:
                existing_tables.append(table)
        except:
            pass
    
    should_stamp = len(existing_tables) >= 2
    
    print(f'Existing tables: {existing_tables}')
    print(f'Should stamp: {should_stamp}')
    
    if should_stamp:
        print('✅ Logic will choose STAMP (existing schema detected)')
    else:
        print('✅ Logic will choose UPGRADE (fresh deployment)')
