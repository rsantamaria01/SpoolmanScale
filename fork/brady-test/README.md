# M211 bench harness (fork only)

This classic ESP32 environment compiles the actual `ble_service.cpp` and `brady.cpp`.
It has no display, scale, backend, SD card, model profile or M511 support.

## Hardware gate

Do not open `/dev/ttyUSB0` or `/dev/ttyACM0` while they are placeholder files.
Ask Raul first: **A: board and printer are ready, CT rebooted** or
**B: later, open the PR as draft**. Replugging requires the host operator to reboot
CT 159. Do not change the infrastructure from this harness.
After A, verify the selected path is a character device and identify the chip with
PlatformIO's esptool (`chip_id`) before uploading. The board must be classic ESP32.

```sh
pio run -e esp32-brady-test
pio run -e esp32-brady-test -t upload --upload-port /dev/ttyUSB0
```

Use bounded pyserial sessions at 115200 baud, never a blocking monitor. Save logs
outside tracked source, then attach them to the Paseo Progress dashboard. Opening
the port can reset the board depending on DTR/RTS; disable those when possible.
There is no automatic connection or print. First boot enables the existing shared
transport's `spoolscale/ble_on` key and restarts once to retain controller RAM.
The harness stores its random ownership UUID in `brady-test/owner` before using it;
a failed save or invalid stored identity blocks connection. Do not erase NVS to
work around an ownership error without asking Raul.

## Commands, one per line

- `scan`: FD1C-advertising devices only; disconnect first.
- `connect aa:bb:cc:dd:ee:ff`: subscribe, write ownership and request status.
- `status`: pump replies; print geometry, validity/error bits and job result.
- `print test`: border, 1 mm grid, small BRADY OK inscription.
- `print spool`: text-only sample: MAKER, PLA, BLUE, large 123.
- `cut`: explicit cut command; result is unconfirmed, not proof of a physical cut.
- `disconnect`: close GATT, preserving persisted ownership.

Printing requires all four geometry properties and all seven requested safety
properties to be valid and clear. Finite media uses the reported height;
continuous media explicitly uses 320 printable dots (about 40 mm), plus live
vertical margins. Harness buffer limit is 8192 bytes; too-small labels are refused,
not silently clipped. Test glyphs are original 3x5 diagnostic drawings under this
repository's GPL-3.0 license, not a Brady font.

After **each** print ask Raul what came out and request a photo. First expect a
complete rectangle, evenly spaced grid and readable BRADY OK on white stock.
Second expect four text rows, with 123 larger and no QR code. Check orientation,
clipping, spacing and polarity. A correlated `Successful` reply alone does not
prove correct paper. Never automatically replay an unconfirmed job.

## Sources and unverified assumptions

Protocol facts: JonBons/hacs-brady (MIT), commit
`19ed2251a1e95bcb102a1fc40ad48c960291d0cd`,
`specs/brady_m211_bluetooth_protocol.md` and Python protocol/client/vgl/render;
that spec cross-checks ggiesen/pybrady. No proprietary fonts, binaries or templates
were copied. NimBLE API checked against upstream tag 2.5.1 because Context7 quota
was unavailable: `subscribe(false, callback)` selects indications;
`writeValue(..., true)` requests acknowledgement.

Still to verify on this M211: ownership flags (1 for a new persisted identity,
0 for reuse), whether acknowledged writes are accepted, response framing,
1=black raster polarity, page dimensions/offsets, raw row commands and VGL6
length/name offsets. Page width currently adds live left offset; height adds
live vertical offset twice. The Python source contains BlueZ-specific workarounds;
they are not assumed to apply to ESP32. No mixed-write retries or print replay.
If claim fails, stop and ask Raul to close the Brady app or hold printer power for
5 seconds until the Bluetooth LED pulses. Record only hardware-confirmed facts
in Hindsight `personal`, under `spoolmanscale/learnings`.

## Software checks

Install pinned dependencies first (`pio pkg install -e wt32-sc01-plus`) for the
ArduinoJson-backed host tests. Run every `test/*.py` directly, `scripts/check.sh`,
`python3 scripts/check_conventions.py`, and both firmware builds. This directory
and environment are fork-only and must not accompany an upstream patch.
