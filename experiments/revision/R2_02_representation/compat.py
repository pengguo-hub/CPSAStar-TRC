"""Only namespace compatibility for byte-identical upstream offline dependencies."""
import sys
import types
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor"

def setup():
    # task_generator and Astar_base contain old absolute SRTP.experiment imports.
    for name, path in [("SRTP", VENDOR.parent), ("SRTP.experiment", VENDOR)]:
        if name in sys.modules:
            existing = list(getattr(sys.modules[name], "__path__", []))
            if str(path) not in existing:
                raise RuntimeError(f"Namespace {name} is already loaded from another project; use a fresh Python process.")
        else:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]
            sys.modules[name] = module

setup()
