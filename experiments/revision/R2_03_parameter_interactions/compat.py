"""Namespace compatibility for the original experiment.zip task generator."""
import sys
import types
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor"

def setup():
    for name, path in [("SRTP", VENDOR.parent), ("SRTP.experiment", VENDOR)]:
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]
            sys.modules[name] = module
setup()
