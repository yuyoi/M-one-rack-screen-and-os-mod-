// M-One flash dumper over J5 (ESP32-S3 = SPI master, DSP56362 SHI = slave, Mode-5 boot).
// Read-only. All J5-facing pins stay high-Z until a command runs.
// Serial commands (115200, or native USB):
//   t  boot the dumper, sync on the markers, print the first 64 flash bytes as hex
//   d  boot the dumper, stream DUMP_BYTES bytes as binary: "MONEDUMP" u32 len, data, u32 crc32
//   n  normal boot: SPI_DOWNLOAD low + reset pulse (unit boots its own flash), then release pins
//   s  slow SPI (100 kHz)   f  fast SPI (1 MHz)   default 250 kHz

#include "tee.h"          // first: Serial = UART + WiFi TCP port 23
#include <SPI.h>
#include "display.h"
#include "theme.h"         // PS1 heavy-metal look: canvas, pixel font, animations (after display.h)
#include "controls.h"
#include "ota.h"
#include "buttons.h"
#include "menu.h"
#include "face.h"

// ESP32-S3 pins -> J5
const int PIN_SCK   = 12;  // J5-6  SPI_CLK
const int PIN_MOSI  = 11;  // J5-7  SPI_MOSI
const int PIN_MISO  = 13;  // J5-9  SPI_MISO
const int PIN_SS    = 10;  // J5-18 DSP_SS*
const int PIN_RESET = 4;   // J5-16 DSP_RESET (board pull-down: drive low, then HIGH to run)
const int PIN_DL    = 5;   // J5-11 SPI_DOWNLOAD (high = boot from SPI)
// GND -> J5-12 DGND. Nothing else. J5-10/13 carry +/-15 V.

const uint32_t DUMP_BYTES = 524288;  // 512 KB; a smaller chip shows up as mirrored halves
const uint32_t LOAD_ADDR = 0x000100;
const uint32_t DUMPER[] = {
  0x08F4B8, 0xD00409,  // movep #$D00409,x:AAR1
  0x62F400, 0xD00000,  // move  #$D00000,r2
  0x000000, 0x000000,  // nop nop
  0x01918F, 0x000106,  // jclr  #15,x:HCSR,*
  0x07F413, 0xC0FFEE,  // movep #$C0FFEE,x:HTX
  0x01918F, 0x00010A,  // jclr  #15,x:HCSR,*
  0x07F413, 0x123456,  // movep #$123456,x:HTX
  0x07DA84,            // LOOP: movem p:(r2)+,x0
  0x01918F, 0x00010F,  // jclr  #15,x:HCSR,*
  0x04C493,            // movep x0,x:HTX
  0x0C010E,            // jmp   LOOP
};
const uint32_t DUMPER_WORDS = sizeof(DUMPER) / sizeof(DUMPER[0]);  // 19 = $13

uint32_t spiHz = 250000;
uint32_t gapUs = 20;

void releasePins() {
  SPI.end();
  for (int p : {PIN_SCK, PIN_MOSI, PIN_MISO, PIN_SS, PIN_RESET, PIN_DL}) pinMode(p, INPUT);
}

uint32_t xfer24(uint32_t out) {
  digitalWrite(PIN_SS, LOW);
  delayMicroseconds(2);
  uint32_t in = SPI.transfer((out >> 16) & 0xFF);
  in = (in << 8) | SPI.transfer((out >> 8) & 0xFF);
  in = (in << 8) | SPI.transfer(out & 0xFF);
  delayMicroseconds(2);
  digitalWrite(PIN_SS, HIGH);
  delayMicroseconds(gapUs);
  return in;
}

void resetDsp(bool spiBoot) {
  pinMode(PIN_DL, OUTPUT);
  digitalWrite(PIN_DL, spiBoot ? HIGH : LOW);
  pinMode(PIN_RESET, OUTPUT);
  digitalWrite(PIN_RESET, LOW);
  delay(20);
  digitalWrite(PIN_RESET, HIGH);  // drive high: the mainboard PULLS IT DOWN (the front AVR used to hold it high)
  delay(50);
}

// Boots the dumper and syncs on the two markers. True = DSP code is running.
bool bootDumper(bool verbose) {
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  pinMode(PIN_SS, OUTPUT);
  digitalWrite(PIN_SS, HIGH);
  SPI.beginTransaction(SPISettings(spiHz, MSBFIRST, SPI_MODE1));  // SHI reset: CPHA=1 CPOL=0
  resetDsp(true);
  xfer24(DUMPER_WORDS);
  xfer24(LOAD_ADDR);
  for (uint32_t i = 0; i < DUMPER_WORDS; i++) xfer24(DUMPER[i]);
  delay(2);
  uint32_t prev = 0;
  for (int i = 0; i < 32; i++) {
    uint32_t w = xfer24(0);
    if (verbose) Serial.printf("  sync %2d: %06X\n", i, w);
    if (prev == 0xC0FFEE && w == 0x123456) return true;
    prev = w;
  }
  return false;
}

