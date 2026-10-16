// M-One OS UI: pages on the front controls; FX settings go live to the DSP kernel (dsp/os.py) over J8.
// Drawn with theme.h (PS1 heavy-metal look): every page renders itself into the 120x120 canvas from the current state,
// and uiAnimTick redraws it ~9x a second (faster while the rows fly in) so the lava, flames and selection shimmer move.
// Buttons by position (buttons.h):
//   T1 = FX page   T2 = TUNE page   T3 = SYSTEM page (live inputs, WiFi)   T5 = EDIT (the effect's own settings)
//   T6 / B6 = cursor up / down    encoder = change the selected value    R1 / B4 / B5 = enter (value +1)    R2 = back to FX
//   B1 / B2 = bypass FX1 / FX2 (toggle, works on any page)
//   SYSTEM page + enter = BUTTON TEST page (every button only lights its box there; R2 twice = back to FX)
// Serial keys from the PC do the same: '[' ']' cursor, '-' '=' value, 'F' FX page, 'T' button test.
#pragma once

bool onceWriteX(uint8_t aa, uint32_t value);  // in the .ino
bool onceWriteXMany(const uint8_t *aa, const uint32_t *value, int n);
bool onceReadXMany(const uint8_t *aa, uint32_t *value, int n);
bool onceWriteXLong(const uint16_t *aa, const uint32_t *value, int n);

enum { PAGE_FX, PAGE_TUNE, PAGE_SYS, PAGE_TEST, PAGE_EDIT };
int uiPage = PAGE_FX;

static const char *MODE_NAMES[] = {"SINGLE", "DOUBLE", "DBL-SINGLE"};
static const char *FX_NAMES[] = {"CLEAN", "HEAVY", "REVERSE", "COMP", "TUNE", "VOX", "AMP", "RADIO", "FORMANT", "OCTAVE"};
static const char *FX_SHORT[] = {"CLN", "HVY", "REV", "CMP", "TUNE", "VOX", "AMP", "RAD", "FMT", "OCT"};   // DOUBLE routing line
static const bool FX_PEDAL[] = {false, true, true, true, false, false, true, false, false, false};   // PEDAL: mock pedal idle
static const uint32_t FX_COL[] = {0xFF7000, 0xFF7000, 0x963CDC, 0x2E8BFF, 0xFFCC00, 0xE6AA28, 0xE82010, 0xAA4614,
                                  0xE82010, 0x963CDC};                                   // pedal colours
static const char *KEY_NAMES[] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
static const char *SCALE_NAMES[] = {"CHROMATIC", "MAJOR", "MINOR"};
static const int N_MODES = 3, N_FX = 10;
static const uint8_t SCALE_STEPS[3][12] = {
  {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11},  // chromatic
  {0, 2, 4, 5, 7, 9, 11, 0, 0, 0, 0, 0},   // major (7 used)
  {0, 2, 3, 5, 7, 8, 10, 0, 0, 0, 0, 0},   // natural minor (7 used)
};
static const int SCALE_LEN[3] = {12, 7, 7};

struct MenuState {
  int mode = 0, fx1 = 0, fx2 = 2;  // boot state: CLEAN (HEAVY is +60 dB: a wall of noise on a live mic)
  bool byp1 = false, byp2 = false;
  int key = 0, scale = 0, speed = 6;  // speed 6 ~ the DSP default (0.002 per sample)
  int cursor = 0;                  // row on the FX / TUNE page
} menu;

static int wrapv(int v, int n) { return ((v % n) + n) % n; }

bool rowsVisible() { return liveOn && !faceOn && uiPage == PAGE_SYS && learnIdx < 0; }

// ---- render state: status line, dirty flag, page-open time (fly-in), live input values for SYSTEM
bool uiDirty = true;
static uint32_t pageT0 = 0;
static int lastPage = -1;
static char uiStat[32] = "";
static uint32_t uiStatCol = th::YELLOW, uiStatT = 0;
int sysMv[5] = {0, 0, 0, 0, 0};             // pots 1-3, ladders 1-2 (mV), set by controlsTick
uint32_t uiLastPushMs = 0;                  // how long the last frame took (serial 'V')

