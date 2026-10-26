# claude-compact-statusline

A compact, boxed status line for [Claude Code](https://claude.com/claude-code). One
Python file, standard library only, no Nerd Font required.

```
╭─ Fable 5.1 ──────────────────────────────────────────────────── 05:03 ╮
│ █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░  37% 371k/1.0M sharp (^‿^) │
│ …/services/keep                                         master ~4 ?8 │
│ $23.16 · 4h41m                                               +296 -1 │
╰──────────────────────────────────────────────────────────────────────╯
```

Four rows: model and clock; context fill; directory and git state; cost,
session time and lines changed. Every row is laid out for a narrow phone
terminal first and only spreads out when there is room, so the same file
works in a 48-column Termux window and a wide desktop terminal.

## The scale

The context bar is labelled by how much headroom the model has left:

| Context used | Word     | Face    |
|-------------:|----------|---------|
| under 40%    | sharp    | `(^‿^)` |
| 40 to 60%    | coasting | `(•‿•)` |
| 60 to 75%    | foggy    | `(•_•)` |
| 75 to 90%    | cooked   | `(x_x)` |
| 90% and up   | dumb     | `(°﹃°)` |

The face is the first thing dropped when the row gets narrow, then the
word, then the token counts. The bar never shrinks below ten cells.

## Install

```sh
curl -fsSLo ~/.claude/statusline/compact.py \
  https://raw.githubusercontent.com/Aypex-agent/claude-compact-statusline/main/compact.py
```

Then point Claude Code at it in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline/compact.py",
    "padding": 0
  }
}
```

Needs `python3` and `git` on `PATH`. Git rows are skipped outside a repo.

## Tuning

All optional, set in the environment the status line command runs in
(for example by prefixing them in the `command` string above):

| Variable          | Default | Effect                                              |
|-------------------|--------:|-----------------------------------------------------|
| `PHONE_SL_WIDTH`  | auto    | Force the box width instead of detecting the tty    |
| `PHONE_SL_MAX`    | `120`   | Width cap; the original phone build used `72`       |
| `PHONE_SL_MARGIN` | `4`     | Columns left free for Claude Code's own indent      |
| `PHONE_SL_FACE`   | `1`     | `0` hides the face and keeps just the word          |

## Origin

Written as the status line for a Claude Code instance living in a proot
container on a phone, where every column counts. It turned out to be less
cluttered than the full-width alternatives on the desktop too, so it moved
there as well. The layout is inspired by
[yas](https://github.com/tmck-code/yet-another-statusline).

## License

MIT. See [LICENSE](LICENSE).
