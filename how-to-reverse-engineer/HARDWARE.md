# Hardware

## Boards (plain M-One)
- Mainboard P16001-4 (some units print -3): DSP56362, 3x KM68V1002 SRAM, KM416V1204 DRAM, socketed PLCC32 flash
  ("M-ONE MAIN V1.06"), AK4524, CS8414, J5 front ribbon, J8 JTAG.
- Front board: AT90LS8535 (socketed, "M-ONE FRONT V1.05"), tact switches, edit wheel, pots, LEDs, segment LCD with zebra
  strips and an LED backlight, and the power switch.
- PSU board with its own wiring to the front switch and the mainboard rails (3V3, 5V, +/-15 V).

## Wiring summary
- ESP32-S3 <-> J8: see `../USER_GUIDE.md` (6 wires incl. GND on J8-2).
- Screen: SPI3 on GPIO 7/6, RES 15, DC 16, BLK 17, from the ESP's 3V3 (20-40 mA).
- Without the front panel: hold **J5 pin 16 high** (ESP GPIO, or ~1 k to 3.3 V) or the DSP stays in reset.

## Power for the ESP later
- Not from the M-One 3.3 V while USB is plugged in. For a permanent build: 5 V (J5-4) into the ESP's own regulator, or a
  small buck converter from the digital/raw supply (not the +/-15 V analog rails).

## Case
- The front panel is held only by the side cheeks (Torx). The lid comes off from the top. The user's build replaces the lid and
  front with their own (acrylic, printed caps, TPU).
