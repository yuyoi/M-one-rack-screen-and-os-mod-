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
python vocal.py                         # writes vocal.hex (P:$0700): vocal effects (VOX)
python os.py                            # writes os.hex (P:$0A00, the kernel; calls into autotune and vocal)
python codec_on.py                      # writes codec_on.hex (P:$0900): codec on + outputs unmuted, then the kernel
python ../tools/mone.py COMx boot       # loads all four over J8, verifies, starts codec_on -> kernel
                                        # then the ESP sends its panel state, so the sound matches the screen
```
Effects: CLEAN, HEAVY, REVERSE, COMP, TUNE (autotune), VOX (vocal chain), AMP (modeled tube amp), RADIO (6 lo-fi
modes), FORMANT and OCTAVE (PSOLA), HARMONY, DOUBLER, REVERB, DELAY, SHIMMER (goes right before REVERB), SWELL
(auto fade-in) and GRAIN (granular cloud; shares REVERSE's buffer, so never both). STRIP is an input stage in front of every mode (gate, de-esser, leveler, EQ, drive). Modes: SINGLE,
DOUBLE (parallel), DBL-SINGLE (series).
Parameter addresses: `VOCAL_ARCH.md` in the FX lab notes; `boot` loads autotune, vocal, vocal2, vocal3, amp (each
with its table in SRAM), os and codec_on.
`python model/sim_os_tune.py 215` runs the whole OS in the simulator with FX 1 = TUNE (expect A3, within a few cents).
`python model/sim_vox.py` does the same with FX 1 = VOX and compares it with `model/vox_model.py` (expect ~1e-7).
`python model/sim_radio.py MODE` (0-5) and `python model/sim_psola.py 8 1.0 0.78` (FORMANT) / `9 0.5 1.0` (OCTAVE)
compare RADIO and the PSOLA engine with their models (expect ~2e-7 and 0 LSB). `python ../tools/fxmeter.py PORT 4 7 8 9`
boots meter builds with the outputs muted and prints each effect's worst cycles per frame on the hardware.

**RADIO** modes (X:$0210): TELEPHONE (300-3400 Hz, 8 kHz sample-and-hold), MEGAPHONE (horn peak, hard breakup,
0.5 ms horn comb), AM RADIO (boxy, static + crackle), WALKIE (narrow, crushed, squelch "kshh" when you stop),
CASSETTE (head bump, tape saturation, wow + flutter, hiss), VINYL 78 (gramophone band, crackle, 78 rpm wow).
**FORMANT** moves the formants and keeps the pitch (GIANT 0.78, CHIPMUNK 1.35); **OCTAVE** drops the pitch an octave
and keeps the formants. Both use TUNE's pitch detector (now spread over 4 frames: TUNE's worst case went from ~1410
to ~670 cycles per frame).

**VOX** is a vocal chain voiced for a crystal/ceramic ham mic (D-104 style): HPF 80 Hz, +5 dB body at 180 Hz,
-4 dB at 1 kHz (honk) and 3.5 kHz (crystal peak), a leveling compressor, light tube saturation, an exciter (the
part above 3 kHz saturated and mixed back in, for clarity without boosting hiss) and a 110 ms slap. The constants
are at the top of `dsp/model/vox_model.py`.

**AMP** is a modeled tube amp: a 4x oversampled preamp (three triode stages with coupling filters, dynamic bias and
soft clipping), a Fender or Marshall tone stack, a power amp with resonance, presence and supply sag, and a 512-tap
cab IR. `python model/sim_amp.py` runs it in the simulator against `model/amp_ref.py` (expect bit-exact). With the
kernel it takes ~1770 of the 2112 cycles per frame, so it runs on its own, without vocal effects next to it.
Its EDIT page: TYPE (CLEAN = Fender stack, low gain / CRUNCH / LEAD = Marshall stack; picking one loads its starting
knobs), GAIN (0-10; 7.0 = the type's own gain, each step 1.25 dB on the first two stages), BASS / MID / TREBLE (the
real tone-stack circuit, computed on the ESP), PRESENCE (wide 3 kHz peak, -12..+12 dB), RESONANCE (100 Hz, 0..+12 dB),
DRIVE (power amp, -12..+18 dB), SAG (supply droop, 0-90 %), MASTER. While AMP plays the pots are a pedal: POT 1 = level,
POT 2 = GAIN, POT 3 = TREBLE (a pot takes over its row once it moves; the mix is all amp, the kernel tone filter open),
and the idle screen shows a mock pedal with LEVEL / GAIN / TONE. Serial `a<10 values>` prints the words the ESP
computes for a setting (the check against `amp_ref.ui_words`).

## The front panel
First boot (or serial `K`): the screen asks for every button by position, T1-T6 top row, B1-B6 bottom row, R1/R2
right column. Press each once; turn the encoder to skip a dead one. The map is stored on the ESP.

| Control | Does |
|---|---|
| T1 / T2 / T3 | shortcuts: VOCAL FX page / SETTINGS (tune) / SYSTEM (live inputs, WiFi IP + signal in dBm) |
| T4 | PRESETS (opens on a playing preset) |
| T5 | EDIT page: the effect's own settings |
| T6 / B6 | cursor up / down (MODE ring and PEDAL board: turn / swap) |
| encoder | change the selected value (MODE ring: turn it; PEDAL board: swap pedals) |
| R1 / B4 / B5 | enter: open (ring item, preset list, a pedal's settings), else value +1; SYSTEM: button test |
| R2 | EXIT: one step back along the way you came, all the way to the MODE ring |
| B1 / B2 | bypass FX 1 / FX 2 (a preset: B1 bypasses its whole chain) |
| B3 | reverb FREEZE on / off (while REVERB plays) |
| POT 1 / 2 / 3 | volume (40 dB taper, far left = off) / dry-wet mix / tone (low-pass, far right = open); with AMP playing: level / GAIN / TREBLE |
| hold R1 + T6, 3 s | reboot the ESP (only while the face is asleep) |

- MODE ring (the boot screen; EXIT always leads back here): five low-poly 3D icons turning over a Castlevania night,
  Crash Bandicoot 2 style (`firmware/mone_dev/ring3d.h`; sprites from `tools/gen_sprites.py`): tuxedo cat = VOCAL FX,
  vinyl = PRESETS, the red '69 stompbox = PEDAL, chrome cog = SETTINGS, bible = SYSTEM. The knob turns it, enter
  opens, a gold crown sits on the mode that is playing, the status bar says what plays. Every page remembers its
  cursor, so EXIT then enter lands you where you were.
- PEDAL board: guitar pedals, each drawn with its own knobs (HEAVY: LEVEL TONE, COMP: LEVEL BLEND, REVERSE: LEVEL MIX
  TONE, AMP: LEVEL GAIN BASS MID TREB PRES). The knob slides to the next pedal; the sound follows once it rests.
  POT 1 = LEVEL; POT 2 / 3 = the pedal's MIX / TONE where it has them (AMP: GAIN / TREBLE); a pedal without a MIX knob
  plays all wet. Enter opens the pedal's settings. Careful: HEAVY is +60 dB. Real-pedal sims come next (DSP).
- PRESET page (T4): the loaded preset (number, name, type, chain, a hint like TONE DARK). Turn the knob (or T6 / B6)
  for the previous / next one: it loads once the knob rests. Enter opens the list by type (STUDIO, TUNE, HARMONY,
  LO-FI / RADIO, MONSTER, AMBIENT), enter again opens a type, enter on a preset loads it; R2 goes back a level.
  A preset is a chain of up to 6 effects (CHAIN mode) plus STRIP and every setting, sent in one short halt. Its tune
  and harmony parts follow the TUNE page's key. The EDIT pages show the preset's values; changing one marks the
  preset EDITED. The ESP remembers the last preset and takes it back after a reboot when the DSP still plays it.
  The table is generated: `py -3.10 tools/gen_presets.py` (from `dsp/presets.py`) writes `firmware/mone_dev/presets.h`.
- FX page: MODE, FX 1, FX 2, STRIP (on / off; T5 on this row opens its settings). Every change goes to the DSP at
  once. With a preset loaded MODE shows CHAIN and the routing line shows the chain; turning FX 1 / FX 2 leaves it.
- TUNE page: KEY, SCALE (chromatic / major / minor), SPEED 0-10 (0 = natural glide, 10 = hard robot). Notes outside
  the scale snap to the nearest scale note (ties snap down). All 13 values go to the DSP in one short halt.
- EDIT page (T5): the settings of FX 1 (or of FX 2 when FX 1 has none) for AMP, RADIO, FORMANT, OCTAVE, HARMONY, DOUBLER,
  REVERB, DELAY, SHIMMER, SWELL and GRAIN; on the FX page's STRIP row, STRIP's own (GATE, DE-ESS, COMP, MAKEUP, DRIVE, EQ
  PRESENCE / AIR / LOW + EQ GAIN). The first row of FORMANT (VOICE), REVERB and DELAY (TYPE) is a preset that sets the rows under it;
  turning one of those rows by hand makes it CUSTOM. Long lists scroll (yellow arrows at the right edge). Changes go
  out at once. HARMONY's two voices are intervals in the TUNE page's key and scale (3RD UP, 5TH DN, ...; CHROMATIC
  harmonizes in major) or fixed ones (+7 ST, ...); changing the key re-sends them.
- BUTTON TEST page (SYSTEM page, then enter; or serial `T`): every press only lights its box. Green = has worked,
  yellow = latest, grey = not seen yet. The latest press shows its source (GPIO pin or ladder mV); a press that
  matches no learned button shows `??` in red. The page also shows the pots as bars and counts encoder steps.
  Press R2 twice to go back to the FX page. The idle face stays away while the test is on.
- Idle face: 8 s without input and it takes over the screen; 60 s and it dozes. It **sings along with the output**:
  the mouth opens with the level, loud parts close the eyes to ^ ^, and music notes float up. The level comes from
  the kernel through the DSP's OnCE mailbox (OGDB), read over JTAG without halting the DSP, so no audio blips.
- No input for 8 s: uwu. A minute: it sleeps. The first touch only wakes it.
- PC keys still work: `mone.py COMx key ]=` (`[ ]` cursor, `- =` value, `F` FX page, `#` PRESET page,
  `< >` previous / next preset).

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
