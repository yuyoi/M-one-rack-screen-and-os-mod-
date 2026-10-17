# PEDAL board: guitar pedal + amp sims on the DSP56362

Lineup = the GP-16 PEDAL/RIG list (30 pedals + 7 amps, `gp16/PEDAL_MODES.md`). Knob sets are the real pedals'
(not a forced 3); where the GP-16 had to fake one (Metal Zone mid, TR-2 wave, RE-201 heads) the real control is back.
Pattern per engine = AMP's: circuit model (`model/<e>_model.py`, oversampled where it distorts), bit-exact fixed-point
reference (`model/<e>_ref.py`), DSP code (`dsp/<e>.py`), sim56 test (`model/sim_<e>.py`, 0 LSB).
**Nothing here has run on the hardware.** Memory and effect ids agreed with the FX lab 2026-10-17 (VOCAL_ARCH.md).

## Engines (one engine per circuit family, pedals = coefficient sets)
Cycles: sim56 instructions per frame, measured; hardware estimate x1.3 (AMP: 1299 instr -> ~1690 cycles).
Budget 2112/frame, kernel + CLEAN ~85, AMP + kernel ~1770.

| Engine | id* | Circuit model | Pedals | instr/frame | hw est. | P words |
|---|---|---|---|---|---|---|
| DIRT | 17 | DC blocker, pre-EQ biquad (+ dry), 4x polyphase up, 1-3 stages (coupling HPF, gain + pre-clip LPF, bias - dynamic bias, 257-point circuit-solved curve), 48-tap down, clean sum (delayed to line up), 1-3 tone biquads, level | TS808, SD-1, Klon, RAT, DS-1, Big Muff, Metal Muff, Metal Zone, Fuzz Face, Funeral, Iron Man; amp RADIO | 401-439 (1 stage), 557-595 (2) | 520-570 / 720-770 | 222 |
| MOD | 18 | BBD line: drive, split biquad (BBD in-filter / Leslie crossover), ring A (512) + ring B (64), 2 voices: ramped LFO (rotor inertia), triangle or sine, interpolated read, AM tap, regen; post biquad | CE-2, Dimension D, Flanger (BF-2), Tremolo (TR-2), Leslie 122 | 168-342 | 220-445 | 249 |
| PHASER | 19 | 4 JFET all-passes, break frequency linear in the LFO (JFET triode region), cubic fit, script / block feedback | Phase 90 | 99 | ~130 | 58 |
| WAH | 20 | Cry Baby tank as a Chamberlin SVF band-pass + LP leak, treadle smoothed on the DSP (15 ms), f / Q polynomials | Crybaby, Reso Wah | 77 | ~100 | 66 |
| SPRING | 21 | two springs: dwell drive, ring (33 / 41 ms), band-edge LP, 8 stretched all-passes (dispersion chirp) in each loop, tone LP | Spring (6G15-style); Space Echo's tank | 342 | ~445 | 142 |
| DELAY / REVERB / SHIMMER / SWELL | 13 / 12 / 14 / 15 (FX lab) | the FX lab's engines as they are: the pedal knobs are tables of their param words | Slapback, Digital, Space Echo (DELAY tape -> SPRING), Hall/Plate, Cathedral, Church, Stage, Cave (DELAY -> REVERB), Ambient (SWELL -> REVERB), Shimmer (SHIMMER -> REVERB) | FX lab | FX lab | 0 |
| AMP | 6 | the AMP engine unchanged; 6 voicings = its words (stage gains, coupling / Miller per stage, tone-stack parts, defaults) + a cab IR each | Clean (Deluxe), Twin, JCM800, AC30, Doom, DI | ~1299 | ~1690 | 0 |

*ids agreed; SPRING is built and bit-exact but has no P RAM (sim only), so the SPRING pedal and Space Echo's tank
use a small REVERB for now. Board example (no AMP): TS -> CE-2 -> REVERB ~ 540 + 220 + 470 + 85 = ~1320 cycles.
A DIRT pedal into the full AMP does NOT fit (1770 + 540 > 2112). For RIG mode either DIRT gets optimised (its stage
body is 39 instructions; ~25 is reachable with parallel moves) or RIG uses a lighter amp.

