# Platform

## DSP: Motorola DSP56362 (XCB56362PV100, 100 MHz, 24-bit)
- DSP56300 core. Manuals: DSP56362 User Manual (memory map, boot modes, ESAI, SHI, Appendix A boot ROM) and the
  DSP56300 Family Manual (instruction encodings ch.12-13, JTAG/OnCE ch.7).
- JTAG IDCODE **0186201D**. Boot: Mode 1 (byte-wide flash at P:$D00000 through AA1), selected by MODx/SPI_DOWNLOAD.
- Memory: 3K internal P RAM, internal X/Y RAM, external 128K x 24 SRAM ($020000, AAR0), 1M x 16 DRAM ($200000, AAR2),
  512 KB flash ($040000 window, AAR1). See `../FLASH_MAP.md`.

## Audio
- AKM AK4524 codec, slave to the board clock logic (MCLK/FS64/FS1); ESAI is a clock slave in network mode, 2 slots.
- ADC -> ESAI RX1, ESAI TX1 -> DAC. CS8414 S/PDIF receiver on the digital input path (RX0).
- Codec control (CCLK/CDTI/CSN/PDN) is bit-banged from DSP port B/C GPIO. The exact pin map is **hypothesis**: trace the
  codec init in `dumps/app.lst` before writing our own init.

## Connectors
- **J5** (2x10, shrouded, FD-20P): the front-panel ribbon. SPI (SHI) + DSP_RESET + SPI_DOWNLOAD + MIDI + power +/-15 V.
- **J8** (2x5, right next to J5): JTAG/OnCE. Odd row 1/3/5/7/9 = TCK/TDI/TMS/TDO/TRST, pin 2 = GND,
  pin 10 = 3.3 V.

## Front board
- AVR AT90LS8535-4JC (socketed): the whole stock UI, buttons, edit wheel, LEDs, segment LCD, and MIDI routing through J5.
  The buttons don't reach the DSP; see `../FRONT_PROTOCOL.md`.
- Power switch on the front board. The PSU runs on its own: "won't start" without the front panel = the DSP held in
  reset by the J5-16 pulldown.

## ESP32-S3 side (`firmware/mone_dev`)
- J8 JTAG bit-banged on GPIO 12/11/13/5/4. Screen on SPI3 (GPIO 7/6/15/16/17). Planned controls: see `../USER_GUIDE.md`.
