#!/usr/bin/env python3
"""SessionStart hook of the compact-statusline plugin.

Plugins can't declare a statusLine, so this points the user's statusLine at the
plugin's own compact.py, and repoints it when an update moves the plugin to a new
folder. It only touches a statusLine that is unset or already runs a compact.py
(this status line, installed by hand or by an older version); any leading
VAR=value prefixes (e.g. PHONE_SL_FACE=0) are kept. Someone else's statusLine is
left alone, with a one-time note. Never fails the session: errors exit quietly.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
SETTINGS = CONFIG / "settings.json"
STATE = CONFIG / "compact-statusline"
OURS = re.compile(r"compact\.py")
PREFIX = re.compile(r"^((?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*)")


def say(msg):
    print(json.dumps({"systemMessage": msg}))


def main():
    if os.environ.get("COMPACT_STATUSLINE_MANAGE") == "0":
        return
    script = ROOT / "compact.py"
    if not script.is_file():
        return
    want = f'python3 "{script}"'
    try:
        data = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except (OSError, ValueError):
        return  # unreadable settings: never write over them
    if not isinstance(data, dict):
        return
    sl = data.get("statusLine")
    current = sl.get("command", "") if isinstance(sl, dict) else ""

    if current and not OURS.search(current):
        STATE.mkdir(parents=True, exist_ok=True)
        flag = STATE / "noted-foreign-statusline"
        if not flag.exists():
            flag.write_text(current)
            say("compact-statusline: you already have a statusLine of your own, so it was left as is. "
                f"To use this one, set statusLine.command to: {want}")
        return

    prefix = PREFIX.match(current).group(1) if current else ""
    command = f"{prefix}{want}"
    if current == command:
        return
    new_sl = dict(sl) if isinstance(sl, dict) else {}
    new_sl.update({"type": "command", "command": command})
    new_sl.setdefault("padding", 0)
    data["statusLine"] = new_sl

    STATE.mkdir(parents=True, exist_ok=True)
    backup = STATE / "settings.json.before-compact-statusline"
    if SETTINGS.exists() and not backup.exists():
        backup.write_text(SETTINGS.read_text())
    fd, tmp = tempfile.mkstemp(dir=SETTINGS.parent, prefix=".settings.", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, SETTINGS)
    say("compact-statusline: status line " + ("updated to this version." if current else "installed."))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - a status line must never break a session
        sys.exit(0)
