"""Script Manager dev proxy for import_gemcad_asc.py.

Paste this once into Cinema 4D's Script Manager and run *it* during
development instead of the real script. It re-reads SCRIPT_PATH from disk
and executes main() on every run, so edits made in an external editor take
effect immediately -- no re-copy/paste into C4D, and no stale .pyc from
C4D's own script cache.
"""

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(r"c:\Users\liza.desya\Documents\GitHub\lizatendril\Gem-Designer-Script\C4D-script\import_gemcad_asc.py")


def main():
    spec = importlib.util.spec_from_file_location("import_gemcad_asc", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.main()


if __name__ == "__main__":
    main()
