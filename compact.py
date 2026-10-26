#!/usr/bin/env python3
"""Compact boxed statusline for Claude Code.

Inspired by yas (tmck-code/yet-another-statusline), but every row is laid
out to fit a narrow phone screen first and only spreads out when there is
room. Uses plain Unicode glyphs that JetBrains Mono ships (no Nerd Font).

Width: $PHONE_SL_WIDTH, else $COLUMNS, else the controlling tty, else 48;
capped at $PHONE_SL_MAX (default 120; the original phone build used 72).
$PHONE_SL_MARGIN (default 4) leaves room for Claude Code's indent.
$PHONE_SL_FACE=0 hides the face next to the context band word.

Born as the phone-terminal statusline of a Claude Code instance running
in a proot container; promoted to the desktop once it proved less
cluttered than the full-width alternatives.
"""
import json
import os
import subprocess
import sys
import time
import unicodedata

# ── palette (matches the cyan starship prompt) ──────────────────────────
RST = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
BCYAN = "\033[1;36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAG = "\033[35m"
GREY = "\033[90m"

# context bands: (upper %, colour, word, face)
# The face gets progressively less intelligent as the context fills,
# ending in a drool. It sits after the word and is the first thing
# dropped when the row is too narrow.
BANDS = [(40, GREEN, "sharp", "(^‿^)"), (60, CYAN, "coasting", "(•‿•)"),
         (75, YELLOW, "foggy", "(•_•)"), (90, RED, "cooked", "(x_x)"),
         (101, MAG, "dumb", "(°﹃°)")]


def term_width():
    for var in ("PHONE_SL_WIDTH", "COLUMNS"):
        v = os.environ.get(var, "")
        if v.isdigit() and int(v) > 0:
            return int(v)
    try:
        with open("/dev/tty") as tty:
            return os.get_terminal_size(tty.fileno()).columns
    except OSError:
        pass
    return 48


def vis_len(s):
    """Display width of s, ignoring ANSI escapes."""
    n, esc = 0, False
    for ch in s:
        if esc:
            esc = ch != "m"
        elif ch == "\033":
            esc = True
        elif not unicodedata.combining(ch):
            n += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
    return n


def clip(s, width):
    """Cut s to width display columns, ending in … if cut."""
    if vis_len(s) <= width:
        return s
    out, n, esc = "", 0, False
    for ch in s:
        if esc:
            out += ch
            esc = ch != "m"
            continue
        if ch == "\033":
            out += ch
            esc = True
            continue
        if n + 1 > width - 1:
            break
        out += ch
        n += 1
    return out + "…" + RST


def fit(parts, width, sep=" "):
    """Join parts left to right, dropping from the end until they fit."""
    parts = [p for p in parts if p]
    while len(parts) > 1 and vis_len(sep.join(parts)) > width:
        parts.pop()
    return clip(sep.join(parts), width)


def spread(left, right, width):
    """left … right on one line; right is dropped if it won't fit."""
    gap = width - vis_len(left) - vis_len(right)
    if right and gap >= 1:
        return left + " " * gap + right
    return clip(left, width)


def human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)


def short_dir(path, keep=2):
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        path = "~" + path[len(home):]
    parts = [p for p in path.split("/") if p]
    if len(parts) <= keep:
        return path
    return "…/" + "/".join(parts[-keep:])


def git_info(cwd):
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v1", "--branch"],
            capture_output=True, text=True, timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    lines = out.stdout.splitlines()
    head = lines[0][3:] if lines else ""
    branch = head.split("...")[0].replace("No commits yet on ", "")
    ahead = behind = 0
    if "[" in head:
        for tok in head[head.index("[") + 1:-1].split(", "):
            k, _, v = tok.partition(" ")
            if k == "ahead":
                ahead = int(v)
            elif k == "behind":
                behind = int(v)
    mod = sum(1 for ln in lines[1:] if ln[:2] != "??")
    new = sum(1 for ln in lines[1:] if ln[:2] == "??")
    return branch, mod, new, ahead, behind


