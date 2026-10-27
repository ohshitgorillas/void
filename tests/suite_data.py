"""The suite's own Void data folder: no test writes Void's real one (~/.local/share/void).

app/server.py settles its data folder (DATA_DIR, and MEM_PATH, ... under it) from the environment once, as
it is imported, so every test module that imports it, or that resolves the data folder itself, imports this module
first. On its first import, once per process, this points the environment's data folder (XDG_DATA_HOME; LOCALAPPDATA
on Windows) at a throwaway folder, removed at exit; processes the tests start inherit it.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

WIN = os.name == "nt"
_ENV = "LOCALAPPDATA" if WIN else "XDG_DATA_HOME"


def _data_dir() -> Path:
    """Void's data folder as app/server.py resolves it from the environment now."""
    if WIN:
        return Path(os.environ.get(_ENV) or Path.home() / "AppData" / "Local") / "void"
    return Path(os.environ.get(_ENV) or Path.home() / ".local/share") / "void"


_HOME = Path(tempfile.mkdtemp(prefix="void-suite-data-"))
atexit.register(shutil.rmtree, _HOME, True)
os.environ[_ENV] = str(_HOME)
DATA_DIR = _data_dir()                                 # the suite's data folder, where server.DATA_DIR now resolves
