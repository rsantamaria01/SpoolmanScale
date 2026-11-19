# AGENTS.md (fork-only: rsantamaria01/SpoolmanScale)

Raul's fork of Niko11111/SpoolmanScale (GPL-3.0), ESP32-S3 filament scale firmware (PlatformIO, Arduino core 3.3.12 on ESP-IDF 5.5, NimBLE, LVGL). The fork exists to add Brady BLE label printers (M211 first, M511 later) in a way that can go upstream as a pull request.

This file, the `esp32-brady-test` env and anything under `fork/` are fork-only. They never go into an upstream PR.

## Current mode
- Integration branch: `brady-m211` on `origin` (rsantamaria01/SpoolmanScale). Job branches come off it.
- Push gate: push your job branch to `origin` and open a PR into `brady-m211`. Raul merges. Never push to `brady-m211` or `main` directly.
- The only remote is `origin` (the fork). Niko11111/SpoolmanScale is deliberately not configured as a remote: never add it, push to it, or open PRs or issues there. After hardware testing, Raul opens the upstream PR himself from the fork.
- Upstream's `.gitignore` ignores everything except a whitelist (`src/`, `test/`, `scripts/`, `tools/`, `platformio.ini` ...). Commit fork-only paths such as `fork/` with `git add -f`; never edit `.gitignore` for them. Check `git status --ignored` before every commit so no new file is silently left out.
- CI: upstream workflows may run on the fork; they must stay green for `wt32-sc01-plus`.

## Upstream-friendly rules
- Read the existing printer drivers before writing one: `src/services/label_printer.{h,cpp}`, `niimbot.{h,cpp}`, `phomemo_m_series.{h,cpp}`, `ble_service.{h,cpp}`, `label_raster.h`. Match their structure, naming and comment style (a header block that says what the file is and where the protocol facts come from; comments explain why).
- Brady code lives in `src/services/brady.{h,cpp}` and reuses `ble_service` for transport.
- `LabelPrinterModel` and `LabelPrinterProtocol` values are NVS content: append new values at the end, never renumber or reuse.
- Protocol sources: JonBons/hacs-brady `specs/brady_m211_bluetooth_protocol.md` (MIT) and gitlab ggiesen/pybrady. Use them as facts and credit them in the header comment, like `niimbot.h` credits niimbluelib. Never copy Brady binaries, fonts, `.BWS` templates or decompiled code.
- Keep the house rules: no em-dash (U+2014) anywhere; files under 1000 lines; functions with at most 5 parameters (otherwise a struct); every UI string through the string table with German and English (French via `tools/lang_fr.py`).
- Treat the hacs-brady spec as unverified: its README says raster polarity and VGL framing were never captured from a live M211. What the real printer does wins. Record every confirmed or corrected fact.

## Checks (all must pass before a PR)
- `scripts/check.sh`
- `python3 scripts/check_conventions.py` (the baseline may stay or fall, never rise)
- `python3 test/<file>.py` for every file in `test/`, plus new host tests for pure logic (packet framing, GUID byte order, VGL encoding)
- `pio run -e wt32-sc01-plus` still builds (the real scale target, ESP32-S3)
- `pio run -e esp32-brady-test` builds when you touch the Brady code

## Hardware on this box (rs-lxc-33, CT 159)
- A plain ESP32 dev board (not S3; check the chip with `esptool chip_id`) is plugged into Proxmox node rs-srv-01 and bind-mounted into this container as `/dev/ttyUSB0` (or `/dev/ttyACM0`). With no board plugged in, these paths are empty placeholder files.
- The bind mount happens only at container start. After the board is replugged, someone with host access must run `pct reboot 159`. You cannot: ask Raul.
- Flash: `pio run -e esp32-brady-test -t upload --upload-port /dev/ttyUSB0`. Read the serial port non-interactively with a timeout (pyserial is in PlatformIO's venv); never leave an interactive monitor blocking a turn.
- A Brady M211 sits within BLE range of rs-srv-01. Only Raul can see the paper. After every print, ask him what came out (`question ask`) and say what he should expect to see.
- The M211 accepts one owner at a time. If the session claim fails, ask Raul to hold the power button for 5 s until the Bluetooth LED pulses, or to close the Brady Express Labels app.

## Memory
Hindsight bank `personal` (MCP `hindsight`), tag `project:spoolmanscale`, document ids `spoolmanscale/<type>/<slug>`. Background: `spoolmanscale/decisions/2026-11-19-brady-driver`, `homelab/services/rs-lxc-33`. Save confirmed protocol facts and gotchas to `spoolmanscale/learnings`. Never store secrets.