uint32_t crc32Update(uint32_t crc, uint8_t b) {
  crc ^= b;
  for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320 & (0 - (crc & 1)));
  return crc;
}

void cmdTest() {
  Serial.printf("boot @ %lu Hz\n", spiHz);
  if (!bootDumper(true)) { Serial.println("NO SYNC (markers not seen)"); releasePins(); return; }
  Serial.println("SYNC OK - dumper running");
  for (int i = 0; i < 64; i++) {
    uint32_t w = xfer24(0);
    Serial.printf("%02X%s", w & 0xFF, (i % 16 == 15) ? "\n" : " ");
  }
  SPI.endTransaction();
  releasePins();
}

void cmdDump() {
  if (!bootDumper(false)) { Serial.print("NOSYNC"); releasePins(); return; }
  Serial.write((const uint8_t *)"MONEDUMP", 8);
  Serial.write((const uint8_t *)&DUMP_BYTES, 4);
  uint8_t buf[256];
  uint32_t crc = 0xFFFFFFFF;
  for (uint32_t i = 0; i < DUMP_BYTES; i += sizeof(buf)) {
    for (size_t j = 0; j < sizeof(buf); j++) {
      buf[j] = xfer24(0) & 0xFF;
      crc = crc32Update(crc, buf[j]);
    }
    Serial.write(buf, sizeof(buf));
  }
  crc = ~crc;
  Serial.write((const uint8_t *)&crc, 4);
  SPI.endTransaction();
  releasePins();
}

void cmdNormal() {
  releasePins();
  resetDsp(false);
  releasePins();
  Serial.println("normal boot done, pins released");
}

// Reads each J5 line with weak pull-up then pull-down. Same both times = board drives it.
void probeLine(const char *name, int pin) {
  pinMode(pin, INPUT_PULLUP);
  delay(5);
  int up = digitalRead(pin);
  pinMode(pin, INPUT_PULLDOWN);
  delay(5);
  int dn = digitalRead(pin);
  pinMode(pin, INPUT);
  Serial.printf("  %-6s GPIO%-2d  pullup=%d pulldown=%d  -> %s\n", name, pin, up, dn,
                up == dn ? (up ? "driven HIGH" : "driven LOW") : "floating");
}

void cmdProbe() {
  releasePins();
  Serial.println("idle (nothing driven by ESP):");
  probeLine("CLK", PIN_SCK);
  probeLine("MOSI", PIN_MOSI);
  probeLine("MISO", PIN_MISO);
  probeLine("SS", PIN_SS);
  probeLine("RESET", PIN_RESET);
  probeLine("DL", PIN_DL);
  Serial.println("after reset pulse with DL high:");
  resetDsp(true);
  probeLine("RESET", PIN_RESET);
  probeLine("MISO", PIN_MISO);
  releasePins();
}

// Boots TC's own firmware from flash (DL low), HOLDS reset high, reads a few SHI words.
// The DSP keeps running until 'x' (release) or power-off, so audio can be checked meanwhile.
void cmdRunStock() {
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  pinMode(PIN_SS, OUTPUT);
  digitalWrite(PIN_SS, HIGH);
  SPI.beginTransaction(SPISettings(spiHz, MSBFIRST, SPI_MODE1));
  resetDsp(false);
  delay(1500);  // let the app boot from flash
  Serial.println("stock app running, reading SHI:");
  for (int i = 0; i < 8; i++) Serial.printf("  %06X\n", xfer24(0));
  SPI.endTransaction();
  Serial.println("reset held HIGH - check audio now; send x to release");
}

// Boots the dumper, then checks whether MISO becomes driven while SS is held low.
void cmdMisoCheck() {
  bool ok = bootDumper(false);
  Serial.printf("boot sync: %s\n", ok ? "OK" : "none");
  SPI.endTransaction();
  SPI.end();
  pinMode(PIN_SS, OUTPUT);
  digitalWrite(PIN_SS, HIGH);
  probeLine("MISO ss=H", PIN_MISO);
  digitalWrite(PIN_SS, LOW);
  delay(2);
  probeLine("MISO ss=L", PIN_MISO);
  digitalWrite(PIN_SS, HIGH);
  releasePins();
}

// Software bisect: both RESET polarities x both SPI_DOWNLOAD levels.
// For each: reset, try the Mode-5 boot + marker sync, then check MISO with SS low.
bool resetActiveHigh = false;

