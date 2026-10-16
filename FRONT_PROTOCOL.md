# M-One front panel <-> DSP protocol (from the flash disassembly; `tools/build_app.py` makes `dumps/app.lst` from your own dump)

Link: J5 SPI. The front AVR (AT90LS8535) is the master; the DSP SHI is a slave, 24-bit words, SPI mode 1 (HCSR=$0000A8, HCKR=$000001,
set at P:$02D7F1, SHI IRQ priority via IPRP bits 2/3). Every transfer is **full duplex**: one 24-bit word each way.

## SHI interrupt (P:~$13A-$215)
On each received word:
1. `Y:$1D9 = HRX` (the word from the AVR).
2. The DSP reply goes into HTX for the NEXT transfer, picked in this order:
   - Y:$1DF if nonzero (a one-shot priority word, e.g. `$D84110`), then cleared
   - else the next entry of the **outgoing queue** Y:$820[256] (read idx Y:$1DE, write idx Y:$1DC, 8-bit wrap)
   - else **`$A00000` = idle / nothing to send**
3. Decode the AVR word by its top byte:
   - **`$DC` = edit wheel**: delta = (W & 7) - ((W >> 8) & 7), i.e. bits 2:0 = clockwise steps, bits 10:8 = counter-clockwise steps.
     Accumulated in Y:$1DA.
   - **`$A0` = AVR idle**: ignored.
   - **anything else** = an event (buttons / knobs / fader), pushed into the **incoming queue** Y:$720[256]
     (write idx Y:$1DB, read idx Y:$1DD). Queue full -> toggles HDR bit 5 (a busy/handshake GPIO).
   - There's also a timer path (TCSR1) that injects `$D10000` as a synthetic message.

## Main loop (P:$027FEA)
- `JSR $02FEB6` pops one event into X:$23B/$23C/$23D = [type][b1][b2] (type = top byte, b1/b2 = the next bytes;
  for `$DC` the wheel delta is split into + / - steps), then `JSR $02E2C8` = the event dispatcher (button/knob codes: still to decode).

## DSP -> front (P:$02FE89)
- Messages are 3 bytes from X:(R0),(R0+1),(R0+2), packed `[cmd][b1][b2]` -> pushed into the outgoing queue. Called from ~13 places in
  P:$02E6A3-$02E842 (display/LED/meter updates).
- Startup (P:$02FEFF): reset all queue indexes, init SHI, then loop sending **`[$A1][$01][$00]`** until it's queued (hello/init to the front).

## What this means for the new OS
- To keep the stock buttons + fader through the AVR, our DSP code has to speak this: answer each SHI word, queue `$A00000` when idle,
  and decode `$DC` wheel words plus event words. Still TODO: decode the dispatcher at P:$02E2C8 to name every button/knob code
  (or just log the raw words live over J8 while pressing buttons).
- Alternative: the ESP reads the front board's switches/encoder directly (no AVR) and talks to our DSP code over J5/J8 in our own format.

## Tested on hardware (2026-10-15)
- With the stock firmware running, the front-panel buttons and edit wheel send **nothing** to the DSP: TC's UI lives in the
  front AVR (AT90LS8535, socketed, "M-ONE FRONT V1.05"). The incoming ring only held TC's own timer tick `$D10000`
  plus one `$DA7700` at boot.
- The DSP -> front stream is a repeating frame `DD0000` + ten `D8 rr vv` register writes (rr = 11, 0E, 06, 07, 06, 0C, 0D x4).
  These are probably front-board display/LED levels (**hypothesis**). Not needed for the new OS.
