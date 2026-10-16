# M-One new OS: user guide

## What you need
- A TC Electronic M-One (plain, mainboard P16001-4 or -3). The lid comes off; the front panel stays connected for now.
- An ESP32-S3 dev board (tested: N16R8 / N8R8 with a CH343 USB-serial port).
- Optional: a 1.54" 240x240 ST7789 SPI screen.
- A PC with Python 3 + pyserial, and arduino-cli (or the Arduino IDE) with the esp32 core and LovyanGFX.

## Wiring: ESP32-S3 to J8 (the 2x5 header next to the front-panel ribbon)
J8 pin 1 is the corner nearest the ribbon header (J5), on the row toward the DSP. Leave pin 10 (3.3 V) empty: the ESP
runs on its own USB.

```
J8 pin 1  (TCK)  = GPIO 12
J8 pin 2  (GND)  = GND
J8 pin 3  (TDI)  = GPIO 11
J8 pin 5  (TMS)  = GPIO 13
J8 pin 7  (TDO)  = GPIO 10
J8 pin 9  (TRST) = GPIO 4
J8 pin 10 (3V3)  = not connected
```

## Wiring: the screen
```
TFT GND = GND        TFT VCC = 3V3
TFT SCL = GPIO 8     TFT SDA = GPIO 9   (as wired: the order that works)
TFT RES = GPIO 15    TFT DC  = GPIO 16
TFT BLK = GPIO 17    TFT CS  = GPIO 18 (held LOW by the firmware)
```
Check GND twice: on the first build the screen's GND went to 5 V and the screen stayed black.

## Wiring: controls
```
POT 1-3   = GPIO 5, 6, 7  (wiper; outer lugs to 3V3 and GND, never 5 V)
            in a row on the left header. Lug order only flips direction.
ENC A/B   = GPIO 38, 39   (middle pin to GND, no push switch, internal pullups)
BUTTONS   = GPIO 48, 47, 21, 20, 19, 40, 41, 42, 14 (9 direct buttons, other leg to GND; any order, the learn maps them)
DSP SENSE = GPIO 3        (power button pole B: closes to GND when the DSP is off; open/unwired = on)
LADDER 1  = GPIO 1        (resistor-ladder button bank, ADC1)
LADDER 2  = GPIO 2        (second ladder bank, ADC1; 1 and 2 sit side by side)
            all buttons (tap and bypass too) live on the two ladders
            per ladder: 10k from 3V3 to the GPIO; each button = GPIO -> own resistor -> button -> common GND
            button resistors: 100R, 3.3k, 4.7k, 10k, 15k, 22k, 47k (7 per ladder; firmware learns the levels)
            ladder 1 = one button only (~1650 mV); the near-idle one moved to a direct pin
```
The screen shows live pots / ladders / encoder (rows 0-3) and the WiFi IP (row 4). Any serial command takes the
rows over; `i` brings the live view back.

## Power button (DPDT)
```
pole A: middle -> J5-16 (DSP reset)   one side -> J5-17 (3V3)   other side -> nothing
pole B: middle -> GND                 OTHER side -> GPIO 3      first side -> nothing
```
One position: the DSP runs and GPIO 3 is open (the UI is awake). Other position: the board holds the DSP in reset
and GPIO 3 goes to GND (the face sleeps, backlight off after 5 min without input). The ESP itself stays powered from J5 pin 4.
If pressed-in turns out to be "off", swap both outer wires to the opposite side.

## WiFi + OTA
- `python tools/mone.py COMx wifi`: asks for the SSID and password (hidden) and stores them on the ESP (NVS, never in the source).
- `python tools/mone.py ota [mone.local | IP]`: builds the firmware and flashes it over WiFi. No USB needed after the first flash.

## Setup
1. `arduino-cli compile --upload -p COMx --fqbn esp32:esp32:esp32s3 firmware/mone_dev`
2. `python tools/fetch_opcodes.py` (once: builds the disassembler table)
3. Power the M-One on normally and let it boot (this sets up the clocks and the audio port).
4. `python tools/mone.py COMx jid`: must print `0186201D`, which is the DSP answering on J8.