void resetPol(bool activeHigh, bool dl) {
  pinMode(PIN_DL, OUTPUT);
  digitalWrite(PIN_DL, dl ? HIGH : LOW);
  pinMode(PIN_RESET, OUTPUT);
  digitalWrite(PIN_RESET, activeHigh ? HIGH : LOW);   // assert
  delay(20);
  digitalWrite(PIN_RESET, activeHigh ? LOW : HIGH);   // deassert and hold
  delay(50);
}

void cmdSweep() {
  for (int pol = 0; pol < 2; pol++) {
    for (int dl = 1; dl >= 0; dl--) {
      Serial.printf("== reset active-%s, DL=%d\n", pol ? "HIGH" : "LOW", dl);
      SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
      pinMode(PIN_SS, OUTPUT);
      digitalWrite(PIN_SS, HIGH);
      SPI.beginTransaction(SPISettings(spiHz, MSBFIRST, SPI_MODE1));
      resetPol(pol, dl);
      if (dl) {
        xfer24(DUMPER_WORDS);
        xfer24(LOAD_ADDR);
        for (uint32_t i = 0; i < DUMPER_WORDS; i++) xfer24(DUMPER[i]);
        delay(2);
      } else {
        delay(1500);
      }
      Serial.print("  words:");
      for (int i = 0; i < 6; i++) Serial.printf(" %06X", xfer24(0));
      Serial.println();
      SPI.endTransaction();
      SPI.end();
      pinMode(PIN_SS, OUTPUT);
      digitalWrite(PIN_SS, LOW);
      delay(2);
      probeLine("MISO ss=L", PIN_MISO);
      digitalWrite(PIN_SS, HIGH);
    }
  }
  releasePins();
}

// ---- J8 JTAG (DSP56362 OnCE port). J8 odd row: 1 TCK, 3 TDI, 5 TMS, 7 TDO, 9 TRST*.
// TCK/TDI/TMS kept their J5 wires (black, white, gray); TRST stays on 4 (green), TDO (purple) moved 5 -> 10 (blue = GND on J8-2).
const int PIN_TCK = 12, PIN_TDI = 11, PIN_TMS = 13, PIN_TDO = 10, PIN_TRST = 4;  // 5/6/7 = pots

void cmdJtagProbe() {  // inputs only, safe on any wiring mistake
  Serial.println("J8 lines (nothing driven by ESP):");
  probeLine("TCK", PIN_TCK);
  probeLine("TDI", PIN_TDI);
  probeLine("TMS", PIN_TMS);
  probeLine("TDO", PIN_TDO);
  probeLine("TRST", PIN_TRST);
}

int jtagClock(int tms, int tdi) {  // TDO is sampled before the rising edge
  digitalWrite(PIN_TMS, tms);
  digitalWrite(PIN_TDI, tdi);
  delayMicroseconds(5);
  int tdo = digitalRead(PIN_TDO);
  digitalWrite(PIN_TCK, HIGH);
  delayMicroseconds(5);
  digitalWrite(PIN_TCK, LOW);
  delayMicroseconds(5);
  return tdo;
}

// Read the JTAG IDCODE (TAP only: the DSP core keeps running, no audio gap). Pins are released after.
uint32_t jtagReadId() {
  pinMode(PIN_TCK, OUTPUT); digitalWrite(PIN_TCK, LOW);
  pinMode(PIN_TMS, OUTPUT);
  pinMode(PIN_TDI, OUTPUT);
  pinMode(PIN_TDO, INPUT_PULLUP);
  pinMode(PIN_TRST, OUTPUT); digitalWrite(PIN_TRST, HIGH);  // TAP enabled
  delay(2);
  for (int i = 0; i < 6; i++) jtagClock(1, 0);  // Test-Logic-Reset: IDCODE is selected
  jtagClock(0, 0);                              // Run-Test/Idle
  jtagClock(1, 0);                              // Select-DR
  jtagClock(0, 0);                              // Capture-DR
  jtagClock(0, 0);                              // Shift-DR
  uint32_t id = 0;
  for (int i = 0; i < 32; i++) id |= (uint32_t)jtagClock(i == 31, 0) << i;
  jtagClock(1, 0);                              // Update-DR
  jtagClock(0, 0);                              // Idle
  for (int p : {PIN_TCK, PIN_TMS, PIN_TDI, PIN_TDO, PIN_TRST}) pinMode(p, INPUT);
  return id;
}

void cmdJtagId() {
  uint32_t id = jtagReadId();
  Serial.printf("JTAG IDCODE = %08lX  (bit0 must be 1; Motorola mfr id 0x00E -> low 12 bits 01D)\n", id);
  { char b[16]; snprintf(b, sizeof b, "%08lX", id); displayRow(0, "IDCODE", b, (id & 0xFFF) == 0x01D ? C_GRN : C_RED); }
}

