# M-One flash + memory map (plain M-One, flash "M-ONE MAIN V1.06")

Status words: see `how-to-reverse-engineer/README.md`. Everything here is **verified** from a dump unless marked otherwise.
Addresses are DSP addresses. No TC code is reproduced here, only the facts needed to work with the hardware.

## Flash (PLCC32, 512 KB, IC17)
- Read by the boot ROM in Mode 1 at P:$D00000 with AAR1 = $D00409: one byte per address on D7-D0.
- **Offset 0: a Mode-1 boot record** `[count][addr][words]`, each a 3-byte little-endian value: 986 words -> P:$000000 (TC's loader).
- **The loader** (P:$232 init, P:$3C0 main) copies these records into P memory (the table is at P:$4D-$51; flash address = $040000 + offset):

| flash offset | words | loads to |
|---|---|---|
| 0x00B94 | 10749 | P:$025600-$027FFC (external SRAM) |
| 0x08991 | 10610 | P:$02D600-$02FF71 (contains the reset target $02FF6E) |
| 0x105ED | 3158 | P:$02FF72-$030BC7 |
| 0x12AF5 | 9 | P:$001000-$001008 |
| 0x12B16 | 9 | P:$001200-$001208 |

  Then `JMP $1000`. The rest of the chip after 0x12B37 is data (presets, tables) and is used up to the end.
- A good dump parses so that every section ends exactly where the next one starts.

## Memory map (from the loader init)
| Reg | Value | Meaning |
|---|---|---|
| PCTL | $FF0040 | PLL (10 MHz crystal) |
| AAR0 | $020739 | external SRAM, P+X+Y, $020000-$03FFFF (3x 128Kx8 = 128K x 24) |
| AAR1 | $0406B9 | flash, P+X+Y, byte packing, $040000 window |
| AAR2 | $200332 | DRAM 1Mx16, X+Y, $200000 |
| AAR3 | $800001 | (no spaces enabled) |
| BCR / DCR | $013E81 / $813907 | wait states / DRAM refresh |
| OMR / SR | $000B81 / $800300 | Mode 1 boot, interrupts masked during init |
- Internal P RAM = 3K (P:$0000-$0BFF). TC uses P:$0000-$03D9 (vectors, ISRs, loader). **New code goes at P:$0A00.**
- Internal X/Y RAM: TC keeps its front-panel state at Y:$1D9-$1E1 and queues at Y:$720 and Y:$820 (see FRONT_PROTOCOL.md).
  Our programs use X:$30-$37 (short absolute) for state.

## Ports (loader values)
| Reg | Value | Meaning |
|---|---|---|
| HPCR / HDDR / HDR | $000001 / $00EFFD / $00C5BA | port B = all GPIO (codec control, relays, clock select) |
| PCRC / PRRC | $0005FF / $000EF8 | ESAI pins on; PC9 + PC11 = GPIO |
| TCCR = RCCR | $1C4301 | ESAI clock **slave** (FS64/FS1 come from the board), 2 slots |
| TCR = RCR | $017D00 | network mode, early frame sync |
| SAICR | $000040 | TX/RX synchronous |
| HCSR / HCKR | $0000A8 / $000001 | SHI: SPI slave, 24-bit, mode 1 (the front-panel link) |

## Audio
- **ADC = ESAI RX1** (RCR RE1). RX0 is the digital (S/PDIF) input path. **DAC = ESAI TX1** (TCR TE1).
- SAISR: RFS (first slot of the frame) = bit 6, ROE = 7, **RDF = 8**, TUE = 14, TDE = 15.
- TC's audio ISRs are at P:$95 / P:$D6. $FFFFD0-$FFFFD7 = DAX (S/PDIF out).
- Sample rate is set by the board's clock selects plus the PLL. The switch routines are at P:$27D / P:$292
  (PCTL $F00041 vs $F00047, HDR bits 3/6 = EN_44.1_FS / EN_48_FS).

## J5 (front panel ribbon) facts
- DSP_RESET (J5-16) goes to the DSP reset with a **3.74 k pulldown** (R66) and 100 nF (C40). The DSP only runs when something
  holds it high (stock: the front AVR). SPI_DOWNLOAD (J5-11) high selects SPI boot (Mode 5). Mode-5 SPI boot over J5 never
  answered in testing (MISO stayed floating); J8 is used instead.
