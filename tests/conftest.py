"""The decision core runs without Home Assistant."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))

# 0.78.x / hcd: the core also as `hc_core` (as the hc-core package installs it) and the hcd package on the path,
# so the standalone service's tests run here too without installing anything.
import importlib.util as _ilu

_CORE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat" / "core"
if "hc_core" not in sys.modules:
    _spec = _ilu.spec_from_file_location("hc_core", _CORE / "__init__.py", submodule_search_locations=[str(_CORE)])
    _mod = _ilu.module_from_spec(_spec)
    sys.modules["hc_core"] = _mod
    _spec.loader.exec_module(_mod)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hcd"))