// Core status without halting: IR capture bits 3:2 = OS1:OS0, and OSCR via ENABLE_ONCE + READ_OSCR.
void cmdStatus() {
  jPinsUp();
  uint8_t st = jIR(0x6);                    // ENABLE_ONCE (constants are defined further down)
  uint32_t oscr = onceRead(0x80);           // READ_OSCR
  uint8_t st2 = jIR(0x2);  // back to IDCODE (no debug request)
  jPinsDown();
  Serial.printf("STATUS ircap=%X OS=%d%d oscr=%06lX ircap2=%X\n", st, (st >> 3) & 1, (st >> 2) & 1, oscr, st2);
}

// DSP watch: the power button is a DPDT. Pole A ties J5-16 (DSP reset) to J5-17 (3V3) = DSP runs; pole B closes
// GPIO3 to GND in the OTHER position = DSP held in reset. So GPIO3 HIGH (internal pullup, also when unwired) = DSP on,
// LOW = off -> the face sleeps. (JTAG can't tell: the IDCODE answers even while the DSP is held in reset.)
// 3 equal reads 50 ms apart = debounced.
const int PIN_DSP_SENSE = 3;
uint32_t dspWatchHold = 0;                      // kept for the serial loop; not needed by the pin read
void dspWatch() {
  static uint32_t last = 0;
  static int same = 0;
  static bool init = false, prev = true;
  if (!init) { pinMode(PIN_DSP_SENSE, INPUT_PULLUP); init = true; }
  if (millis() - last < 50) return;
  last = millis();
  bool on = digitalRead(PIN_DSP_SENSE) == HIGH;
  same = on == prev ? same + 1 : 0;
  prev = on;
  if (same >= 3 && on != dspAwake) {
    dspAwake = on;
    Serial.printf("DSP %s (power button)\n", on ? "on" : "off");
    if (on) faceActivity(0);                    // wake up with it
  }
}

// ---- OnCE debug layer (DSP56300 Family Manual ch.7). LSB first, 8-bit commands + 24-bit data.
// OCR = R/W(7) GO(6) EX(5) RS(4:0). IR capture: bit0=1 bit1=0 bit2=OS0 bit3=OS1; OS=11 -> Debug mode.
const uint8_t IR_DEBUG_REQUEST = 0x7, IR_ENABLE_ONCE = 0x6;
const uint8_t OC_READ_OSCR = 0x80, OC_READ_GDB = 0x89, OC_READ_PDB = 0x8A, OC_READ_PIL = 0x8B;
const uint8_t OC_WRITE_PDB = 0x0A, OC_WRITE_PDB_GO = 0x4A, OC_WRITE_PDB_GO_EX = 0x6A, OC_NOSEL_GO = 0x5F;
const uint32_t X_OGDB = 0xFFFFFC;

int jclk(int tms, int tdi) {  // fast version of jtagClock
  digitalWrite(PIN_TMS, tms);
  digitalWrite(PIN_TDI, tdi);
  delayMicroseconds(1);
  int tdo = digitalRead(PIN_TDO);
  digitalWrite(PIN_TCK, HIGH);
  delayMicroseconds(1);
  digitalWrite(PIN_TCK, LOW);
  return tdo;
}
uint32_t jShift(uint32_t v, int n) {  // in Shift-xR; last bit exits to Exit1
  uint32_t out = 0;
  for (int i = 0; i < n; i++) out |= (uint32_t)jclk(i == n - 1, (v >> i) & 1) << i;
  return out;
}
uint8_t jIR(uint8_t ins) {  // Idle -> shift 4-bit IR -> Idle, returns captured status
  jclk(1, 0); jclk(1, 0); jclk(0, 0); jclk(0, 0);
  uint8_t st = jShift(ins, 4);
  jclk(1, 0); jclk(0, 0);
  return st;
}
uint32_t jDR(uint32_t v, int n) {  // Idle -> shift n-bit DR -> Idle
  jclk(1, 0); jclk(0, 0); jclk(0, 0);
  uint32_t o = jShift(v, n);
  jclk(1, 0); jclk(0, 0);
  return o;
}
void jPinsUp() {
  pinMode(PIN_TCK, OUTPUT); digitalWrite(PIN_TCK, LOW);
  pinMode(PIN_TMS, OUTPUT);
  pinMode(PIN_TDI, OUTPUT);
  pinMode(PIN_TDO, INPUT_PULLUP);
  pinMode(PIN_TRST, OUTPUT); digitalWrite(PIN_TRST, HIGH);
  delay(2);
  for (int i = 0; i < 6; i++) jclk(1, 0);
  jclk(0, 0);  // Run-Test/Idle
}
void jPinsDown() { for (int p : {PIN_TCK, PIN_TMS, PIN_TDI, PIN_TDO, PIN_TRST}) pinMode(p, INPUT); }

