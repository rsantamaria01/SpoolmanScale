# Brady Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert M211 PICL cartridge geometry into bounded 203-dpi rasters without changing the verified M21-750 print.

**Architecture:** Parse raw PICL status and media type in the existing driver, convert with one tested pure helper, and pass converted geometry to the existing raster/print path. Keep raw status for media-change detection and log unverified conversions.

**Tech Stack:** C++17, Arduino/PlatformIO ESP32, Python host tests.

**Spec:** `docs/superpowers/specs/2026-11-20-brady-geometry-design.md`

## Global Constraints

- Fork-only `fork/` and `AGENTS.md` must not enter upstream PR; push job branch only to origin and PR into `brady-m211`.
- No vendor table or assets, no UI/NVS/M511/layout expansion, no em dash, files under 1000 lines, <=5 function parameters.
- PICL 1/100 inch is hypothetical; only `75/0/0/0 -> 152` dots is paper-verified.
- Do not print without valid bounds; do not replay an unconfirmed job.

## Review Focus

- Invalid size and offsets must fail before BLE writes.
- Nonzero converted offsets must not silently alter the known-good 0-offset wire encoding.
- Continuous media should honor caller-selected length, while die-cut uses PICL fixed length.
- A partial or invalid 0013 response must never be mistaken for a safe continuous cartridge.
- Media changes between status and print must refuse, even with an explicit geometry argument.

---

### Task 1: Convert and validate geometry

**Files:** Modify `src/services/brady.h`, `src/services/brady.cpp`, `fork/brady-test/labels.h`, `test/test_brady.py`, `test/test_brady_labels.py`.

**Interfaces:** `bool bradyGeometryExperiment(const BradyStatus& raw, BradyStatus& dots)` converts and bounds geometry; `bradyVgl` accepts converted geometry. Keep `bradyPrint` caller contract and raw status comparison.

- [ ] Add failing host assertions for 75/0/0/0 -> 152/0/0/0, rounding, nonzero offsets, width+offset above 192, zero width, fixed die-cut length, continuous caller length, and unsafe VGL refusal.
- [ ] Run `python3 test/test_brady.py` and `python3 test/test_brady_labels.py`; confirm expected failures.
- [ ] Implement one conversion helper and adapt encoder, raster harness, status parsing for 0013 and 002A. Keep known-good VGL bytes exactly; log every nonverified geometry as experimental.
- [ ] Re-run both host tests and inspect the diff.

### Task 2: Verify with actual cartridge and record learning

**Files:** Modify `fork/brady-test/hardware-evidence.md` only for observations from this run; record hypothesis to Hindsight `spoolmanscale/learnings`.

- [ ] Build and flash `esp32-brady-test` on `/dev/ttyUSB0`; verify the board identity and connect to the M211 without changing its saved owner.
- [ ] Request a single regression print and capture a correlated `Successful` in serial log; ask Raul through `question ask` to confirm that the physical label looks unchanged.
- [ ] Retain actual observations, units hypothesis, and experimental status under `spoolmanscale/learnings`.

### Task 3: Check and publish

**Files:** All touched files and the design/plan, with fork-only files force-added if ignored.

- [ ] Run `scripts/check.sh`, `python3 scripts/check_conventions.py`, every `test/*.py`, `pio run -e wt32-sc01-plus` and `pio run -e esp32-brady-test`.
- [ ] Review `git status --ignored`, commit to `brady-geometry`, push it to origin and open PR into `brady-m211` after hardware confirmation.
