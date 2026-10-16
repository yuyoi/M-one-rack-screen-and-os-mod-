# Pitfalls (all of these already happened)

- **Flash dump wrapped (M0 modulo).** The stock app leaves modulo values in M0, so `(r0)+` wrapped at 0x5600, and in another
  run at 0x8000. Two identical "verified" dumps were both wrong; "identical twice" only proves the bug repeats. Fix:
  `movec #$FFFFFF,m0` before any OnCE memory walk (and save/restore it on live reads).
- **OnCE NOSEL+GO re-execution stalls on P reads.** Re-executing `movep p:(r0)+,x:OGDB` with "no select + GO" let the read
  word land in the instruction latch and execute: reads repeated a 2-word opcode forever. Fix: re-send the instruction for
  every word (`write PDB with GO`).
- **Rare JTAG bit errors** (2 bytes in 512 KB) on long dupont leads. Always dump twice and settle differences by
  re-reading just those addresses.
- **J5 Mode-5 SPI boot never answered.** MISO stayed floating even with SS low, with every reset polarity and boot mode tried.
  The J5 reset line has a 3.74 k pulldown, so drive it high to run. J8 was the user's plan from the start and it worked
  first try: take the user's hardware route first.
- **Screen black = GND on 5 V.** Meter-check every power wire. (Also: CS-less ST7789 modules want SPI mode 3, and BLK is
  driven as a plain GPIO because the core 3.x LEDC API changed.)
- **Wrong memory space in a hand encoding.** `5E/5F` short moves are Y:, not X:. Caught by reading the printed
  disassembly before loading. Always read it.
- **Too little drive.** Real input levels are low: +24 dB only made the first distortion louder. Measure (peek X1 over
  OnCE) instead of guessing levels.
- **Feedback through a window.** A triangle window averages ~0.5, so loop gain = FB x 0.5. FB 0.2 died after one repeat,
  0.85 rang ~10 s, 0.55 is the keeper at 92 BPM.