bool waitDebug() {
  for (int i = 0; i < 200; i++)
    if ((jIR(IR_ENABLE_ONCE) & 0xC) == 0xC) return true;
  return false;
}
uint32_t onceRead(uint8_t cmd) { jDR(cmd, 8); return jDR(0, 24); }

// The kernel's output envelope (dsp/os.py writes it to OGDB every frame). OnCE registers can be read while the core
// runs (DSP56300FM ch. 7: "accessible even when the chip operates in Normal mode"), so this does NOT halt the DSP:
// no audio blip, fine at the face's 25 fps.
uint32_t dspLevel() {
  if (!dspAwake) return 0;
  jPinsUp();
  jIR(IR_ENABLE_ONCE);
  uint32_t v = onceRead(OC_READ_GDB);
  jPinsDown();
  return v & 0xFFFFFF;
}
bool exec1(uint32_t op) { jDR(OC_WRITE_PDB_GO, 8); jDR(op, 24); return waitDebug(); }
bool exec2(uint32_t op, uint32_t ext) {
  jDR(OC_WRITE_PDB, 8); jDR(op, 24);
  jDR(OC_WRITE_PDB_GO, 8); jDR(ext, 24);
  return waitDebug();
}
uint32_t savedPdb, savedPil;

bool enterDebug(bool verbose) {
  jPinsUp();
  uint8_t st = jIR(IR_DEBUG_REQUEST);
  if (verbose) Serial.printf("IR capture before halt: %X (OS=%d%d)\n", st, (st >> 3) & 1, (st >> 2) & 1);
  if (!waitDebug()) {
    if (verbose) Serial.println("core did NOT enter debug mode");
    jIR(0x2);  // IDCODE: take DEBUG_REQUEST back out of the IR, or a DSP held in reset halts the moment it is released
    return false;
  }
  savedPdb = onceRead(OC_READ_PDB);
  savedPil = onceRead(OC_READ_PIL);
  if (verbose) Serial.printf("HALTED. PDB=%06lX PIL=%06lX OSCR=%06lX\n", savedPdb, savedPil, onceRead(OC_READ_OSCR));
  return true;
}
void resumeDebug() {  // Manual 7.2.7.7: restore pipeline and exit
  jDR(OC_WRITE_PDB, 8); jDR(savedPil, 24);
  jDR(OC_WRITE_PDB_GO_EX, 8); jDR(savedPdb, 24);
}

// Halt, read a few registers through OGDB, resume. Only OGDB is touched, so the stock app keeps running.
void cmdOnceRegs() {
  if (!enterDebug(true)) { jPinsDown(); return; }
  struct { const char *name; uint32_t op, ext; } r[] = {
    {"OMR ", 0x08FA3C, 0},          // movep omr,x:$fffffc
    {"SR  ", 0x08F93C, 0},          // movep sr,x:$fffffc
    {"AAR1", 0x0870B8, X_OGDB},     // movep x:$fffff8,x:$fffffc
    {"BCR ", 0x0870BB, X_OGDB},     // movep x:$fffffb,x:$fffffc
    {"HCSR", 0x077011, X_OGDB},     // movep x:$ffff91,x:$fffffc
    {"HCKR", 0x077010, X_OGDB},     // movep x:$ffff90,x:$fffffc
  };
  for (auto &e : r) {
    bool ok = e.ext ? exec2(e.op, e.ext) : exec1(e.op);
    uint32_t v = onceRead(OC_READ_GDB);
    Serial.printf("  %s = %06lX%s\n", e.name, v, ok ? "" : "  (no debug ack!)");
    int row = 1 + (&e - r);
    if (row <= 4) { char b[12]; snprintf(b, sizeof b, "$%06lX", v); displayRow(row, e.name, b, ok ? C_YEL : C_RED); }
  }
  resumeDebug();
  Serial.println("resumed");
  displayStatus("DSP resumed", C_GRN);
  jPinsDown();
}

// Flash dump through OnCE: AAR1 like the boot ROM ($D00409, byte per address on D7-0),
// r0 = $D00000, then re-execute "movep p:(r0)+,x:OGDB" once per byte. Leaves the DSP halted.
void cmdOnceDump() {
  if (!enterDebug(false)) { Serial.print("NODEBUG"); jPinsDown(); return; }
  exec2(0x08F4B8, 0xD00409);  // movep #$D00409,x:AAR1
  exec2(0x05F420, 0xFFFFFF);  // movec #$FFFFFF,m0  (linear: the app leaves modulo values in M0!)
  exec2(0x60F400, 0xD00000);  // move #$D00000,r0
  Serial.write((const uint8_t *)"MONEDUMP", 8);
  Serial.write((const uint8_t *)&DUMP_BYTES, 4);
  uint8_t buf[256];
  uint32_t crc = 0xFFFFFFFF;
  bool first = true;
  for (uint32_t i = 0; i < DUMP_BYTES; i += sizeof(buf)) {
    for (size_t j = 0; j < sizeof(buf); j++) {
      exec1(0x08D87C);  // movep p:(r0)+,x:$fffffc  (always re-sent: NOSEL+GO let read data into the PIL)

      buf[j] = onceRead(OC_READ_GDB) & 0xFF;
      crc = crc32Update(crc, buf[j]);
    }
    Serial.write(buf, sizeof(buf));
  }
  crc = ~crc;
  Serial.write((const uint8_t *)&crc, 4);
  jPinsDown();
}

