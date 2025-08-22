# Import built-in platform functions to avoid shadowing issues.
import importlib
_builtin_platform = importlib.import_module("platform")
for attr in ["python_implementation", "version", "platform", "system", "machine", "processor", "architecture"]:
    if attr not in globals():
        try:
            globals()[attr] = getattr(_builtin_platform, attr)
        except Exception:
            pass
