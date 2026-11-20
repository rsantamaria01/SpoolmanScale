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
properties to be valid and clear. The experimental harness accepts only raw PICL
width/x/height/y = 75/0/0/0, paired with a 152-dot page in the successful M21-750
app capture. Raw properties remain unchanged; this is not a general unit conversion.
Other geometry fails closed. Both labels use 56 rows (about 7 mm at 203 dpi),
at Raul's request to minimize waste. The captured app page was 152x114; the shorter
page was accepted in both ESP32 paper tests. Actual tape length and minimum
physical feed/cut length remain unmeasured. This fits all four sample text rows
including the large ID. Harness buffer limit is 8192 bytes; too-small labels are refused,
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

Q14: Raul confirmed the official-app TEST printed correctly. Its private BLE capture
shows JobName first (no 12-byte outer wrapper), PartName M21-750, p/o/O/b +00,
M=01, PageSize, W=00, A/Q/a, IBUlbl0, X/Y=0, RLE rows, final Y at page height,
image end, a/G/A, then JobNameEnd last. The encoder now generates this sequence
from our own raster, without repeat-row optimization, printable-size/offset commands
or speculative margins. No captured IDs, ownership bytes or raw capture enter Git.
Fresh 32-hex correlation names avoid assuming how shorter names are handled;
0029 accepts an exact name followed by colon and zero or one space.

On 2026-11-20, both generated 152x56 RLE labels received fresh correlated
`Successful` replies and Raul confirmed their paper output (Q18/Q19 A). The
border/grid printed correctly; the spool label showed MAKER, PLA, BLUE and large
123, small but visible, across the 0.75-inch tape with rows along the roll.
See [sanitized hardware evidence](hardware-evidence.md).

Still to verify: measured grid dimensions, full-width edge precision and physical
feed/cut length. The 152-dot page does not prove all 152 dots are printable.
Nonzero offsets and general PICL units remain unsupported; the raw 75 -> 152
mapping and hardcoded M21-750 part are stock-specific. Ownership flag variants
and long-transfer flush behavior also need further testing. The Python source contains BlueZ-specific workarounds;
they are not assumed to apply to ESP32. No mixed-write retries or print replay.
Ask Raul again before any upload or print; software checks are not hardware proof.
If claim fails, stop and ask Raul to close the Brady app or hold printer power for
5 seconds until the Bluetooth LED pulses. Record only hardware-confirmed facts
in Hindsight `personal`, under `spoolmanscale/learnings`.

## Software checks

Install pinned dependencies first (`pio pkg install -e wt32-sc01-plus`) for the
ArduinoJson-backed host tests. Run every `test/*.py` directly, `scripts/check.sh`,
`python3 scripts/check_conventions.py`, and both firmware builds. This directory
and environment are fork-only and must not accompany an upstream patch.
