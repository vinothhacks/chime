# CHIME — Screen Recording Narration Script

Use this while you record. You speak; the screen shows the steps.
Estimated total: 8–12 minutes. Pause wherever you want to go deeper.

Suggested layout: terminal on the left (or full screen), editor with this file on the right if you need a teleprompter.

Data isolation for the demo (so you do not touch a real store):

```powershell
$env:CHIME_DATA_DIR = "$PWD\demo-data"
$env:CHIME_TIMEZONE = "Asia/Kolkata"
```

---

## Scene 1 — What it is (0:00–0:45)

**On screen:** `docs/CHIME-REFINED-DESIGN.md`, scroll the product boundary.

**Say:**

> This is Chime, a terminal-native alarm clock for Windows, macOS, and Linux.
> It is CLI and TUI only. There is no web UI, no React, and no database.
> Alarms live in a small JSON file. The important limitation for version one:
> the app has to be running to ring. That is intentional. OS scheduler
> integration is a different product.

---

## Scene 2 — The hard problem (0:45–2:00)

**On screen:** the occurrence-key section in the design doc, then `src/chime/scheduler.py`.

**Say:**

> The easy version of an alarm clock stores last-fired and hopes for the best.
> That breaks on crash, restart, and clock jumps — you either ring twice or
> miss the alarm. Chime treats the schedule as a definition, not as runtime
> state. Each due moment gets a deterministic occurrence key: alarm id, local
> date, local time, and DST fold. We claim that key, persist it, and only then
> open the ringing screen. If persist fails, we do not ring. Spring-forward
> times that do not exist are skipped. Fall-back times that happen twice fire
> once.

---

## Scene 3 — Install and CLI happy path (2:00–3:30)

**On screen:** project root. Run:

```powershell
uv run chime --help
uv run chime add 07:30 --once -l Gym
uv run chime add 08:15 --days sat,sun -l Weekend
uv run chime add 22:00 --days weekdays -l Wind down
uv run chime list
uv run chime list --json
```

**Say:**

> Packaging is uv. The same application services back both the CLI and the TUI,
> so add in the CLI is the same validation and the same JSON as add in the TUI.
> List has a human table and a JSON mode. JSON goes only to stdout, so scripts
> can parse it. Ids are short, eight hex characters, so delete and toggle are
> easy to type.

---

## Scene 4 — TUI tour (3:30–5:30)

**On screen:**

```powershell
uv run chime
```

Walk: big clock, next-alarm line, list with ON/OFF text, footer keys.
Press `?` for help, `a` for add (cancel), `q` to quit.

**Say:**

> Bare chime opens the Textual UI. Time is the dominant element. Enabled state
> is the word ON or OFF, not color alone. Keyboard shortcuts stay on the
> footer, and the help screen is generated from the same bindings so it cannot
> drift. This is a terminal app, not a website in a terminal.

---

## Scene 5 — Ring, snooze, dismiss (5:30–7:30)

**On screen:** add an alarm a minute ahead, or use test-sound plus a near-term once alarm.

```powershell
uv run chime add  (use a time ~1 minute from now) --once -l Demo ring
uv run chime
```

When it rings: point at claim-before-ring in the status, press `S` once, then `D`.

Also:

```powershell
uv run chime test-sound
```

**Say:**

> When an occurrence is due inside the five-minute grace window, Chime persists
> the claim first, then shows the ringing screen and tries to play the bundled
> beep. Audio is best-effort — if the player is missing we fall back, and the
> visual ring still counts. Snooze is a runtime reminder, not a new alarm.
> Dismiss on a one-shot alarm disables it. If I quit while it is ringing,
> version one treats that as dismiss after confirm, so the same occurrence
> does not come back on the next launch.

---

## Scene 6 — Safety and diagnostics (7:30–9:00)

**On screen:**

```powershell
uv run chime doctor
uv run pytest -q
```

Open `.github/workflows/ci.yml` and `README.md` screenshots.

**Say:**

> Doctor reports Python, OS, data directory, lock, JSON health, timezone, and
> which audio backend was detected. It does not dump secrets or the whole
> environment. Tests inject a fake clock — we never sleep on the real wall
> clock. CI runs on Windows, macOS, and Linux. The README states the
> running-app limitation and shows real screenshots of the TUI.

---

## Scene 7 — Close (9:00–9:30)

**On screen:** GitHub repo `vinothhacks/chime`.

**Say:**

> That is Chime v1: deterministic time, explicit DST, durable occurrence
> identity, atomic JSON, a single writer lock, and one application layer
> shared by CLI and TUI. Small on purpose. Reliable on purpose.

---

## Optional B-roll if you have extra time

- Edit an alarm in the TUI (`e`), toggle with Space, delete with `d`.
- `chime off <id>` then `chime list`.
- Narrow the terminal to show the compact layout.
- Open `alarms.json` in the demo-data dir and show `schema_version` and `claimed_occurrences`.

## Recording tips

- Use a high-contrast terminal theme; Tokyo Night matches the app.
- Font size ≥ 16 so the big clock reads on video.
- Do not record a personal home path; the demo `CHIME_DATA_DIR` keeps the store in-tree.
- If an alarm does not fire, check the clock and timezone with `chime doctor`.
- Cut dead air; keep Scene 2. That is the architectural point of the video.
