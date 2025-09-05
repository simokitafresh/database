#!/usr/bin/env python3
"""
Final migration validation test - simulates production deployment
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_migration_chain():
    """Test migration chain like production deployment would"""
    
    print("=== Production Migration Chain Test ===\n")
    
    # Simulate production PostgreSQL URL
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://postgres:password@localhost:5432/production'
    
    try:
        from alembic.script import ScriptDirectory
        from alembic.config import Config
        
        config = Config('alembic.ini')
        script_dir = ScriptDirectory.from_config(config)
        
        # Test the specific error condition from production
        print("1. Testing revision resolution...")
        
        # This was the failing call in production
        try:
            # Simulate the command: alembic upgrade head
            script_dir.get_revisions('head')
            print("   ✅ HEAD revision resolved successfully")
        except KeyError as e:
            print(f"   ❌ KeyError (production error): {e}")
            return False
        except Exception as e:
            print(f"   ❌ Other error: {e}")
            return False
        
        # Test specific revision that was failing
        print("2. Testing revision '003' resolution...")
        try:
            rev_003 = script_dir.get_revision('003')
            print(f"   ✅ Revision 003 found: {rev_003.revision}")
        except Exception as e:
            print(f"   ❌ Failed to find revision 003: {e}")
            return False
        
        # Test the full chain walk
        print("3. Testing full chain traversal...")
        try:
            revisions = list(script_dir.walk_revisions())
            print(f"   ✅ Full chain traversed: {len(revisions)} revisions")
            
            # Verify the chain that was failing
            chain = []
            for rev in reversed(revisions):
                chain.append(rev.revision)
            
            expected_chain = ['001', '002', '003', '004', '005', '006']
            if chain == expected_chain:
                print(f"   ✅ Chain matches expected: {' -> '.join(chain)}")
            else:
                print(f"   ❌ Chain mismatch. Expected: {expected_chain}, Got: {chain}")
                return False
                
        except Exception as e:
            print(f"   ❌ Chain traversal failed: {e}")
            return False
        
        # Test revision parsing (the specific line that was failing)
        print("4. Testing revision map building...")
        try:
            revision_map = script_dir.revision_map
            print(f"   ✅ Revision map built successfully")
            
            # Check the specific revision that was missing using get_revision
            try:
                rev_003_from_map = script_dir.get_revision('003')
                if rev_003_from_map.revision == '003':
                    print("   ✅ Revision '003' accessible through revision map")
                else:
                    print("   ❌ Revision '003' mismatch in map")
                    return False
            except Exception as e:
                print(f"   ❌ Revision '003' not accessible: {e}")
                return False
                
        except Exception as e:
            print(f"   ❌ Revision map building failed: {e}")
            return False
        
        print("\n✅ ALL TESTS PASSED - Migration chain is ready for production!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error (missing alembic?): {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    success = test_migration_chain()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