// Status messages show for 2.5 s, then the page's own hint comes back
void displayStatus(const char *line, uint32_t col) {
  snprintf(uiStat, sizeof uiStat, "%s", line);
  uiStatCol = col;
  uiStatT = millis();
  if ((!liveOn || learnIdx >= 0) && th::ready) { th::status(uiStat, col); th::present(); }   // serial / OTA / learn screen
  else uiDirty = true;
}

void displayRow(int row, const char *key, const char *val, uint32_t col) { uiDirty = true; }   // SYSTEM draws live values

static void statusOr(const char *hint) {
  bool fresh = uiStat[0] && millis() - uiStatT < 2500;
  th::status(fresh ? uiStat : hint, fresh ? uiStatCol : th::YELLOW);
}

// Dark ember backdrop between the header and the status bar
static void backdrop() {
  th::cv.fillScreen(th::BLACK);
  for (int y = 23; y < 108; y++) th::cv.drawFastHLine(0, y, 120, th::p15(th::mix(th::BLACK, th::ASH, (y - 23) / 85.0f)));
}

// ---- Button test page: green = has worked, yellow = latest press, grey = not seen yet. Shows where the latest
// press came from (GPIO or ladder mV, "??" in red if it matches no learned button), the 3 pots and the encoder count.
static uint16_t testSeen = 0;              // bit per button
static int testLast = -1, testPrevKey = -1, testEnc = 0;
static char testBig[8] = "", testSmall[24] = "";
static uint32_t testCol = th::STEEL_L;

static void drawTest(uint32_t now) {
  backdrop();
  th::header("BUTTON TEST", now);
  drawTiles(26, testLast, testSeen, th::YELLOW);
  th::metal(60, 56, testBig, 3, th::WHITE, testCol == th::RED ? th::RED : th::YELLOW, 'm');
  th::text(60, 82, testSmall, th::p15(th::STEEL_L), 1, 'm');
  for (int k = 0; k < 3; k++) {              // pot bars
    int x = 4 + k * 39, pct = constrain(sysMv[k] / 31, 0, 100);
    th::cv.drawRect(x, 93, 36, 8, th::p15(th::STEEL));
    static const uint32_t st[3] = {th::YELLOW, th::ORANGE, th::RED};
    if (pct) th::grad(x + 1, 94, x + 1 + 34 * pct / 100, 100, st, 3, false);
  }
  int n = 0;
  for (int i = 0; i < K_N; i++) n += (testSeen >> i) & 1;
  char s[24];
  snprintf(s, sizeof s, "%d/%d K%+d R2R2:EXIT", n, K_N, testEnc);
  statusOr(s);
}

static void testSource(char *s, size_t n, int src, int val) {
  if (src == 3) snprintf(s, n, "GPIO %d", val);
  else snprintf(s, n, "LADDER %d  %d MV", src, val);
}

void uiShow();

void testStart() {
  uiPage = PAGE_TEST;
  testSeen = 0;
  testLast = testPrevKey = -1;
  testEnc = 0;
  snprintf(testBig, sizeof testBig, "PRESS");
  snprintf(testSmall, sizeof testSmall, "ANY BUTTON");
  testCol = th::STEEL_L;
  uiShow();
}

static void testPress(int b) {
  if (b == K_R2 && testPrevKey == K_R2) { uiPage = PAGE_FX; menu.cursor = 0; uiShow(); return; }
  testPrevKey = b;
  testLast = b;
  testSeen |= 1 << b;
  testSource(testSmall, sizeof testSmall, lastBtnSrc, lastBtnVal);
  snprintf(testBig, sizeof testBig, "%s", BTN_NAMES[b]);
  testCol = th::YELLOW;
  uiDirty = true;
}

