#!/usr/bin/env python3
"""
Database Connection Diagnostic Tool for Supabase
"""

import os
import sys
import time
from urllib.parse import urlparse
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_supabase_connection():
    """Test Supabase database connection with detailed diagnostics"""
    
    print("=== Supabase Connection Diagnostics ===\n")
    
    # Check environment variables
    database_url = os.getenv('DATABASE_URL') or os.getenv('ALEMBIC_DATABASE_URL')
    
    if not database_url:
        print("❌ No DATABASE_URL or ALEMBIC_DATABASE_URL found in environment")
        return False
    
    print(f"🔗 Database URL detected: {database_url[:50]}...")
    
    # Parse URL components
    parsed = urlparse(database_url)
    print(f"📊 Connection details:")
    print(f"   Host: {parsed.hostname}")
    print(f"   Port: {parsed.port}")
    print(f"   Database: {parsed.path[1:] if parsed.path.startswith('/') else parsed.path}")
    print(f"   SSL Mode: {'enabled' if 'sslmode=require' in database_url else 'disabled'}")
    print()
    
    # Test 1: Basic SQLAlchemy sync connection (for Alembic)
    print("🧪 Test 1: SQLAlchemy Sync Connection (Alembic-style)")
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        
        # Convert asyncpg to psycopg for Alembic
        sync_url = database_url
        if sync_url.startswith('postgresql+asyncpg://'):
            sync_url = sync_url.replace('postgresql+asyncpg://', 'postgresql+psycopg://', 1)
        
        engine = create_engine(
            sync_url,
            poolclass=NullPool,
            connect_args={
                "connect_timeout": 30,
                "application_name": "diagnostic-sync",
            }
        )
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()")).scalar()
            print(f"   ✅ Sync connection successful")
            print(f"   📋 PostgreSQL version: {result[:50]}...")
        
    except Exception as e:
        print(f"   ❌ Sync connection failed: {e}")
        return False
    
    # Test 2: Async SQLAlchemy connection (for app)
    print("\n🧪 Test 2: SQLAlchemy Async Connection (App-style)")
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from sqlalchemy.pool import NullPool
        
        async_engine = create_async_engine(
            database_url,
            poolclass=NullPool,
            connect_args={
                "command_timeout": 30,
                "server_settings": {
                    "application_name": "diagnostic-async"
                }
            }
        )
        
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT current_timestamp"))
            timestamp = result.scalar()
            print(f"   ✅ Async connection successful")
            print(f"   ⏰ Server time: {timestamp}")
            
        await async_engine.dispose()
        
    except Exception as e:
        print(f"   ❌ Async connection failed: {e}")
        return False
    
    # Test 3: Our app's engine factory
    print("\n🧪 Test 3: App Engine Factory")
    try:
        from app.db.engine import create_engine_and_sessionmaker
        
        engine, sessionmaker = create_engine_and_sessionmaker(database_url)
        
        async with sessionmaker() as session:
            result = await session.execute(text("SELECT 'App engine test successful' as message"))
            message = result.scalar()
            print(f"   ✅ App engine successful: {message}")
        
        await engine.dispose()
        
    except Exception as e:
        print(f"   ❌ App engine failed: {e}")
        return False
    
    print("\n✅ All connection tests passed!")
    return True

def main():
    """Run the diagnostic tests"""
    
    try:
        # Run async tests
        result = asyncio.run(test_supabase_connection())
        
        if result:
            print("\n🎉 Database connection is healthy!")
            sys.exit(0)
        else:
            print("\n💥 Database connection issues detected!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️  Diagnostic interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Diagnostic failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
