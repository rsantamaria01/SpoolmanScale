# M211 hardware evidence, 2026-11-20 (fork only)

Sanitized summary of our own ESP32 serial sessions and Raul's paper confirmations.
No phone bugreport, raw BLE capture, app job identifiers, printer address or
ownership identity is included.

## Setup and observations

- Classic ESP32-D0WD-V3; M211 firmware 1.0.1053703.
- Cartridge: M21-750-595-WT, nominal 0.75-inch white tape.
- FD1C discovery, indication replies and acknowledged ownership flag 0 worked;
  negotiated MTU was 156. This does not establish other ownership flag behavior.
- Raw PICL width/x/height/y was 75/0/0/0. The harness preserves these values and
  explicitly maps only this observed geometry to a 152-dot raster width.
- Both generated jobs used a 152x56-dot page, RLE rows and fresh 32-hex wire names.
  Each terminal 0029 reply matched that job's exact name with `:Successful`.
- Geometry regression on this same stock: 0013=False, 002A=72, raw 75/0/0/0;
  one new 152x56 border/grid/BRADY OK job returned a correlated `Successful`.
  Raul answered Q3 A: the paper looks the same as before.

## Paper confirmations

1. Border/grid test: our serial log `q17-print.log` recorded a correlated
   `Successful`. Raul answered Q18 A, confirming the border/grid printed correctly.
2. Text-only spool test: our serial log `brady-spool-print.log` recorded a different
   fresh correlated `Successful`. Raul answered Q19 A: all four rows MAKER, PLA,
   BLUE and large 123 were present, small but visible. Text ran across the tape
   width and the rows along the roll. No QR code was requested or printed.

Original local serial logs are attached to the Paseo Progress dashboard, not Git.
The paper confirmations are human observations, not inferred from job status.

## Confirmed correction and remaining limits

The working BLE stream starts with JobName, has no 12-byte outer file wrapper,
uses PartName M21-750 and ends with JobNameEnd. The encoder generates its own
raster and correlation name; no vendor font, binary or template was copied.

The follow-up driver converts PICL sizes and offsets under an unverified
1/100-inch hypothesis with bounded head geometry. Nonzero offsets and other
cartridges have host tests but no paper verification. Actual tape length,
minimum feed/cut length, measured grid
spacing and full-width edge precision were not measured. Other cartridges,
long transfers, reconnect stress, M511 and scale UI integration remain untested
or outside scope. Do not automatically replay an unconfirmed job.
