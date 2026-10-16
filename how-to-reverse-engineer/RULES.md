# Rules (non-negotiable)

## Legal
- No TC Electronic code, ROM data, update payloads, disassembly listings or service documents in the repo. Dumps and
  listings stay in `dumps/` (ignored). Docs may state facts (addresses, register values, formats), not reproduce code.
- The opcode table is GPL-3.0 (dsp56300 emulator): fetched by `tools/fetch_opcodes.py`, never committed.

## Safety
- **Never write the flash** until there is a verified backup and our own init is proven. All development is RAM-only
  over J8: a power cycle always brings the stock unit back.
- Never connect the ESP to J5 pins 10/13 (+/-15 V). Never feed the ESP from the M-One's 3.3 V while it's on USB.
- Check every new wire with a meter first (GND beeps to GND, 3.3 V reads 3.3 V) before power-up.
- Keep the monitor volume low the first time a new program runs.

## Workflow
- Build -> read the printed disassembly line by line -> load (it must say `verify OK`) -> go -> confirm it runs
  (`regs`: PIL/PDB inside our code) -> the user listens.
- One change at a time. When something fails on hardware, measure (probe pins, peek registers or memory over OnCE)
  before theorizing.
- Write Python files with the editor tools or `encoding='utf-8'` plus temp-file-and-rename: a cp1252 crash once truncated a
  notes file to 0 bytes.
