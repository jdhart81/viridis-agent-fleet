"""Keep the subscriptions package isolated when collected from fleet root."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for module_name in [name for name in list(sys.modules)
                    if name == "src" or name.startswith("src.")]:
    del sys.modules[module_name]