// From btnEvent: a press that matches no learned button
void uiUnknown(int src, int val) {
  if (uiPage != PAGE_TEST || !liveOn || faceOn) return;
  testPrevKey = -1;
  testSource(testSmall, sizeof testSmall, src, val);
  snprintf(testBig, sizeof testBig, "??");
  testCol = th::RED;
  uiDirty = true;
}

// From controlsTick (every 50 ms): the live values for the SYSTEM / test pages
void testPots(const int *v) {
  static int shown[5] = {-9999, -9999, -9999, -9999, -9999};
  bool moved = false;
  for (int k = 0; k < 5; k++) {
    sysMv[k] = v[k];
    if (abs(v[k] - shown[k]) > (k < 3 ? 30 : 20)) { shown[k] = v[k]; moved = true; }
  }
  if (moved && (uiPage == PAGE_TEST || uiPage == PAGE_SYS)) uiDirty = true;
}

// ---- pages
static void drawFX(uint32_t now) {
  backdrop();
  th::header("FX", now, 0);
  char v[24];
  th::row(28, "MODE", MODE_NAMES[menu.mode], menu.cursor == 0, false, now, th::slide(now, pageT0, 0));
  snprintf(v, sizeof v, menu.byp1 ? "%s OFF" : "%s", FX_NAMES[menu.fx1]);
  th::row(46, "FX 1", v, menu.cursor == 1, menu.byp1, now, th::slide(now, pageT0, 1));
  snprintf(v, sizeof v, menu.byp2 ? "%s OFF" : "%s", FX_NAMES[menu.fx2]);
  th::row(64, "FX 2", v, menu.cursor == 2, menu.mode == 0 || menu.byp2, now, th::slide(now, pageT0, 2));
  if (now - pageT0 > 250) {                  // routing line, once the rows have landed
    char s[32];
    const char *a = menu.byp1 ? "-" : FX_NAMES[menu.fx1], *b = menu.byp2 ? "-" : FX_NAMES[menu.fx2];
    if (menu.mode == 0) snprintf(s, sizeof s, "IN > %s > OUT", a);
    else {
      a = menu.byp1 ? "-" : FX_SHORT[menu.fx1]; b = menu.byp2 ? "-" : FX_SHORT[menu.fx2];
      snprintf(s, sizeof s, menu.mode == 1 ? "IN>%s+%s>OUT" : "IN>%s>%s>OUT", a, b);
    }
    th::text(60, 89, s, th::p15(th::ORANGE), 1, 'm');
  }
  statusOr("KNOB:EDIT T6/B6:MOVE");
}

static void drawTune(uint32_t now) {
  backdrop();
  th::header("TUNE", now, 1);
  char v[16];
  th::row(28, "KEY", KEY_NAMES[menu.key], menu.cursor == 0, false, now, th::slide(now, pageT0, 0));
  th::row(46, "SCALE", SCALE_NAMES[menu.scale], menu.cursor == 1, false, now, th::slide(now, pageT0, 1));
  snprintf(v, sizeof v, menu.speed >= 9 ? "%d ROBOT" : (menu.speed <= 2 ? "%d NATURAL" : "%d"), menu.speed);
  th::row(64, "SPEED", v, menu.cursor == 2, false, now, th::slide(now, pageT0, 2));
  bool on = menu.fx1 == 4 || (menu.mode != 0 && menu.fx2 == 4);
  if (!on) th::text(60, 89, "SET AN FX TO TUNE", th::p15(th::RED), 1, 'm');
  statusOr("KNOB:EDIT T6/B6:MOVE");
}

extern bool dspAwake;                        // face.h: the power switch says the DSP runs

