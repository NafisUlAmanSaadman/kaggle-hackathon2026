"""conftest.py – Adds the project root to sys.path so pytest can import agents,
schema, and security without needing an editable install.
"""
import sys
from pathlib import Path

# Insert the project root (parent of the tests/ directory) at the front of
# sys.path so that 'import agents', 'import schema', etc. all resolve correctly.
sys.path.insert(0, str(Path(__file__).parent.parent))