// Program loader over OnCE: "L<base6hex> w w w ...\n" (6-hex words). Writes P memory, verifies, stays halted.
void cmdLoad() {
  String ln = Serial.readStringUntil('\n');
  ln.trim();
  if (ln.length() < 6) { Serial.println("LOAD BADARGS"); return; }
  uint32_t base = strtoul(ln.substring(0, 6).c_str(), 0, 16);
  static uint32_t w[1024];                // autotune.hex is 710 words
  int n = 0, pos = 6;
  while (pos < (int)ln.length() && n < 1024) {
    while (pos < (int)ln.length() && ln[pos] == ' ') pos++;
    if (pos >= (int)ln.length()) break;
    w[n++] = strtoul(ln.substring(pos, pos + 6).c_str(), 0, 16);
    pos += 6;
  }
  if (!enterDebug(false)) { Serial.println("LOAD NODEBUG"); jPinsDown(); return; }
  exec2(0x05F420, 0xFFFFFF);             // movec #$FFFFFF,m0
  exec2(0x60F400, base);                 // move #base,r0
  for (int i = 0; i < n; i++) {
    exec2(0x44F400, w[i]);               // move #w,x0
    exec1(0x075884);                     // movem x0,p:(r0)+
  }
  exec2(0x60F400, base);
  int bad = 0;
  for (int i = 0; i < n; i++) {
    exec1(0x08D87C);                     // movep p:(r0)+,x:OGDB
    uint32_t v = onceRead(OC_READ_GDB);
    if (v != w[i]) { bad++; Serial.printf("  verify P:%06lX wrote %06lX read %06lX\n", base + i, w[i], v); }
  }
  Serial.printf("LOADED %d words at P:%06lX, verify %s (DSP halted)\n", n, base, bad ? "FAIL" : "OK");
  char b[24]; snprintf(b, sizeof b, "%d w @%04lX %s", n, base, bad ? "BAD" : "ok");
  displayRow(4, "LOAD", b, bad ? C_RED : C_GRN);
  jPinsDown();
}

// "G<addr6hex>\n": jump the halted DSP to addr and leave debug mode (manual 7.2.7.8).
void cmdGo() {
  String ln = Serial.readStringUntil('\n');
  uint32_t addr = strtoul(ln.substring(0, 6).c_str(), 0, 16);
  jPinsUp();
  if (!waitDebug()) { Serial.println("GO: DSP not in debug mode"); jPinsDown(); return; }
  jDR(OC_WRITE_PDB, 8); jDR(0x0AF080, 24);   // JMP opcode into the instruction latch
  jDR(0x6C, 8); jDR(addr, 24);               // write PDB GO-TO register, GO+EX
  Serial.printf("GO P:%06lX\n", addr);
  char b[16]; snprintf(b, sizeof b, "run @%04lX", addr);
  displayStatus(b, C_YEL);
  jPinsDown();
}

// Live write of one X short-address param (X:$00-$3F) while the DSP runs: halt, save X0,
// move #v,x0 ; move x0,x:$aa, restore X0, resume. Used by the menu.
// Write n X-short words ($00-$3F) in ONE debug halt (one tiny audio gap however many values)
bool onceWriteXMany(const uint8_t *aa, const uint32_t *value, int n) {
  if (!dspAwake) return false;              // power switch off: the DSP is held in reset, don't even ask
  if (!enterDebug(false)) { jPinsDown(); return false; }
  exec1(0x08C43C);                          // movep x0,x:OGDB
  uint32_t savedX0 = onceRead(OC_READ_GDB);
  for (int i = 0; i < n; i++) {
    exec2(0x44F400, value[i] & 0xFFFFFF);   // move #value,x0
    exec1(0x440000 | ((uint32_t)(aa[i] & 0x3F) << 8));  // move x0,x:$aa
  }
  exec2(0x44F400, savedX0);                 // restore x0
  resumeDebug();
  jPinsDown();
  return true;
}

bool onceWriteX(uint8_t aa, uint32_t value) { return onceWriteXMany(&aa, &value, 1); }