static void drawSys(uint32_t now) {
  backdrop();
  th::header("SYSTEM", now, 2);
  char s[32];
  th::text(4, 27, "POTS", th::p15(th::STEEL_L));
  for (int k = 0; k < 3; k++) {              // pot bars
    int x = 34 + k * 28, pct = constrain(sysMv[k] / 31, 0, 100);
    th::cv.drawRect(x, 27, 25, 7, th::p15(th::STEEL));
    static const uint32_t st[3] = {th::YELLOW, th::ORANGE, th::RED};
    if (pct) th::grad(x + 1, 28, x + 1 + 23 * pct / 100, 33, st, 3, false);
  }
  int y = 39;
  snprintf(s, sizeof s, "%d MV", sysMv[3]);
  th::text(4, y, "LADDER 1", th::p15(th::STEEL_L)); th::text(116, y, s, th::p15(th::WHITE), 1, 'r');
  snprintf(s, sizeof s, "%d MV", sysMv[4]);
  th::text(4, y + 11, "LADDER 2", th::p15(th::STEEL_L)); th::text(116, y + 11, s, th::p15(th::WHITE), 1, 'r');
  snprintf(s, sizeof s, "%d", encSteps / 4);
  th::text(4, y + 22, "ENCODER", th::p15(th::STEEL_L)); th::text(116, y + 22, s, th::p15(0x28C8E6), 1, 'r');
  th::text(4, y + 33, "DSP", th::p15(th::STEEL_L));
  th::text(116, y + 33, dspAwake ? "ON" : "OFF (SWITCH)", th::p15(dspAwake ? 0x30D060 : th::RED), 1, 'r');
  if (WiFi.status() == WL_CONNECTED) {
    int r = WiFi.RSSI();
    snprintf(s, sizeof s, "WIFI %dDBM", r);
    th::text(4, y + 44, s, th::p15(r > -70 ? 0x30D060 : (r > -80 ? th::YELLOW : th::RED)));
    th::text(116, y + 55, WiFi.localIP().toString().c_str(), th::p15(th::WHITE), 1, 'r');
  } else th::text(4, y + 44, "WIFI CONNECTING..", th::p15(th::STEEL));
  statusOr("ENTER:BUTTON TEST");
}

static void drawEdit(uint32_t now);         // below, with the effect settings

void uiRedraw(uint32_t now) {
  if (!th::ready) return;
  if (uiPage == PAGE_FX) drawFX(now);
  else if (uiPage == PAGE_TUNE) drawTune(now);
  else if (uiPage == PAGE_SYS) drawSys(now);
  else if (uiPage == PAGE_EDIT) drawEdit(now);
  else drawTest(now);
  uint32_t t = millis();
  th::present();
  uiLastPushMs = millis() - t;
}

// Draw the current page now (a new page restarts the fly-in)
void uiShow() {
  liveOn = true;
  faceOn = false;
  if (uiPage != lastPage) { pageT0 = millis(); lastPage = uiPage; }
  uiDirty = false;
  uiRedraw(millis());
}

// Call every loop: keeps the visible page animated
void uiAnimTick() {
  if (!th::ready || !liveOn || faceOn || learnIdx >= 0) return;
  static uint32_t last = 0;
  uint32_t now = millis();
  uint32_t period = now - pageT0 < 600 ? 40 : 110;   // fly-in fast, then ~9 fps for the lava / flames / shimmer
  if (!uiDirty && now - last < period) return;
  last = now;
  uiDirty = false;
  uiRedraw(now);
}

