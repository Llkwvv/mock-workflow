"""Sample module: auto-discover all readers on import."""

import importlib
import pkgutil

from backend.sample import readers

# Auto-import every module under backend.sample.readers so that
# @register_reader decorators fire and populate the registry.
for _, module_name, _ in pkgutil.iter_modules(readers.__path__):
    importlib.import_module(f"{readers.__name__}.{module_name}")
