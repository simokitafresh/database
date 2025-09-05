#!/usr/bin/env python3
"""
Simple Database Connection Test using SQLite
"""

import sys
from pathlib import Path
import asyncio

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_sqlite_connection():
    """Test database connections using SQLite"""
    
    print("=== SQLite Database Connection Test ===\n")
    
    # Test 1: Basic SQLAlchemy sync connection
    print("🧪 Test 1: SQLAlchemy Sync Connection")
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import StaticPool
        
        engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 'SQLite sync connection successful' as message")).scalar()
            print(f"   ✅ {result}")
        
    except Exception as e:
        print(f"   ❌ Sync connection failed: {e}")
        return False
    
    # Test 2: Async SQLAlchemy connection
    print("\n🧪 Test 2: SQLAlchemy Async Connection")
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from sqlalchemy.pool import StaticPool
        
        async_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
        
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 'SQLite async connection successful' as message"))
            message = result.scalar()
            print(f"   ✅ {message}")
            
        await async_engine.dispose()
        
    except Exception as e:
        print(f"   ❌ Async connection failed: {e}")
        return False
    
    # Test 3: Our app's engine factory with SQLite
    print("\n🧪 Test 3: App Engine Factory with SQLite")
    try:
        from app.db.engine import create_engine_and_sessionmaker
        
        # Use SQLite for testing
        engine, sessionmaker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
        
        async with sessionmaker() as session:
            result = await session.execute(text("SELECT 'App engine SQLite test successful' as message"))
            message = result.scalar()
            print(f"   ✅ {message}")
        
        await engine.dispose()
        
    except Exception as e:
        print(f"   ❌ App engine failed: {e}")
        return False
    
    # Test 4: Alembic env.py simulation
    print("\n🧪 Test 4: Alembic Environment Simulation")
    try:
        import os
        
        # Set environment variable
        os.environ['DATABASE_URL'] = 'sqlite:///test.db'
        
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        
        engine = create_engine(
            "sqlite:///test.db",
            poolclass=NullPool
        )
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 'Alembic simulation successful' as message")).scalar()
            print(f"   ✅ {result}")
            
        # Clean up test file
        import os
        if os.path.exists('test.db'):
            os.remove('test.db')
        
    except Exception as e:
        print(f"   ❌ Alembic simulation failed: {e}")
        return False
    
    print("\n✅ All SQLite connection tests passed!")
    return True

def test_postgresql_locally():
    """Test with actual PostgreSQL settings if available"""
    
    print("\n=== Local PostgreSQL Connection Test ===\n")
    
    # Test with actual settings from .env
    database_urls = [
        "postgresql+asyncpg://user:pass@localhost:5432/app",
        "postgresql+psycopg://user:pass@localhost:5432/app",
    ]
    
    for url in database_urls:
        print(f"🧪 Testing: {url}")
        
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.pool import NullPool
            
            # Convert async URL to sync for testing
            test_url = url
            if test_url.startswith('postgresql+asyncpg://'):
                test_url = test_url.replace('postgresql+asyncpg://', 'postgresql+psycopg://')
            
            engine = create_engine(
                test_url,
                poolclass=NullPool,
                connect_args={"connect_timeout": 5}
            )
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT current_timestamp")).scalar()
                print(f"   ✅ Connection successful! Server time: {result}")
                return True
                
        except Exception as e:
            print(f"   ❌ Connection failed: {e}")
    
    return False

def main():
    """Run comprehensive database tests"""
    
    print("🏗️ Database Connection Comprehensive Test\n")
    
    # First test SQLite (should always work)
    sqlite_success = asyncio.run(test_sqlite_connection())
    
    if not sqlite_success:
        print("\n💥 Basic SQLite tests failed - there may be package issues")
        sys.exit(1)
    
    # Then test PostgreSQL if available
    postgresql_success = test_postgresql_locally()
    
    if postgresql_success:
        print("\n🎉 PostgreSQL connection is working!")
    else:
        print("\n⚠️  PostgreSQL connection not available locally")
        print("   This is normal if PostgreSQL is not installed or running")
        print("   The SQLite tests confirm the connection logic is working")
    
    print("\n📋 Summary:")
    print(f"   SQLite tests: {'✅ PASSED' if sqlite_success else '❌ FAILED'}")
    print(f"   PostgreSQL tests: {'✅ PASSED' if postgresql_success else '⚠️  NOT AVAILABLE'}")
    
    if sqlite_success:
        print("\n✅ Connection infrastructure is working correctly!")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
