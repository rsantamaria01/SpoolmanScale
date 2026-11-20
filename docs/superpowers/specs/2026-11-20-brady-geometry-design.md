# Brady cartridge geometry design

Intent: size M211 rasters from PICL for other cartridges while keeping the verified M21-750-595-WT output unchanged. Other media units, offsets, feed length and print behavior remain experimental.

Approaches: hard-code the known cartridge (safe but fails the goal); compute but prohibit other media (safe but fails the goal); or convert PICL 1/100-inch sizes and offsets at 203 dpi with bounds and explicit experimental logging (chosen). Do not use a vendor part table.

Use one tested conversion helper in the Brady driver, round to nearest dot, retaining 75 -> 152. Reject zero and head-width overflow including offsets. For die-cut media use the reported fixed length; for continuous media use the caller-selected raster length. Parse and log 0013 and 002A. Preserve job correlation and verified print bytes. No UI, NVS profile, M511, new layout, or vendor data. Hardware print and host tests verify the known stock; other cartridges need later physical calibration.