## Pedals and knobs (real controls; 0-100 unless noted)
| Pedal | Engine | Knobs |
|---|---|---|
| TUBE SCREAMER | DIRT 1 stage: 1N914s in the feedback (curve fitted per DRIVE), clean sum, 723 Hz tone | DRIVE TONE LEVEL |
| SD-1 | DIRT 1: asymmetric 2 + 1 diodes in the feedback | LEVEL TONE DRIVE |
| KLON | DIRT 1: 1N34A to ground, dual-gang GAIN (gain + less clean), mid bump, treble shelf | GAIN TREBLE OUTPUT |
| RAT | DIRT 1: LM308 gain network (60 Hz / 1.5 kHz shelves, GBW pole down to ~300 Hz), 1N914s to ground, FILTER RC | DISTORTION FILTER VOLUME |
| DS-1 | DIRT 1: booster + op-amp into 1N4148s, LPF / HPF blend tone (nodal analysis) | TONE LEVEL DIST |
| BIG MUFF | DIRT 2: two transistor stages with diodes in the feedback, the 39k/10n + 4n/22k tone stack | VOLUME TONE SUSTAIN |
| METAL MUFF | DIRT 2: two op-amp stages into diodes, 3-band | VOLUME BOTTOM MIDDLE TOP DISTORTION BOOST(switch) |
| METAL ZONE | DIRT 2: feedback diodes + diodes to ground, shelves +-15 dB, swept mid 200 Hz-5 kHz | LEVEL LOW HIGH MIDDLE MIDFREQ DIST |
| FUZZ FACE | DIRT 2: germanium CE stages (Ebers-Moll), input-cap bias shift (dynamic bias) | VOLUME FUZZ |
| FUNERAL | DIRT 2: doom Muff core, dark stack, parked wah peak, low shelf | VOLUME FUZZ WAH LOW |
| IRON MAN | DIRT 2: Rangemaster (Ge, treble boost) into a cranked 12AX7 stage (Koren) | BOOST TREBLE VOLUME |
| CE-2 | MOD: 4.5 ms BBD, triangle 0.1-7 Hz | RATE DEPTH |
| DIMENSION D | MOD: two antiphase BBD lines | MODE (buttons 1-4) |
| FLANGER | MOD: 0.5-6 ms, regen | MANUAL DEPTH RATE RES |
| TREMOLO | MOD: AM, triangle -> square | RATE WAVE DEPTH |
| LESLIE | MOD: horn / drum, 800 Hz crossover, Doppler + AM, spin-up 0.7 s / 4 s, preamp drive | SPEED(switch) DEPTH DRIVE |
| PHASE 90 | PHASER | SPEED BLOCK(switch: script / block feedback) |
| CRYBABY | WAH | PEDAL (the treadle) |
| RESO WAH | WAH, high Q | PEDAL RES |
| SPRING | REVERB stopgap (SPRING engine: no P) | DWELL TONE MIX |
| SLAPBACK / DIGITAL DLY | DELAY | TIME LEVEL / LEVEL FEEDBACK TIME |
| SPACE ECHO | DELAY HEADS (T / 2T / 3T, wow, tape sat) -> REVERB | MODE(1-7: H1 H2 H3 H2+3 H1+2 H1+3 H1+2+3; the selector's reverb on/off = REVERB at 0) RATE INTENSITY ECHO REVERB(volume) TONE (RE-201 BASS + TREBLE folded into TONE) |
| HALL/PLATE, CATHEDRAL, CHURCH, STAGE | REVERB | DECAY TONE PRE-DLY LEVEL |
| CAVE | DELAY -> REVERB | DECAY ECHO TONE LEVEL |
| AMBIENT | SWELL -> REVERB | DECAY SWELL TONE LEVEL |
| SHIMMER | SHIMMER -> REVERB | DECAY SHIMMER TONE LEVEL |
| amps CLEAN / TWIN / JCM800 / AC30 / DOOM / DI | AMP voicings (`model/amp_voicings.py`) | VOLUME TREBLE BASS MASTER / VOLUME TREBLE MIDDLE BASS MASTER / PRE-AMP MASTER TREBLE MIDDLE BASS PRESENCE / VOLUME TREBLE BASS CUT MASTER / GAIN BASS MID TREBLE VOLUME / VOLUME |
| amp RADIO | DIRT 1: class-B crossover, 2.5" speaker band-pass + cone peak | TUNE VOLUME |

The v1/v2 GP-16 extras (HM-2, OD-1, Rangemaster, Octavia, Ram's Head, Green Russian, Fuzz Factory, CE-1, Small
Clone, Mistress, Dim C, Memory Man, signature pedals) are more coefficient sets on DIRT / MOD: later.

## ESP hand-off (`firmware/mone_dev/pedals_dsp.h`, generated: `py -3.10 tools/gen_pedals.py`)
`PD_PEDALS[]`, one `PdDef` per pedal: name, colour, `fx[nfx]` (1 id = SINGLE mode, 2 = CHAIN), init writes
(`ia`/`iv`: the param block at the default knobs + start states), curves (DIRT: 257 words at an X address),
knobs (`label`, default 0..100, steps) and knob tables (`PdTab`: the knob(s), steps, X addresses, values).
- Pick: halt once: init writes, every table at its knob's position, the curves, then mode + FX id(s).
- Knob move: that knob's table row (1-8 long X writes). Every param word belongs to exactly one table (checked by
  the generator); Metal Zone MIDDLE x MIDFREQ, Metal Muff TOP x BOOST and Flanger MANUAL x DEPTH (and Space Echo
  MODE x RATE) are 2-D tables (21 steps each, a switch 2, mode buttons their count).