## Running an effect
```
cd dsp
python revdelay.py                      # prints the disassembly, writes revdelay.hex
python ../tools/mone.py COMx load revdelay.hex
python ../tools/mone.py COMx go A00
```
`load` halts the stock firmware, writes the program to P:$0A00 and reads it back (`verify OK`). `go` starts it.
To get the stock M-One back: power-cycle.

**Without the front panel the outputs stay muted.** TC's firmware only un-mutes when its front panel tells it to.
So also `python codec_on.py`, `load codec_on.hex`, and then `go 900` instead of `go A00`. That writes the codec's run
values, drives MUTE* (PB12) low and jumps to $0A00. On this board MUTE* works backwards: high or open = muted.

## The OS
```
cd dsp
python autotune.py                      # writes autotune.hex (P:$0400)
python os.py                            # writes os.hex (P:$0A00, the kernel; calls into autotune)
python codec_on.py                      # writes codec_on.hex (P:$0900): codec on + outputs unmuted, then the kernel
python ../tools/mone.py COMx boot       # loads all three over J8, verifies, starts codec_on -> kernel
```
Effects: CLEAN, HEAVY, REVERSE, COMP, TUNE (autotune). Modes: SINGLE, DOUBLE (parallel), DBL-SINGLE (series).
`python model/sim_os_tune.py 215` runs the whole OS in the simulator with FX 1 = TUNE (expect A3, within a few cents).

## The front panel
First boot (or serial `K`): the screen asks for every button by position, T1-T6 top row, B1-B6 bottom row, R1/R2
right column. Press each once; turn the encoder to skip a dead one. The map is stored on the ESP.

| Control | Does |
|---|---|
| T1 / T2 / T3 | FX page / TUNE page / SYSTEM page (live inputs, WiFi IP + signal in dBm) |
| T6 / B6 | cursor up / down |
| encoder | change the selected value |
| R1 / B4 / B5 | enter (value +1); on the SYSTEM page: button test |
| R2 | back to the FX page |
| B1 / B2 | bypass FX 1 / FX 2 |
| hold R1 + T6, 3 s | reboot the ESP (only while the face is asleep) |

- FX page: MODE, FX 1, FX 2. Every change goes to the DSP at once.
- TUNE page: KEY, SCALE (chromatic / major / minor), SPEED 0-10 (0 = natural glide, 10 = hard robot). Notes outside
  the scale snap to the nearest scale note (ties snap down). All 13 values go to the DSP in one short halt.
- BUTTON TEST page (SYSTEM page, then enter; or serial `T`): every press only lights its box. Green = has worked,
  yellow = latest, grey = not seen yet. The latest press shows its source (GPIO pin or ladder mV); a press that
  matches no learned button shows `??` in red. The page also shows the pots as bars and counts encoder steps.
  Press R2 twice to go back to the FX page. The idle face stays away while the test is on.
- No input for 8 s: uwu. A minute: it sleeps. The first touch only wakes it.
- PC keys still work: `mone.py COMx key ]=` (`[ ]` cursor, `- =` value, `F` FX page).

## Other commands (`tools/mone.py COMx ...`)
| Command | What |
|---|---|
| `jid` | DSP JTAG ID |
| `regs` | halt, read OMR/SR/AAR1/BCR/HCSR/HCKR, resume |
| `jdump out.bin` | dump the 512 KB flash (~6 min) |
| `pmem` / `xmem` / `ymem out.bin START COUNT` | read live DSP memory (hex words), non-destructive |
| `screen` | screen test: backlight blink, red/green/blue fills, splash |

## Tweaking the effects
The constants are at the top of each script: `revdelay.py` has `N` (chunk length in samples; 1 beat = 44100*60/BPM,
even number), `FB` (feedback), `WET`. `heavy.py` has the filter coefficients and the output trim. Change, re-run,
`load`, `go`.
