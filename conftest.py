import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Map hyphen-named service dirs to underscored package names so pytest can
# import e.g. `risk_engine` from `services/risk-engine/`.
_PACKAGE_MAP = {
    "gateway": ROOT / "services" / "gateway",
    "risk_engine": ROOT / "services" / "risk-engine",
    "anomaly_service": ROOT / "services" / "anomaly-service",
    "telemetry_ingest": ROOT / "services" / "telemetry-ingest",
    "forensics": ROOT / "services" / "forensics",
}

for pkg_name, pkg_path in _PACKAGE_MAP.items():
    if not pkg_path.exists():
        continue
    parent = str(pkg_path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

# Allow `import gateway`, `import risk_engine`, etc. via symlink-like alias.
import importlib
import importlib.util

for pkg_name, pkg_path in _PACKAGE_MAP.items():
    if pkg_name in sys.modules or not pkg_path.exists():
        continue
    init_file = pkg_path / "__init__.py"
    if not init_file.exists():
        continue
    spec = importlib.util.spec_from_file_location(
        pkg_name, init_file, submodule_search_locations=[str(pkg_path)]
    )
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name] = module
        spec.loader.exec_module(module)
