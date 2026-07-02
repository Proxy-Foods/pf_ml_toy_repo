import sys
from pathlib import Path

# Make the repo root importable so `from src.recipe_utils import ...` works
# no matter which directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent))
