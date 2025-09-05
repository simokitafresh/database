#!/usr/bin/env python3
"""
Check migration chain consistency
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from alembic.script import ScriptDirectory
    from alembic.config import Config
    
    # Mock database URL to avoid connection requirements
    os.environ['DATABASE_URL'] = 'postgresql://mock:mock@localhost/mock'
    
    config = Config('alembic.ini')
    script_dir = ScriptDirectory.from_config(config)
    
    # Get all revisions
    revisions = list(script_dir.walk_revisions())
    
    print("=== Migration Chain Analysis ===")
    print(f"Total revisions found: {len(revisions)}")
    print()
    
    # Display chain in order
    print("Chain (from base to head):")
    for rev in reversed(revisions):
        parent = rev.down_revision or "<base>"
        print(f"  {parent} -> {rev.revision}")
    print()
    
    # Check for consistency
    print("=== Consistency Check ===")
    revision_ids = {rev.revision for rev in revisions}
    
    errors = []
    for rev in revisions:
        if rev.down_revision and rev.down_revision not in revision_ids:
            errors.append(f"Revision {rev.revision} references unknown down_revision: {rev.down_revision}")
    
    if errors:
        print("❌ ERRORS FOUND:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("✅ All migrations are properly linked!")
        
    # Display revision details
    print("\n=== Revision Details ===")
    for rev in reversed(revisions):
        print(f"File: {Path(rev.path).name}")
        print(f"  Revision: {rev.revision}")
        print(f"  Down revision: {rev.down_revision}")
        print(f"  Doc: {rev.doc or 'No description'}")
        print()

except Exception as e:
    print(f"❌ Error checking migrations: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