static void send(uint8_t aa, int v) {
  bool ok = onceWriteX(aa, v);
  displayStatus(ok ? "SENT TO DSP" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
}

// Autotune params (dsp/autotune.py): X:$0B retune speed (Q23 per sample), X:$23-$2E snap map = signed semitone
// offset per pitch class (C = 0) to the nearest note of the scale; ties snap down. Same rule as dsp/model/sim_os_tune.py.
static void tuneFill(uint8_t *aa, uint32_t *v) {   // the 13 tune values: snap map $23-$2E, speed $0B
  bool allowed[12] = {false};
  for (int i = 0; i < SCALE_LEN[menu.scale]; i++) allowed[(menu.key + SCALE_STEPS[menu.scale][i]) % 12] = true;
  static const int TRY[5] = {0, -1, 1, -2, 2};
  for (int pc = 0; pc < 12; pc++) {
    int d = 0;
    for (int t : TRY) if (allowed[(pc + t + 12) % 12]) { d = t; break; }
    aa[pc] = 0x23 + pc;
    v[pc] = (uint32_t)d & 0xFFFFFF;
  }
  // speed 0..10 -> 0.00005 .. 0.02 per sample, log-spaced (0 = very natural ~0.5 s glide, 10 = instant robot)
  aa[12] = 0x0B;
  v[12] = (uint32_t)lroundf(0.00005f * powf(400.0f, menu.speed / 10.0f) * 8388608.0f);
}

static void tuneSend() {
  uint8_t aa[13];
  uint32_t v[13];
  tuneFill(aa, v);
  bool ok = onceWriteXMany(aa, v, 13);
  displayStatus(ok ? "TUNE SENT" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
}

// ---- Pots -> the kernel's output stage (normal / vocal mode): POT1 volume, POT2 dry/wet mix, POT3 tone.
// (A later pedal mode can hand the three pots to the effect itself.)
static const uint8_t POT_AA[4] = {0x2F, 0x3D, 0x3E, 0x3C};   // dry gain, wet gain, tone k, volume (dsp/os.py)
static int potSent[3] = {-9999, -9999, -9999};

static uint32_t q23(float x) { return (uint32_t)lroundf(constrain(x, 0.0f, 0.99999988f) * 8388608.0f) & 0xFFFFFF; }

static void potFill(const int *mv, uint32_t *v) {
  float p[3];
  for (int k = 0; k < 3; k++) p[k] = constrain(mv[k] / 3100.0f, 0.0f, 1.0f);
  float vol = p[0] < 0.02f ? 0.0f : powf(10.0f, 2.0f * (p[0] - 1.0f));      // 40 dB audio taper, far left = off
  float fc = 400.0f * powf(50.0f, p[2]);                                     // tone: 400 Hz .. 20 kHz low-pass
  float k = p[2] > 0.97f ? 1.0f : 1.0f - expf(-6.2831853f * fc / 44100.0f);  // far right = no filter
  v[0] = q23(1.0f - p[1]);                   // linear crossfade: CLEAN stays at the same level at any mix
  v[1] = q23(p[1]);
  v[2] = q23(k);
  v[3] = q23(vol);
}

// ---- Effect settings: long X writes into each effect's param block (VOCAL_ARCH.md "Param maps"). T5 = EDIT page.
enum { PK_ENUM, PK_PCT, PK_TRIM, PK_SEMI, PK_RATIO, PK_GAIN };
struct FxParam { const char *name; uint16_t addr; uint8_t kind; int v, lo, hi; const char *const *labels; };
static const char *const RADIO_MODES[] = {"TELEPHONE", "MEGAPHONE", "AM RADIO", "WALKIE", "CASSETTE", "VINYL"};
static const char *const VOICES[] = {"GIANT", "MONSTER", "CHIPMUNK", "ELF", "M > F", "F > M", "CUSTOM"};
static const int VOICE_F[6] = {78, 70, 135, 125, 118, 85};     // formant ratio x100
static const int VOICE_P[6] = {0, -5, 7, 3, 5, -5};           // pitch, semitones
static FxParam radioP[] = {
  {"MODE", 0x0210, PK_ENUM, 0, 0, 5, RADIO_MODES}, {"WET", 0x0211, PK_PCT, 100, 0, 100, nullptr},
  {"DRIVE", 0x0212, PK_TRIM, 100, 0, 200, nullptr}, {"NOISE", 0x0213, PK_TRIM, 100, 0, 200, nullptr}};
static FxParam formantP[] = {
  {"VOICE", 0, PK_ENUM, 0, 0, 6, VOICES},                       // UI only: sets THROAT + PITCH
  {"THROAT", 0x0221, PK_RATIO, 78, 50, 160, nullptr}, {"PITCH", 0x0220, PK_SEMI, 0, -12, 12, nullptr},
  {"WET", 0x0222, PK_PCT, 100, 0, 100, nullptr}, {"GAIN", 0x0223, PK_GAIN, 100, 0, 200, nullptr}};
static FxParam octaveP[] = {
  {"PITCH", 0x0230, PK_SEMI, -12, -12, 12, nullptr}, {"THROAT", 0x0231, PK_RATIO, 100, 50, 160, nullptr},
  {"WET", 0x0232, PK_PCT, 50, 0, 100, nullptr}, {"GAIN", 0x0233, PK_GAIN, 141, 0, 200, nullptr}};
struct FxParams { FxParam *p; int n; };

static FxParams fxParams(int fx) {
  if (fx == 7) return {radioP, 4};
  if (fx == 8) return {formantP, 5};
  if (fx == 9) return {octaveP, 4};
  return {nullptr, 0};
}

static uint32_t paramWord(const FxParam &p) {
  switch (p.kind) {
    case PK_ENUM: return (uint32_t)p.v;
    case PK_PCT: return q23(p.v / 100.0f);                                        // wet 0..100%
    case PK_TRIM: return p.v >= 200 ? 0x7FFFFF : (uint32_t)p.v * 0x400000 / 100;   // 100% = $400000 (as voiced)
    case PK_GAIN: return q23(p.v / 200.0f);                                        // GAIN2 = gain / 2
    case PK_RATIO: return q23(p.v / 200.0f);                                       // F2 = f / 2: 0.78 -> $31EB85
    case PK_SEMI: return q23(0.5f / powf(2.0f, p.v / 12.0f));                      // INVP2 = 1 / (2p): -12 -> $7FFFFF
  }
  return 0;
}

static void paramText(const FxParam &p, char *s, size_t n) {
  if (p.kind == PK_ENUM) snprintf(s, n, "%s", p.labels[p.v]);
  else if (p.kind == PK_RATIO) snprintf(s, n, "X%d.%02d", p.v / 100, p.v % 100);
  else if (p.kind == PK_SEMI) snprintf(s, n, "%+d ST", p.v);
  else snprintf(s, n, "%d%%", p.v);
}

static int editCursor = 0;
static int editFx() {               // FX1 if it has settings, else FX2 when it is in the chain
  if (fxParams(menu.fx1).n) return menu.fx1;
  if (menu.mode != 0 && fxParams(menu.fx2).n) return menu.fx2;
  return menu.fx1;
}

static void editChange(int d) {
  int fx = editFx();
  FxParams ps = fxParams(fx);
  if (!ps.n) return;
  FxParam &p = ps.p[editCursor];
  if (p.kind == PK_ENUM) p.v = wrapv(p.v - p.lo + d, p.hi - p.lo + 1) + p.lo;
  else p.v = constrain(p.v + d * (p.kind == PK_SEMI ? 1 : (p.kind == PK_RATIO ? 2 : 5)), p.lo, p.hi);
  uint16_t aa[2];
  uint32_t w[2];
  int n = 0;
  if (fx == 8 && editCursor == 0) {                 // a voice preset sets THROAT + PITCH
    if (p.v < 6) { formantP[1].v = VOICE_F[p.v]; formantP[2].v = VOICE_P[p.v]; }
    aa[n] = formantP[1].addr; w[n++] = paramWord(formantP[1]);
    aa[n] = formantP[2].addr; w[n++] = paramWord(formantP[2]);
  } else {
    if (fx == 8 && (editCursor == 1 || editCursor == 2)) formantP[0].v = 6;   // hand-tuned = CUSTOM
    aa[n] = p.addr; w[n++] = paramWord(p);
  }
  bool ok = onceWriteXLong(aa, w, n);
  displayStatus(ok ? "SENT TO DSP" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
}

static void drawEdit(uint32_t now) {
  backdrop();
  int fx = editFx();
  th::header(FX_NAMES[fx], now);
  FxParams ps = fxParams(fx);
  if (!ps.n) {
    th::text(60, 50, "NO SETTINGS", th::p15(th::STEEL_L), 1, 'm');
    th::text(60, 62, "FOR THIS EFFECT", th::p15(th::STEEL_L), 1, 'm');
    statusOr("T1:FX T2:TUNE");
    return;
  }
  char v[20];
  for (int i = 0; i < ps.n; i++) {
    paramText(ps.p[i], v, sizeof v);
    th::row(26 + i * 16, ps.p[i].name, v, editCursor == i, false, now, th::slide(now, pageT0, i));
  }
  statusOr("KNOB:EDIT T6/B6:MOVE");
}

// Every effect's settings in one halt (after a boot, with the rest of the panel state)
static bool pushParams() {
  uint16_t aa[16];
  uint32_t w[16];
  int n = 0;
  for (int fx = 7; fx <= 9; fx++) {
    FxParams ps = fxParams(fx);
    for (int i = 0; i < ps.n; i++)
      if (ps.p[i].addr) { aa[n] = ps.p[i].addr; w[n++] = paramWord(ps.p[i]); }
  }
  return onceWriteXLong(aa, w, n);
}

// From controlsTick (every 50 ms): send when a pot moved more than 40 mV, at most every 100 ms (each send is one
// short halt of the DSP, so they are kept rare)
void potsToDsp(const int *mv) {
  static uint32_t last = 0;
  bool moved = false;
  for (int k = 0; k < 3; k++) if (abs(mv[k] - potSent[k]) > 40) moved = true;
  if (!moved || millis() - last < 100 || !dspAwake || learnIdx >= 0) return;
  last = millis();
  uint32_t v[4];
  potFill(mv, v);
  if (onceWriteXMany(POT_AA, v, 4)) for (int k = 0; k < 3; k++) potSent[k] = mv[k];
}

// At ESP start (e.g. after an OTA reboot the DSP keeps playing): take over the DSP's mode / FX so the screen shows
// what is actually playing. Values out of range (stock firmware running) are ignored.
void uiAdoptDsp() {
  uint8_t aa[3] = {0x20, 0x21, 0x22};
  uint32_t v[3];
  if (!onceReadXMany(aa, v, 3)) return;
  if (v[0] >= (uint32_t)N_MODES || v[1] >= (uint32_t)N_FX || v[2] >= (uint32_t)N_FX) return;
  menu.mode = v[0]; menu.fx1 = v[1]; menu.fx2 = v[2];
  Serial.printf("DSP state adopted: mode=%d fx1=%d fx2=%d\n", menu.mode, menu.fx1, menu.fx2);
}

// The whole panel state to the DSP in one halt: mode, FX1/FX2 (bypassed = CLEAN), tune, pots. A freshly booted kernel
// starts on its own defaults, so after every boot this makes the sound match the screen and the knobs.
bool uiPushAll() {
  uint8_t aa[20] = {0x20, 0x21, 0x22};
  uint32_t v[20] = {(uint32_t)menu.mode, (uint32_t)(menu.byp1 ? 0 : menu.fx1), (uint32_t)(menu.byp2 ? 0 : menu.fx2)};
  tuneFill(aa + 3, v + 3);
  int mv[3];
  for (int k = 0; k < 3; k++) mv[k] = analogReadMilliVolts(PIN_POT[k]);
  memcpy(aa + 16, POT_AA, 4);
  potFill(mv, v + 16);
  bool ok = onceWriteXMany(aa, v, 20) && pushParams();
  if (ok) for (int k = 0; k < 3; k++) potSent[k] = mv[k];
  displayStatus(ok ? "PANEL -> DSP" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
  return ok;
}

// Change the selected value by d (encoder steps or K_R1)
static void uiChange(int d) {
  if (uiPage == PAGE_EDIT) { editChange(d); uiShow(); return; }
  int c = menu.cursor;
  if (uiPage == PAGE_FX) {
    if (c == 0) { menu.mode = wrapv(menu.mode + d, N_MODES); send(0x20, menu.mode); }
    if (c == 1) { menu.fx1 = wrapv(menu.fx1 + d, N_FX); if (!menu.byp1) send(0x21, menu.fx1); }
    if (c == 2) { menu.fx2 = wrapv(menu.fx2 + d, N_FX); if (!menu.byp2) send(0x22, menu.fx2); }
    if ((c == 1 && menu.fx1 == 4) || (c == 2 && menu.fx2 == 4)) tuneSend();  // TUNE picked: push its settings
  } else if (uiPage == PAGE_TUNE) {
    if (c == 0) menu.key = wrapv(menu.key + d, 12);
    if (c == 1) menu.scale = wrapv(menu.scale + d, 3);
    if (c == 2) menu.speed = constrain(menu.speed + d, 0, 10);
    tuneSend();
  }
  uiShow();
}

static void cursorMove(int d) {
  if (uiPage == PAGE_SYS) return;
  if (uiPage == PAGE_EDIT) {
    int n = fxParams(editFx()).n;
    if (n) editCursor = wrapv(editCursor + d, n);
    uiShow();
    return;
  }
  menu.cursor = wrapv(menu.cursor + d, 3);
  uiShow();
}

static void bypass(int which) {
  bool &b = which == 1 ? menu.byp1 : menu.byp2;
  b = !b;
  send(which == 1 ? 0x21 : 0x22, b ? 0 : (which == 1 ? menu.fx1 : menu.fx2));  // bypass = CLEAN in that slot
  if (uiPage == PAGE_FX) uiShow();
}

void uiButton(int b) {
  if (faceOn) return;              // first touch only wakes the face
  if (!liveOn) uiShow();           // a serial command had the screen: take it back first
  if (uiPage == PAGE_TEST) { testPress(b); return; }
  switch (b) {
    case K_T1: uiPage = PAGE_FX; menu.cursor = 0; uiShow(); break;
    case K_T2: uiPage = PAGE_TUNE; menu.cursor = 0; uiShow(); break;
    case K_T3: uiPage = PAGE_SYS; uiShow(); break;
    case K_T5: uiPage = PAGE_EDIT; editCursor = 0; uiShow(); break;
    case K_T6: cursorMove(-1); break;
    case K_B6: cursorMove(1); break;
    case K_R1: case K_B4: case K_B5:                         // ENTER (value +1; on SYSTEM: button test)
      if (uiPage == PAGE_SYS) testStart(); else uiChange(1);
      break;
    case K_R2: uiPage = PAGE_FX; menu.cursor = 0; uiShow(); break;
    case K_B1: bypass(1); break;
    case K_B2: bypass(2); break;
    default: {
      char m[24];
      snprintf(m, sizeof m, "%s: NOT ASSIGNED", BTN_NAMES[b]);
      displayStatus(m, th::STEEL_L);
    }
  }
}

// Call every loop: encoder steps change the selected value
void uiTick() {
  static int last = 0;
  int s = encSteps / 4;
  if (s == last) return;
  int d = s - last;
  last = s;
  if (learnIdx >= 0) { btnLearnSkip(); return; }
  if (faceOn || !liveOn) return;  // consumed: waking the face / serial owns the screen
  if (uiPage == PAGE_TEST) { testEnc += d; uiDirty = true; return; }
  uiChange(d);
}

// Serial keys (PC): '[' ']' cursor, '-' '=' value
void menuKey(char k) {
  liveOn = true;
  if (uiPage == PAGE_SYS || uiPage == PAGE_TEST || uiPage == PAGE_EDIT) uiPage = PAGE_FX;
  if (k == '[') cursorMove(-1);
  else if (k == ']') cursorMove(1);
  else if (k == '-') uiChange(-1);
  else if (k == '=') uiChange(1);
}

void menuDraw() { uiPage = PAGE_FX; uiShow(); }

// Which pedal the idle screen shows (or -1 = vocal: the face sings): FX1, else FX2 when it is in the chain
int idlePedal() {
  if (FX_PEDAL[menu.fx1]) return menu.fx1;
  if (menu.mode != 0 && FX_PEDAL[menu.fx2]) return menu.fx2;
  return -1;
}
