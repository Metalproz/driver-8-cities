"""C17 drowning band in Rio (rio2: D2's sea tiles on the former 'void' coast): havana_water at Polish's drive-in spot
D1 (370500, 21000), heading +x (CITY=rio, SPOTS overridable)."""
import os
os.environ.setdefault("CITY", "rio")
os.environ.setdefault("SPOTS", "370500,21000,1024")
import importlib.util as _iu
_sp = _iu.spec_from_file_location("hw_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "havana_water.py"))
_hw = _iu.module_from_spec(_sp); _sp.loader.exec_module(_hw)
SESSION = _hw.SESSION
run = _hw.run