// Long-address X writes (any X:$0000-$FFFF, e.g. the effect param blocks at X:$0210+): move #v,x0 ; move x0,x:$aaaa.
// All n values in one halt, X0 saved and restored like the short writes.
bool onceWriteXLong(const uint16_t *aa, const uint32_t *value, int n) {
  if (!dspAwake) return false;
  if (!enterDebug(false)) { jPinsDown(); return false; }
  exec1(0x08C43C);                          // movep x0,x:OGDB
  uint32_t savedX0 = onceRead(OC_READ_GDB);
  for (int i = 0; i < n; i++) {
    exec2(0x44F400, value[i] & 0xFFFFFF);   // move #value,x0
    exec2(0x447000, aa[i]);                 // move x0,x:$aaaa
  }
  exec2(0x44F400, savedX0);                 // restore x0
  resumeDebug();
  jPinsDown();
  return true;
}

// Read X short addresses in one halt (saves/restores X0 like the writes)
bool onceReadXMany(const uint8_t *aa, uint32_t *value, int n) {
  if (!dspAwake) return false;
  if (!enterDebug(false)) { jPinsDown(); return false; }
  exec1(0x08C43C);                          // movep x0,x:OGDB
  uint32_t savedX0 = onceRead(OC_READ_GDB);
  for (int i = 0; i < n; i++) {
    exec1(0x448000 | ((uint32_t)(aa[i] & 0x3F) << 8));   // move x:$aa,x0
    exec1(0x08C43C);                        // movep x0,x:OGDB
    value[i] = onceRead(OC_READ_GDB);
  }
  exec2(0x44F400, savedX0);                 // restore x0
  resumeDebug();
  jPinsDown();
  return true;
}

// Read X long addresses ($0040-$FFFF) in one halt, like onceReadXMany
bool onceReadXLong(const uint16_t *aa, uint32_t *value, int n) {
  if (!dspAwake) return false;
  if (!enterDebug(false)) { jPinsDown(); return false; }
  exec1(0x08C43C);                          // movep x0,x:OGDB
  uint32_t savedX0 = onceRead(OC_READ_GDB);
  for (int i = 0; i < n; i++) {
    exec2(0x44F000, aa[i]);                 // move x:$aaaa,x0
    exec1(0x08C43C);                        // movep x0,x:OGDB
    value[i] = onceRead(OC_READ_GDB);
  }
  exec2(0x44F400, savedX0);                 // restore x0
  resumeDebug();
  jPinsDown();
  return true;
}

// Live P-memory dump over OnCE: "P<start6hex><count6hex>\n". Saves/restores R0, resumes the DSP.
// Frame: "MONEDUMP" u32 bytes, 3*count bytes (24-bit words, little-endian), u32 crc32.
void cmdOnceMem(uint32_t readOp);
void cmdOnceP() { cmdOnceMem(0x08D87C); }
void cmdOnceX() { cmdOnceMem(0x08D8BC); }
void cmdOnceY() { cmdOnceMem(0x08D8FC); }
void cmdOnceMem(uint32_t readOp) {
  char line[16] = {0};
  size_t n = Serial.readBytesUntil('\n', line, sizeof(line) - 1);
  if (n < 12) { Serial.print("BADARGS"); return; }
  char a[7] = {0}, c[7] = {0};
  memcpy(a, line, 6); memcpy(c, line + 6, 6);
  uint32_t start = strtoul(a, 0, 16), count = strtoul(c, 0, 16);
  if (!enterDebug(false)) { Serial.print("NODEBUG"); jPinsDown(); return; }
  exec1(0x08D03C);                       // movep r0,x:OGDB
  uint32_t savedR0 = onceRead(OC_READ_GDB);
  exec1(0x08E03C);                       // movep m0,x:OGDB
  uint32_t savedM0 = onceRead(OC_READ_GDB);
  exec2(0x05F420, 0xFFFFFF);             // movec #$FFFFFF,m0 (linear addressing)
  exec2(0x60F400, start);                // move #start,r0
  uint32_t bytes = count * 3;
  Serial.write((const uint8_t *)"MONEDUMP", 8);
  Serial.write((const uint8_t *)&bytes, 4);
  uint32_t crc = 0xFFFFFFFF;
  for (uint32_t i = 0; i < count; i++) {
    exec1(readOp);                       // movep [P|X|Y]:(r0)+,x:OGDB (re-sent every word)

    uint32_t v = onceRead(OC_READ_GDB);
    uint8_t b[3] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16)};
    for (int k = 0; k < 3; k++) crc = crc32Update(crc, b[k]);
    Serial.write(b, 3);
  }
  crc = ~crc;
  Serial.write((const uint8_t *)&crc, 4);
  exec2(0x60F400, savedR0);              // restore r0
  exec2(0x05F420, savedM0);              // restore m0
  resumeDebug();
  jPinsDown();
}