def context_from_transcript(path):
    """Fallback: last assistant usage in the transcript."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 200_000))
            tail = f.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return None
    for line in reversed(tail):
        try:
            u = json.loads(line)["message"]["usage"]
        except (ValueError, KeyError, TypeError):
            continue
        return (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                + u.get("cache_creation_input_tokens", 0))
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}

    # Claude Code indents the statusline, so leave room on the right
    margin = int(os.environ.get("PHONE_SL_MARGIN", "4"))
    cap = int(os.environ.get("PHONE_SL_MAX", "120"))
    W = max(24, min(term_width() - margin, cap))
    inner = W - 4  # "│ " + text + " │"

    model = (data.get("model") or {}).get("display_name", "Claude")
    ws = data.get("workspace") or {}
    cwd = ws.get("current_dir") or data.get("cwd") or os.getcwd()
    cost = data.get("cost") or {}
    cw = data.get("context_window") or {}

    # ── context ────────────────────────────────────────────────────────
    size = cw.get("context_window_size") or 200_000
    pct = cw.get("used_percentage")
    used = None
    cu = cw.get("current_usage")
    if isinstance(cu, dict):
        used = (cu.get("input_tokens", 0) + cu.get("cache_read_input_tokens", 0)
                + cu.get("cache_creation_input_tokens", 0))
    if used is None and data.get("transcript_path"):
        used = context_from_transcript(data["transcript_path"])
    if pct is None and used is not None:
        pct = used * 100 / size
    pct = max(0, min(100, round(pct or 0)))
    colour, word, face = next((c, w, f) for lim, c, w, f in BANDS if pct < lim)
    if os.environ.get("PHONE_SL_FACE", "1") == "0":
        face = ""

    # ── row 1: top border with model and clock ─────────────────────────
    title = f" {BCYAN}{model}{RST}{GREY} "
    clock = f" {time.strftime('%H:%M')} "
    fill = W - 2 - vis_len(title) - len(clock) - 1
    if fill >= 1:
        top = f"{GREY}╭─{title}{'─' * fill}{clock}╮{RST}"
    else:
        title = clip(title, W - 4)
        top = f"{GREY}╭─{title}{GREY}{'─' * max(0, W - 3 - vis_len(title))}╮{RST}"

    # ── row 2: context bar ─────────────────────────────────────────────
    stats = f"{colour}{pct:>3}%{RST}"
    tail = f" {GREY}{human(used)}/{human(size)}{RST}" if used is not None else ""
    label = f" {colour}{word}{RST}"
    mug = f" {colour}{face}{RST}" if face else ""
    bar_w = inner - vis_len(stats) - 1
    # give the bar at least 10 cells; extras drop first: face, word, counts
    for extra in (tail + label + mug, tail + label, tail, ""):
        if inner - vis_len(stats + extra) - 1 >= 10:
            bar_w = inner - vis_len(stats + extra) - 1
            stats += extra
            break
    bar_w = max(4, bar_w)
    filled = round(bar_w * pct / 100)
    bar = f"{colour}{'█' * filled}{GREY}{'░' * (bar_w - filled)}{RST}"
    ctx_row = f"{bar} {stats}"

    # ── row 3: directory and git ───────────────────────────────────────
    g = git_info(cwd)
    git = ""
    if g:
        branch, mod, new, ahead, behind = g
        bits = [f"{CYAN}\033[3m{branch}{RST}"]
        if ahead:
            bits.append(f"{GREEN}⇡{ahead}{RST}")
        if behind:
            bits.append(f"{RED}⇣{behind}{RST}")
        if mod:
            bits.append(f"{YELLOW}~{mod}{RST}")
        if new:
            bits.append(f"{GREY}?{new}{RST}")
        git = " ".join(bits)
    d = f"{BCYAN}{short_dir(cwd)}{RST}"
    if git and vis_len(d) + 1 + vis_len(git) <= inner:
        loc_row = spread(d, git, inner)
    elif git:
        # too narrow for both: shorten the path harder, then cut the branch
        d = clip(f"{BCYAN}{short_dir(cwd, keep=1)}{RST}", inner // 2)
        loc_row = spread(d, clip(git, inner - vis_len(d) - 1), inner)
    else:
        loc_row = clip(d, inner)

    # ── row 4: cost, time, lines ───────────────────────────────────────
    usd = cost.get("total_cost_usd")
    mins = (cost.get("total_duration_ms") or 0) // 60000
    added = cost.get("total_lines_added") or 0
    removed = cost.get("total_lines_removed") or 0
    dur = f"{mins // 60}h{mins % 60:02d}m" if mins >= 60 else f"{mins}m"
    left = fit([
        f"{GREEN}${usd:.2f}{RST}" if usd is not None else "",
        f"{GREY}{dur}{RST}",
    ], inner, f" {GREY}·{RST} ")
    right = f"{GREEN}+{added}{RST} {RED}-{removed}{RST}" if added or removed else ""
    use_row = spread(left, right, inner)

    def row(s):
        pad = inner - vis_len(s)
        return f"{GREY}│{RST} {s}{' ' * max(0, pad)} {GREY}│{RST}"

    lines = [top, row(ctx_row), row(loc_row), row(use_row),
             f"{GREY}╰{'─' * (W - 2)}╯{RST}"]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
