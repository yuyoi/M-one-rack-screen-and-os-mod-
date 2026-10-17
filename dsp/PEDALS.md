# PEDAL board: guitar pedal + amp sims on the DSP56362 (plan, 2026-10-17)

Lineup = the GP-16 PEDAL/RIG list (30 pedals + 7 amps, `gp16/PEDAL_MODES.md`). Knob sets are the real pedals'
(not a forced 3); where the GP-16 had to fake one (Metal Zone mid, TR-2 wave, RE-201 heads) the real control is back.
Pattern per engine = AMP's: float circuit model (`model/<e>_model.py`, oversampled where it distorts), bit-exact
fixed-point reference (`model/<e>_ref.py`), DSP code (`dsp/<e>.py`), sim56 test (`model/sim_<e>.py`, 0 LSB).

## Engines (one shared engine per circuit family, pedals = coefficient sets)
Cycle numbers: sim56 instructions per frame, then the hardware estimate (x1.3 = AMP's measured ratio, 1299 instr ->
~1690 cycles). Budget 2112/frame, kernel + CLEAN ~85, AMP + kernel ~1770.

| Engine | id* | Circuit model | Pedals | instr | hw cyc |
|---|---|---|---|---|---|
| DIRT | 17 | input DC blocker, pre-EQ biquad (+ dry), 4x polyphase up, 1-3 stages (coupling HPF, gain + pre-clip LPF, bias - dynamic bias, circuit-solved transfer curve as a 257-point table), 48-tap down, clean sum (delayed to line up), 1-3 tone biquads, level | TS808, SD-1, Klon, RAT, DS-1, Big Muff, Metal Muff, Metal Zone, Fuzz Face, Funeral, Iron Man; amp RADIO | **measured** 1 st: 401-439, 2 st: 557-595 (+156 per stage, +19 per tone section) | ~540 / ~760 |
| MOD | 18 | BBD-style modulated delay: pre/post BBD LPF, 2 voices (triangle/sine LFO, linear-interp read), regen, per-voice AM, 2-band split + rotor inertia for the Leslie | CE-2, Dimension D, Flanger (BF-2), Tremolo (TR-2), Leslie | 90-170 | 120-220 |
| PHASER | 19 | 4 first-order JFET allpasses, LFO -> JFET resistance table, script/block feedback | Phase 90 | ~60 | ~80 |
| WAH | 20 | Cry Baby circuit as a TPT state-variable section, treadle -> (g, k) tables, treadle smoothed on the DSP so a 10 Hz pot write never zippers | Crybaby, Reso Wah | ~55 | ~70 |
| SPRING | 21 | dispersive allpass chain (chirp) + 2 tank delays, damping, dwell drive | Spring (6G15-style) | ~200 | ~260 |
| DELAY | 13 (FX lab) | existing engine + a 3-head tape mode | Slapback, Digital, Space Echo | FX lab | FX lab |
| REVERB / SHIMMER | 12 / 14 (FX lab) | existing engines, pedal presets | Hall/Plate, Cathedral, Cave, Church, Stage, Ambient, Shimmer | FX lab | FX lab |
| AMP | 6 | existing engine, 7 voicings (stage gains, bias, tone-stack parts, presence/resonance, sag, cab IR) | Clean, Twin, JCM800, AC30, Doom, DI | +0 (data) | +0 |

*ids proposed, to be agreed with the FX lab (kernel table, VOCAL_ARCH.md).

Board totals (no AMP): TS -> MOD -> SPRING ~ 540 + 220 + 260 + 85 = ~1100 cycles. A DIRT pedal into the full AMP
does NOT fit (1770 + 540 > 2112): RIG mode needs either an optimised DIRT (parallel moves: the stage body is 39
instructions, ~25 is reachable) or a lighter amp (AMP without its preamp: tone stack + power amp + a 256-tap cab).

