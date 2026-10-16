# Method

1. **Get in through J8.** JTAG -> IDCODE (proves the wiring). OnCE: `DEBUG_REQUEST`, poll the core status bits (OS=11),
   save PDB/PIL, then feed single instructions through OPDBR and read results through OGDB (X:$FFFFFC).
   This is all in `firmware/mone_dev` (`enterDebug`, `exec1`, `exec2`, `onceRead`, `resumeDebug`).
2. **Read anything.** `movep P/X/Y:(r0)+,x:OGDB`, re-sent for every word, with M0 forced linear. Registers: `movep reg,x:OGDB`.
   Peripherals: `movep x:pp,x:OGDB`.
3. **Dump the flash** the same way with AAR1 = $D00409 (the boot ROM's own mapping), two runs, compare, settle any
   difference by repeated reads of just those bytes.
4. **Map it.** `tools/build_app.py` follows the loader and disassembles the app. Grep for peripheral names
   (`TX1`, `RX1`, `HCSR`, `AAR`...) to find init code and ISRs. Confirm against live values read over OnCE.
5. **Write DSP code** as a Python list of words with comments, using `tools/dis56k.py` to print the listing. Check
   every line: the disassembler has already caught a wrong memory-space bit (X vs Y) before it ran.
6. **Load and run.** `mone.py load` (write + readback verify), `mone.py go A00`, `mone.py regs` to see the PC inside our
   code, then listen. To go back to stock: power-cycle.

## Encoding notes
- Every new opcode format was cross-checked against identical instructions in the stock code before first use.
- `MOVE A,X0` (A = 01110) saturates, `MOVE A1,X0` (A1 = 01100) doesn't: use A/B for clipping.
- Short X moves `01dd0ddd`: bit 19 = 0 for X, 1 for Y (`56xx`/`57xx` = A/B to X, `5Exx`/`5Fxx` = Y).
- CMP/CMPM take their register from Table 12-16 (B/A = `000`: `CMP A,B` = `20000D`), ADD/SUB from Table 12-13
  (B/A = `001`: `SUB B,A` = `200014`). `20001D` is MAX A,B, not a compare.
- 12-bit `Jcc`/`JMP` reach only $0000-$0FFF; use the 2-word forms beyond that.
