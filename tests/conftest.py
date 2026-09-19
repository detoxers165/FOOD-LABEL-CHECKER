import sys
from pathlib import Path

# Tests live in tests/, but the engine/adapter modules live at repo root.
# Make sure repo root is importable regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))
