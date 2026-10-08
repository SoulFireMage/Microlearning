import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_cmd_execs_uvicorn():
    """A shell-wrapped CMD must `exec` the server, or a stop signal hits only
    the shell and the orphaned server keeps the port (HF Dev Mode restarts)."""
    for name in ("Dockerfile", "space/Dockerfile"):
        cmd = [l for l in (ROOT / name).read_text().splitlines() if l.startswith("CMD")][0]
        if '"sh", "-c"' in cmd:
            assert re.search(r'"exec uvicorn', cmd), f"{name}: {cmd}"