- Checked: init + table rows = a full rebuild at random knob sets, all DIRT pedals.
- Clear-on-pick: DIRT's and MOD's init writes include INITF = 0 (X:$097F / $0D5F): the engine re-inits on the next
  frame (state + rings cleared, MOD keeps the voice states the pick wrote), so the old pedal's tail never plays.
  That one frame costs more: DIRT ~800-960, MOD ~780-950 instructions.
- Amp voicings are not in this header yet: they need ampTmb (menu.h) to take each voicing's parts and an IR write
  (512 words to Y:$0800 + AMP's SRAM table X:$031C00), so they go to the ESP owner as data (amp_voicings.py).
This plugs into `menu.h` PEDALS[] / PedalDef: a board knob = a `PdKnob` + its tables (the board draws 1-6 knobs).

## Memory (agreed with the FX lab 2026-10-17; VOCAL_ARCH.md is the source of truth)
| What | P | X | Y / SRAM |
|---|---|---|---|
| DIRT | $0E00-$0EDD | $0900 params, $0940 state, $0980 up ring (16), $0990 dry ring (16), $09C0 down ring (64), $0A00-$0D02 3 curves | Y $0D00-$0D5F FIR (copied from AMP's SRAM table) |
| MOD | $0EE0-$0FD8 | $0D10 params, $0D40 state, $0D80 ring B (64), $0E00-$0FFF ring A (512) | - |
| PHASER / WAH | $0960-$09DB (of $0960-$09FF) | $0DC0-$0DFF | - |
| SPRING | none left (needs ~142 words) | (placeholder $0888) | would share REVERB's ring $038000 |

## Status (2026-10-17)
- All engines bit-exact in sim56: `py -3.10 model/sim_dirt.py`, `sim_mod.py`, `sim_filt.py`, `sim_spring.py`,
  `amp_voicings.py`. DIRT reference vs its float circuit model: 46-82 dB SNR (`py -3.10 model/dirt_ref.py`).
- Not on hardware (needs the FX lab's os.py / boot wiring and the OTA handshake); levels are first guesses (DIRT trimmed to ~-18 dBFS rms at the default
  knobs with a hot DI; the rest by ear later).
