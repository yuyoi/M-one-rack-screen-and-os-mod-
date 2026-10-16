# Starter prompt for a new AI session

Paste this, then add what you want done:

> You're continuing the M-One new-OS project (repo: M-one-rack-screen-and-os-mod-). Read
> `how-to-reverse-engineer/README.md`, `RULES.md`, `PITFALLS.md` and `FLASH_MAP.md` first. The DSP is a Motorola DSP56362;
> an ESP32-S3 on J8 (JTAG/OnCE) loads programs into P:$0A00 and starts them. `tools/mone.py` is the PC side,
> `tools/dis56k.py` the disassembler. Every DSP program is a Python script in `dsp/` that writes machine code and
> **prints its own disassembly**: check every line of it before loading. Never write to the flash. Say "verified",
> "hardware" or "hypothesis" honestly. Only I can confirm things on hardware. Keep my wiring and pin choices unless I say
> otherwise, and if I propose a hardware route, try it first.