## Pedals, knobs (real controls, 0-100 unless noted)
| Pedal | Engine (stages) | Knobs |
|---|---|---|
| TUBE SCREAMER | DIRT 1, diodes in feedback, clean sum | DRIVE TONE LEVEL |
| SD-1 | DIRT 1, asymmetric 2+1 diodes in feedback | LEVEL TONE DRIVE |
| KLON | DIRT 1, Ge diodes to ground, clean blend on the gain gang | GAIN TREBLE OUTPUT |
| RAT | DIRT 1, LM308 gain (GBW pole), Si diodes to ground | DISTORTION FILTER VOLUME |
| DS-1 | DIRT 1, transistor boost + op-amp, Si to ground, LPF/HPF tone | TONE LEVEL DIST |
| BIG MUFF | DIRT 2 (+ linear booster), 2 x diodes in feedback, scoop tone | VOLUME TONE SUSTAIN |
| METAL MUFF | DIRT 2, 3-band | VOLUME BOTTOM MIDDLE TOP DISTORTION BOOST(switch) |
| METAL ZONE | DIRT 2, 3-band with sweep mid | LEVEL LOW HIGH MIDDLE MIDFREQ DIST |
| FUZZ FACE | DIRT 2, Ge, dynamic bias (sputter/gate) | VOLUME FUZZ |
| FUNERAL | DIRT 2, doom fuzz, parked wah, low shelf | VOLUME FUZZ WAH LOW |
| IRON MAN | DIRT 2, Ge treble booster into a hot preamp stage | BOOST TREBLE VOLUME |
| CE-2 | MOD | RATE DEPTH |
| DIMENSION D | MOD, 2 antiphase voices | MODE (1-4 buttons) |
| PHASE 90 | PHASER | SPEED SCRIPT(switch) |
| FLANGER | MOD, regen | MANUAL DEPTH RATE RES |
| TREMOLO | MOD (AM only) | RATE WAVE DEPTH |
| LESLIE | MOD, horn/drum split, rotor ramp | SPEED(chorale/tremolo) DEPTH DRIVE |
| SLAPBACK | DELAY | TIME LEVEL |
| DIGITAL DLY | DELAY | LEVEL FEEDBACK TIME |
| SPACE ECHO | DELAY tape mode -> SPRING | MODE(1-12) RATE INTENSITY ECHO REVERB TONE (RE-201 has BASS + TREBLE: folded into TONE) |
| SPRING | SPRING | DWELL TONE MIX |
| HALL/PLATE, CATHEDRAL, CHURCH, STAGE | REVERB | DECAY TONE PRE-DLY LEVEL |
| CAVE | REVERB + echoes | DECAY ECHO TONE LEVEL |
| AMBIENT | REVERB near-freeze | DECAY SWELL TONE LEVEL |
| SHIMMER | SHIMMER -> REVERB | DECAY SHIMMER TONE LEVEL |
| CRYBABY | WAH | PEDAL (the treadle: POT 2) |
| RESO WAH | WAH, high Q | PEDAL RES |
| amps CLEAN / TWIN / JCM800 / AC30 / DOOM / DI | AMP voicings | VOL TRB BAS / VOL TRB MID BAS / GAIN TRB MID BAS PRES MASTER / VOL TRB BAS CUT / GAIN BAS MID TRB VOL / VOL |
| amp RADIO | DIRT 1, class-B crossover curve, speaker band-pass, supply squash | TUNE VOLUME |

The v1/v2 GP-16 extras (HM-2, OD-1, Rangemaster, Octavia, Ram's Head, Green Russian, Fuzz Factory, CE-1, Small
Clone, Mistress, Dim C, Memory Man, signature pedals) are more coefficient sets on DIRT / MOD: later.

## Knob encoding (ESP side)
No math on the ESP: every knob is a table, position 0..100 -> the words it writes (`tools/gen_pedals.py` writes
`firmware/mone_dev/pedals.h` from `dsp/pedals.py`). Knobs that share one filter (Metal Zone MIDDLE x MIDFREQ) get a
2-D table. Transfer curves (129 words per stage) are written when a pedal is picked, in the same halt as its params.

## Memory (PROPOSED to the FX lab 2026-10-17, not agreed yet; VOCAL_ARCH.md is the source of truth)
P for code, X for params + state + curves, Y for the FIR coefficients. SRAM is full (128K all claimed), so pedal
rings share the REVERB / DELAY rings (never in one chain with them) and the curves sit in internal X.
| What | Where |
|---|---|
| DIRT code | P:$0E00-$0EDD (222 words) |
| DIRT params / state / rings | X:$0900-$093F / $0940-$097F / $0980 up (16), $0990 dry delay (16), $09C0 down (64) |
| DIRT curves | X:$0A00, $0B01, $0C02 (257 each) |
| DIRT FIR coefficients | Y:$0D00-$0D5F (copied from AMP's SRAM table at the first call) |
| MOD params / state / ring B / ring A | X:$0D10 / $0D40 / $0D80 (64) / $0E00-$0FFF (512) |

## Status
- DIRT: models + reference + DSP + sim done, all 12 voicings bit-exact in sim56 (`py -3.10 model/sim_dirt.py`).
  Reference vs float circuit model 46-82 dB SNR (`py -3.10 model/dirt_ref.py`). Not on hardware.
- ESP tables: `py -3.10 tools/gen_pedals.py` -> `firmware/mone_dev/pedals_dsp.h` (PD_PEDALS[]: name, colour, FX id,
  init block, curves, knobs with defaults, knob tables). Checked: init + table rows = a full rebuild at any knob set.
