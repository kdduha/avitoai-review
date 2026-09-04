import sys
from pathlib import Path

# Фабрики моделей лежат рядом с тестами.
sys.path.insert(0, str(Path(__file__).parent))
