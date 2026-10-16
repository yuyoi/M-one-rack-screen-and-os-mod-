# How to reverse engineer the M-One (for AI models and humans)

This folder is the briefing for any AI model (or person) that continues the M-One work: the new OS, new effects,
standalone boot, the front-panel controls. Read it before touching code. It says what is known, how it was found,
which tools exist, the rules, and the mistakes that already cost time on the bench.

## Read in this order
| File | What |
|---|---|
| `PROMPT.md` | paste this into a new AI session to start it right |
| `RULES.md` | legal, safety and workflow rules (non-negotiable) |
| `PLATFORM.md` | the hardware: DSP56362, memory, codec, J5/J8, the ESP32-S3 side |
| `METHOD.md` | the method and the tools: J8 OnCE -> dump -> disassemble -> map -> write DSP code -> load -> listen |
| `PITFALLS.md` | every bug that already happened and how to avoid it |
| `HARDWARE.md` | wiring, power, what is on the boards |

The big reference files are in the repo root: `FLASH_MAP.md` (flash format, memory map, audio path),
`FRONT_PROTOCOL.md` (stock DSP <-> front panel link), `dsp/*.py` (effects, heavily commented).

## Status words used everywhere
- **verified**: read from the traced code or the live DSP (or the parsed data is self-consistent).
- **hardware**: the user confirmed it on the real unit, by ear or by eye. Only the user can promote something to this.
- **hypothesis**: plausible, not confirmed. Say so in docs and commits.

## Where things stand (2026-10-15)
- J8 JTAG/OnCE from an ESP32-S3: IDCODE, halt, single-step execution, P/X/Y memory read, flash dump, program load + GO-TO. **hardware**
- Flash dumped and parsed (format + loader sections). **verified**
- Own DSP code runs: passthrough, distortion, heavy distortion, reverse delay with feedback. **hardware** (heard)
- 240x240 ST7789 screen on the ESP. **hardware**
- Not done: standalone codec/ESAI init (TC's boot still sets it up), front-panel controls on the ESP, auto-load, Wi-Fi.
