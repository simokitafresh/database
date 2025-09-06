"""Test configuration for the project.

This file ensures that the application package is importable when the
test suite is executed without installing the project as a package.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path so ``import app`` works from tests
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