void setup() {
  releasePins();
  Serial.begin(115200);
  delay(500);
  Serial.println("M-One dev tool ready: j=id o=regs D=flash dump P=pmem L=load G=go F=fx page i=system page K=learn buttons W=wifi");
  displayBegin();
  if (th::begin()) th::bootSplash(1500);          // spinning low-poly logo + flame progress bar
  controlsBegin();
  wifiStart();
  faceBegin();
  btnLoad();
  pinMode(PIN_DSP_SENSE, INPUT_PULLUP);
  delay(5);
  dspAwake = digitalRead(PIN_DSP_SENSE) == HIGH;  // power switch state before any JTAG
  uiAdoptDsp();                                   // ESP rebooted (OTA)? show what the DSP is playing
  if (btnMapped()) uiShow(); else btnLearnStart();
}

void loop() {
  Tee.poll();
  controlsTick();
  otaTick();
  faceTick();
  uiTick();
  uiAnimTick();                                   // keeps the visible page animated
  dspWatch();
  if (!Serial.available()) return;
  char c = Serial.read();
  dspWatchHold = millis() + 10000;
  if (c > ' ' && !strchr("iKEV[]-=FTUAa", c)) liveOn = false;  // a command owns the screen rows until 'i'
  switch (c) {
    case 't': case 'd': case 'n': case 'p': case 'r': case 'm': case 'w':  // J5 tools: retired, GPIO 5 is a pot now
      Serial.println("J5 tools retired (GPIO 5 = pot)"); break;
    case 'x': releasePins(); Serial.println("released"); break;
    case 'i': uiPage = PAGE_SYS; uiShow(); break;
    case 'K': btnLearnStart(); break;
    case 'S': cmdStatus(); break;
    case 'V': cmdValues(); Serial.printf("VALUES dsp-sense GPIO3 = %s\n", digitalRead(PIN_DSP_SENSE) ? "HIGH (on)" : "LOW (off)");
              Serial.printf("VALUES wifi %d dBm\n", WiFi.RSSI());
              Serial.printf("VALUES menu mode=%d fx1=%d fx2=%d bypass=%d/%d\n", menu.mode, menu.fx1, menu.fx2, menu.byp1, menu.byp2);
              Serial.printf("VALUES ui frame %lu ms\n", (unsigned long)uiLastPushMs);
              break;
    case 'T': testStart(); Serial.println("button test page (R2 twice on the panel = exit)"); break;
    case 'A': Serial.printf("LEVEL %06lX\n", dspLevel()); break;   // output envelope (no halt)
    case 'U':
      if (uiPushAll()) Serial.printf("PUSHED mode=%d fx1=%d fx2=%d bypass=%d/%d\n", menu.mode, menu.fx1, menu.fx2, menu.byp1, menu.byp2);
      else Serial.println("PUSH failed: DSP not answering");
      break;
    case 'W': cmdWifi(); break;
    case 'E': encLog = !encLog; liveOn = true; Serial.println(encLog ? "enc log on" : "enc log off"); break;
    case 'q': cmdJtagProbe(); break;
    case 'j': cmdJtagId(); break;
    case 'o': cmdOnceRegs(); break;
    case 'D': cmdOnceDump(); break;
    case 'P': cmdOnceP(); break;
    case 'X': cmdOnceX(); break;
    case 'Y': cmdOnceY(); break;
    case 'L': cmdLoad(); break;
    case 'G': cmdGo(); break;
    case 'F': menuDraw(); break;
    case 'a': ampCmd(Serial.readStringUntil('\n').c_str()); break;     // AMP words for given settings (menu.h)
    case '[': case ']': case '-': case '=': menuKey(c); break;
    case '#': liveOn = true; uiPage = PAGE_PRESET; presetLevel = 0; uiShow(); break;   // PRESET page
    case '<': case '>':                                                    // previous / next preset (loads at rest)
      liveOn = true; uiPage = PAGE_PRESET; presetLevel = 0; presetKnob(c == '>' ? 1 : -1); uiShow(); break;
    case 'M': displayToggleMode(); Serial.println("spi mode toggled"); break;
    case 'c':  // screen test: backlight blink + solid fills
      Serial.println("screen test");
      for (int k = 0; k < 3; k++) { backlight(false); delay(300); backlight(true); delay(300); }
      tft.fillScreen(0xFF0000); delay(700); tft.fillScreen(0x00FF00); delay(700); tft.fillScreen(0x0000FF); delay(700);
      uiShow();
      Serial.println("screen test done");
      break;
    case 's': spiHz = 100000; Serial.println("SPI 100 kHz"); break;
    case 'f': spiHz = 1000000; Serial.println("SPI 1 MHz"); break;
  }
}
