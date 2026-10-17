// M-One OS UI: pages on the front controls; FX settings go live to the DSP kernel (dsp/os.py) over J8.
// Drawn with theme.h (PS1 heavy-metal look): every page renders itself into the 120x120 canvas from the current state,
// and uiAnimTick redraws it ~9x a second (faster while the rows fly in) so the lava, flames and selection shimmer move.
// Buttons by position (buttons.h):
//   T1 = FX page   T2 = TUNE page   T3 = SYSTEM page (live inputs, WiFi)   T5 = EDIT (the effect's own settings;
//   on the FX page's STRIP row: the STRIP input stage's settings)
//   T6 / B6 = cursor up / down    encoder = change the selected value    R1 / B4 / B5 = enter (value +1)    R2 = back to FX
//   T4 = PRESET page: the knob (or T6 / B6) loads the previous / next preset; enter = list by type; R2 = back
//   B1 / B2 = bypass FX1 / FX2 (toggle, works on any page; a preset's chain: B1 bypasses it all)
//   B3 = reverb FREEZE on / off (while REVERB plays)
//   SYSTEM page + enter = BUTTON TEST page (every button only lights its box there; R2 twice = back to FX)
// Serial keys from the PC do the same: '[' ']' cursor, '-' '=' value, 'F' FX page, 'T' button test.
#pragma once

bool onceWriteX(uint8_t aa, uint32_t value);  // in the .ino
bool onceWriteXMany(const uint8_t *aa, const uint32_t *value, int n);
bool onceReadXMany(const uint8_t *aa, uint32_t *value, int n);
bool onceWriteXLong(const uint16_t *aa, const uint32_t *value, int n);
bool onceReadXLong(const uint16_t *aa, uint32_t *value, int n);

#include "presets.h"                        // generated: tools/gen_presets.py from dsp/presets.py

enum { PAGE_FX, PAGE_TUNE, PAGE_SYS, PAGE_TEST, PAGE_EDIT, PAGE_PRESET, PAGE_MAIN, PAGE_PEDAL, PAGE_PKNOB };
int uiPage = PAGE_MAIN;                     // boots on the MODE ring; EXIT steps back to it

// What is playing (the ring's crown): VOCAL FX = the FX page's own setup, PRESETS = a preset, PEDAL = the pedal board
enum { MODE_VOCAL, MODE_PRESETS, MODE_PEDAL };
static int uiMode = MODE_VOCAL;

static const char *MODE_NAMES[] = {"SINGLE", "DOUBLE", "DBL-SINGLE", "CHAIN"};   // CHAIN (3): set by presets
static const char *FX_NAMES[] = {"CLEAN", "HEAVY", "REVERSE", "COMP", "TUNE", "VOX", "AMP", "RADIO", "FORMANT", "OCTAVE",
                                 "HARMONY", "DOUBLER", "REVERB", "DELAY", "SHIMMER", "SWELL", "GRAIN"};
static const char *FX_SHORT[] = {"CLN", "HVY", "REV", "CMP", "TUNE", "VOX", "AMP", "RAD", "FMT", "OCT",
                                 "HRM", "DBL", "RVB", "DLY", "SHM", "SWL", "GRN"};       // DOUBLE routing line
static const bool FX_PEDAL[] = {false, true, true, true, false, false, true, false, false, false,
                                false, false, false, false, false, false, false};         // PEDAL: mock pedal idle
static const bool FX_SOON[] = {false, false, false, false, false, false, false, false, false, false,
                               false, false, false, false, false, false, false};  // DSP placeholder (plays CLEAN): skipped
static const uint32_t FX_COL[] = {0xFF7000, 0xFF7000, 0x963CDC, 0x2E8BFF, 0xFFCC00, 0xE6AA28, 0xE82010, 0xAA4614,
                                  0xE82010, 0x963CDC, 0xFFCC00, 0xE6AA28, 0x2E8BFF, 0x30D060, 0xC8E6FF, 0xFFCC00,
                                  0x963CDC};
static const char *KEY_NAMES[] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
static const char *SCALE_NAMES[] = {"CHROMATIC", "MAJOR", "MINOR"};
static const int N_MODES = 3, N_FX = 17;
static const int FX_STRIP = 99;             // the STRIP input stage's settings on the EDIT page (not an effect slot)
static const uint8_t SCALE_STEPS[3][12] = {
  {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11},  // chromatic
  {0, 2, 4, 5, 7, 9, 11, 0, 0, 0, 0, 0},   // major (7 used)
  {0, 2, 3, 5, 7, 8, 10, 0, 0, 0, 0, 0},   // natural minor (7 used)
};
static const int SCALE_LEN[3] = {12, 7, 7};

struct MenuState {
  int mode = 0, fx1 = 0, fx2 = 2;  // boot state: CLEAN (HEAVY is +60 dB: a wall of noise on a live mic)
  bool byp1 = false, byp2 = false;
  bool strip = false;              // STRIP input stage (X:$0207), runs before every mode
  int key = 0, scale = 0, speed = 6;  // speed 6 ~ the DSP default (0.002 per sample)
  int cursor = 0;                  // row on the FX / TUNE page
  int preset = -1;                 // PRESETS index of the loaded preset, -1 = none (manual FX page setup)
  int chainN = 0;                  // CHAIN mode (3): X:$0200 = n, X:$0201.. = effect ids
  uint8_t chain[6] = {0};
} menu;
static bool presetDirty = false;   // a setting changed after the preset was loaded

// Navigation: every step forward pushes where you were; EXIT pops one step, all the way back to the MODE ring.
// Going to a page that is already on the path cuts back to it (no loops). Each page keeps its own cursor.
struct NavPos { uint8_t page, level; };
static NavPos navStack[10];
static int navN = 0;
static void navGo(int page, int level = 0);
static void navBack();
static int tuneCur = 0;            // SETTINGS (tune) page row
static uint32_t animUntil = 0;     // a ring turn / pedal swap is animating: redraw fast

static int wrapv(int v, int n) { return ((v % n) + n) % n; }
static int fxStep(int fx, int d) {           // next effect id, stepping over the DSP placeholders
  fx = wrapv(fx + d, N_FX);
  while (FX_SOON[fx]) fx = wrapv(fx + (d > 0 ? 1 : -1), N_FX);
  return fx;
}

bool rowsVisible() { return liveOn && !faceOn && uiPage == PAGE_SYS && learnIdx < 0; }

// ---- render state: status line, dirty flag, page-open time (fly-in), live input values for SYSTEM
bool uiDirty = true;
static uint32_t pageT0 = 0;
static int lastPage = -1;
static char uiStat[32] = "";
static uint32_t uiStatCol = th::YELLOW, uiStatT = 0;
int sysMv[5] = {0, 0, 0, 0, 0};             // pots 1-3, ladders 1-2 (mV), set by controlsTick
uint32_t uiLastPushMs = 0, uiLastDrawMs = 0; // the last frame: push to the screen / drawing (serial 'V')

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
    const uint32_t st[3] = {th::YELLOW, th::ORANGE, th::RED};
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
  navGo(PAGE_TEST);
  testSeen = 0;
  testLast = testPrevKey = -1;
  testEnc = 0;
  snprintf(testBig, sizeof testBig, "PRESS");
  snprintf(testSmall, sizeof testSmall, "ANY BUTTON");
  testCol = th::STEEL_L;
  uiShow();
}

static void testPress(int b) {
  if (b == K_R2 && testPrevKey == K_R2) { navBack(); uiShow(); return; }
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
  th::header("VOCAL FX", now);
  char v[24];
  bool ch = menu.mode == 3;                  // CHAIN (a preset): FX 1 / FX 2 are not used
  snprintf(v, sizeof v, ch && menu.byp1 ? "CHAIN OFF" : "%s", MODE_NAMES[menu.mode]);
  th::row(26, "MODE", v, menu.cursor == 0, false, now, th::slide(now, pageT0, 0));
  snprintf(v, sizeof v, ch ? "IN CHAIN" : (menu.byp1 ? "%s OFF" : "%s"), FX_NAMES[menu.fx1]);
  th::row(42, "FX 1", v, menu.cursor == 1, ch || menu.byp1, now, th::slide(now, pageT0, 1));
  snprintf(v, sizeof v, ch ? "IN CHAIN" : (menu.byp2 ? "%s OFF" : "%s"), FX_NAMES[menu.fx2]);
  th::row(58, "FX 2", v, menu.cursor == 2, ch || menu.mode == 0 || menu.byp2, now, th::slide(now, pageT0, 2));
  th::row(74, "STRIP", menu.strip ? "ON" : "OFF", menu.cursor == 3, !menu.strip, now, th::slide(now, pageT0, 3));
  if (now - pageT0 > 250) {                  // routing line, once the rows have landed
    char s[48];
    const char *a = menu.byp1 ? "-" : FX_NAMES[menu.fx1], *b = menu.byp2 ? "-" : FX_NAMES[menu.fx2];
    const char *in = menu.strip ? "IN>STR" : "IN";
    if (ch) {                                // the chain, on two lines when it is long
      snprintf(s, sizeof s, "%s", in);
      for (int i = 0; i < menu.chainN && !menu.byp1; i++) {
        strlcat(s, ">", sizeof s);
        strlcat(s, menu.chain[i] < N_FX ? FX_SHORT[menu.chain[i]] : "?", sizeof s);
      }
      strlcat(s, ">OUT", sizeof s);
    } else if (menu.mode == 0) snprintf(s, sizeof s, menu.strip ? "%s>%s>OUT" : "%s > %s > OUT", in, a);
    else {
      a = menu.byp1 ? "-" : FX_SHORT[menu.fx1]; b = menu.byp2 ? "-" : FX_SHORT[menu.fx2];
      snprintf(s, sizeof s, menu.mode == 1 ? "%s>%s+%s>OUT" : "%s>%s>%s>OUT", in, a, b);
    }
    int len = strlen(s);
    if (len <= 20) th::text(60, 93, s, th::p15(th::ORANGE), 1, 'm');
    else {                                   // split at the '>' nearest the middle
      int cut = len / 2;
      while (cut > 0 && s[cut] != '>') cut--;
      char s2[48];
      snprintf(s2, sizeof s2, "%s", s + cut);
      s[cut] = 0;
      th::text(60, 89, s, th::p15(th::ORANGE), 1, 'm');
      th::text(60, 98, s2, th::p15(th::ORANGE), 1, 'm');
    }
  }
  statusOr(menu.cursor == 3 ? "T5:STRIP SETTINGS" : "KNOB:EDIT T6/B6:MOVE");
}

static int masterPct = 40;                   // SETTINGS > MASTER: the pedal board's output level (40 = -24 dB)
static void pdLoad();

static void drawTune(uint32_t now) {         // six rows, five on screen (the window follows the cursor)
  backdrop();
  th::header("SETTINGS", now);
  pdLoad();
  char v[16], m[12];
  snprintf(v, sizeof v, menu.speed >= 9 ? "%d ROBOT" : (menu.speed <= 2 ? "%d NATURAL" : "%d"), menu.speed);
  if (masterPct < 2) snprintf(m, sizeof m, "OFF");
  else snprintf(m, sizeof m, "%d DB", (int)lroundf(40.0f * (masterPct / 100.0f - 1.0f)));
  const char *key[6] = {"TUNE KEY", "SCALE", "SPEED", "SCENE", "THEME", "MASTER"};
  const char *val[6] = {KEY_NAMES[menu.key], SCALE_NAMES[menu.scale], v, bg::SCENES[bg::sel].name, bg::themeName(), m};
  int first = constrain(tuneCur - 4, 0, 1);
  for (int i = first; i < first + 5; i++)
    th::row(24 + (i - first) * 17, key[i], val[i], tuneCur == i, false, now, th::slide(now, pageT0, i - first));
  bool on = menu.fx1 == 4 || (menu.mode != 0 && menu.fx2 == 4);
  statusOr(tuneCur == 5 ? "PEDAL BOARD OUTPUT" : tuneCur == 4 ? "MENU COLOURS" : tuneCur == 3 ? "THE MODE RING'S LOOK" :
           on ? "KNOB:EDIT T6/B6:MOVE" : "TUNE IS NOT PLAYING");
}

extern bool dspAwake;                        // face.h: the power switch says the DSP runs

static void drawSys(uint32_t now) {
  backdrop();
  th::header("SYSTEM", now);
  char s[32];
  th::text(4, 27, "POTS", th::p15(th::STEEL_L));
  for (int k = 0; k < 3; k++) {              // pot bars
    int x = 34 + k * 28, pct = constrain(sysMv[k] / 31, 0, 100);
    th::cv.drawRect(x, 27, 25, 7, th::p15(th::STEEL));
    const uint32_t st[3] = {th::YELLOW, th::ORANGE, th::RED};
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
static void drawPreset(uint32_t now);       // below, with the presets
static void drawMain(uint32_t now);
static void drawPknob(uint32_t now);         // below: a sim's knob list         // below: the MODE ring (ring3d.h)
void pedalPageDraw(uint32_t now);           // face.h: the PEDAL board (needs the singing level for its LED)

void uiRedraw(uint32_t now) {
  if (!th::ready) return;
  uint32_t t0 = millis();
  if (uiPage == PAGE_FX) drawFX(now);
  else if (uiPage == PAGE_TUNE) drawTune(now);
  else if (uiPage == PAGE_SYS) drawSys(now);
  else if (uiPage == PAGE_EDIT) drawEdit(now);
  else if (uiPage == PAGE_PRESET) drawPreset(now);
  else if (uiPage == PAGE_MAIN) drawMain(now);
  else if (uiPage == PAGE_PEDAL) pedalPageDraw(now);
  else if (uiPage == PAGE_PKNOB) drawPknob(now);
  else drawTest(now);
  uint32_t t = millis();
  uiLastDrawMs = t - t0;
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
void presetTick();
void pedalTick();
void uiAnimTick() {
  presetTick();                              // a preset picked with the knob loads once the knob rests
  pedalTick();                               // likewise a pedal
  if (!th::ready || !liveOn || faceOn || learnIdx >= 0) return;
  static uint32_t last = 0;
  uint32_t now = millis();
  uint32_t period = now - pageT0 < 600 || now < animUntil ? 33 : 110;   // fly-in / turns fast, then ~9 fps
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
// Pedal mode (AMP playing): POT1 volume, POT2 / POT3 = AMP's GAIN / TREBLE (potsToDsp), the mix all wet, tone open.
static const uint8_t POT_AA[4] = {0x2F, 0x3D, 0x3E, 0x3C};   // dry gain, wet gain, tone k, volume (dsp/os.py)
static int potSent[3] = {-9999, -9999, -9999};
static int potSig = -1;                     // which pot mapping the last pot words used (potMapSig)
static bool fxInPath(int fx);
static int pedalPots();                      // PEDAL board: -1 = off it; AMP 0; 4 = a sim (output stage = MASTER)
static uint32_t masterWord();

static uint32_t q23(float x) { return (uint32_t)lroundf(constrain(x, 0.0f, 0.99999988f) * 8388608.0f) & 0xFFFFFF; }

static void potFill(const int *mv, uint32_t *v) {
  float p[3];
  for (int k = 0; k < 3; k++) p[k] = constrain(mv[k] / 3100.0f, 0.0f, 1.0f);
  float vol = p[0] < 0.02f ? 0.0f : powf(10.0f, 2.0f * (p[0] - 1.0f));      // 40 dB audio taper, far left = off
  float fc = 400.0f * powf(50.0f, p[2]);                                     // tone: 400 Hz .. 20 kHz low-pass
  float k = p[2] > 0.97f ? 1.0f : 1.0f - expf(-6.2831853f * fc / 44100.0f);  // far right = no filter
  int pp = pedalPots();                      // -1 = not on the pedal board
  bool mix = pp < 0 ? !fxInPath(6) : (pp & 1), tone = pp < 0 ? !fxInPath(6) : (pp & 2);
  v[0] = mix ? q23(1.0f - p[1]) : 0;         // linear crossfade: CLEAN stays at the same level at any mix
  v[1] = mix ? q23(p[1]) : 0x7FFFFF;         // a pedal without a MIX knob (and AMP) plays all wet, tone open
  v[2] = tone ? q23(k) : 0x7FFFFF;
  v[3] = pp == 4 ? masterWord() : q23(vol);   // a sim on the board: SETTINGS > MASTER
}

// ---- Effect settings: long X writes into each effect's param block (VOCAL_ARCH.md "Param maps"). T5 = EDIT page.
// A row with addr 0 is a UI-only preset row (VOICE / TYPE): it sets the rows under it; hand-tuning those = CUSTOM.
enum { PK_ENUM, PK_PCT, PK_TRIM, PK_SEMI, PK_RATIO, PK_GAIN, PK_INV, PK_TICKS, PK_INT, PK_HZ, PK_MS44, PK_HZ44,
       PK_SHIFT, PK_DB, PK_RISE, PK_MK, PK_DRV, PK_SDB, PK_POW2, PK_KNOB };
static uint32_t q23s(double x) {             // signed Q23 (24-bit two's complement)
  return (uint32_t)llround(constrain(x, -1.0, 0.99999988) * 8388608.0) & 0xFFFFFF;
}
struct FxParam { const char *name; uint16_t addr; uint8_t kind; int v, lo, hi; const char *const *labels; int step; };
static const char *const OFF_ON[] = {"OFF", "ON"};
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
// REVERB X:$0280 (dsp/model/reverb_model.py PRESETS): TYPE sets SIZE, DECAY, DAMP, PREDLY, WET
static const char *const REV_TYPES[] = {"ROOM", "PLATE", "HALL", "CUSTOM"};
static const int REV_PRE[3][5] = {{35, 45, 35, 5, 25}, {75, 65, 15, 12, 30}, {100, 82, 45, 35, 35}};
static FxParam reverbP[] = {
  {"TYPE", 0, PK_ENUM, 1, 0, 3, REV_TYPES},                     // UI only; the DSP boots on PLATE
  {"SIZE", 0x0280, PK_PCT, 75, 10, 100, nullptr}, {"DECAY", 0x0281, PK_PCT, 65, 0, 95, nullptr},
  {"DAMP", 0x0282, PK_INV, 15, 0, 95, nullptr}, {"PREDLY", 0x0284, PK_TICKS, 12, 1, 60, nullptr},
  {"WET", 0x0285, PK_PCT, 30, 0, 100, nullptr}, {"FREEZE", 0x0286, PK_ENUM, 0, 0, 1, OFF_ON}};
// DELAY X:$0290 (dsp/model/delay_model.py PRESETS): TYPE sets every row
static const char *const DLY_TYPES[] = {"SLAP", "TEMPO", "DOTTED", "DUCKING", "TAPE", "MULTI", "CUSTOM"};
static const int DLY_PRE[6][9] = {   // time ms, feedback, wet, tone, duck (%), taps, wow (ticks), sat, wow rate (Hz x10)
  {110, 0, 35, 70, 0, 0, 0, 0, 7}, {500, 35, 30, 50, 0, 0, 0, 0, 7}, {375, 40, 30, 50, 0, 0, 0, 0, 7},
  {500, 35, 40, 50, 80, 0, 0, 0, 7}, {500, 80, 35, 35, 0, 0, 6, 1, 7}, {720, 30, 35, 45, 0, 1, 0, 0, 7}};
static FxParam delayP[] = {
  {"TYPE", 0, PK_ENUM, 0, 0, 6, DLY_TYPES},                     // UI only; the DSP boots on SLAP
  {"TIME", 0x0290, PK_TICKS, 110, 10, 725, nullptr, 5}, {"FDBK", 0x0291, PK_PCT, 0, 0, 95, nullptr},
  {"WET", 0x0292, PK_PCT, 35, 0, 100, nullptr}, {"TONE", 0x0293, PK_PCT, 70, 5, 100, nullptr},
  {"DUCK", 0x0294, PK_PCT, 0, 0, 100, nullptr}, {"TAPS", 0x0295, PK_ENUM, 0, 0, 1, OFF_ON},
  {"WOW", 0x0296, PK_INT, 0, 0, 20, nullptr}, {"SAT", 0x0297, PK_ENUM, 0, 0, 1, OFF_ON},
  {"WOW HZ", 0x0298, PK_HZ, 7, 1, 50, nullptr}};
// HARMONY X:$0240 (dsp/model/harmony_model.py): +0 MIX1, +1 MIX2, +2 DRY, +4 MAP1, +16 MAP2 (12 signed semitone offsets
// per pitch class of TUNE's note). A voice is a diatonic interval in the TUNE page's key / scale (chromatic = major),
// as diatonic_map(steps, key), or a fixed interval (the same offset for all 12).
static const char *const HARM_IV[] = {"3RD UP", "4TH UP", "5TH UP", "6TH UP", "OCT UP", "3RD DN", "4TH DN", "5TH DN",
                                      "6TH DN", "OCT DN", "+4 ST", "+5 ST", "+7 ST", "-5 ST", "-7 ST", "+19 ST"};
static const int8_t HARM_DEF[16][2] = {{1, 2}, {1, 3}, {1, 4}, {1, 5}, {1, 7}, {1, -2}, {1, -3}, {1, -4}, {1, -5},
                                       {1, -7}, {0, 4}, {0, 5}, {0, 7}, {0, -5}, {0, -7}, {0, 19}};   // {diatonic, steps / ST}
static FxParam harmonyP[] = {
  {"VOICE 1", 0, PK_ENUM, 0, 0, 15, HARM_IV}, {"VOICE 2", 0, PK_ENUM, 2, 0, 15, HARM_IV},   // maps, not preset rows
  {"MIX 1", 0x0240, PK_PCT, 50, 0, 100, nullptr}, {"MIX 2", 0x0241, PK_PCT, 50, 0, 100, nullptr},
  {"DRY", 0x0242, PK_PCT, 80, 0, 100, nullptr}};
// DOUBLER X:$0260: +0 D1, +1 D2 (samples), +2 DEPTH (samples), +3 KW (LFO rate), +4 WET (= doubler_params defaults)
static FxParam doublerP[] = {
  {"TIME 1", 0x0260, PK_MS44, 18, 5, 40, nullptr}, {"TIME 2", 0x0261, PK_MS44, 27, 5, 40, nullptr},
  {"DEPTH", 0x0262, PK_INT, 12, 0, 30, nullptr}, {"RATE", 0x0263, PK_HZ44, 35, 5, 300, nullptr, 5},
  {"WET", 0x0264, PK_PCT, 60, 0, 100, nullptr}};
// SHIMMER X:$02A0 (harmony_model.shimmer_params): +0 GAIN, +1 INC (shifter step); it goes right before REVERB
static FxParam shimmerP[] = {
  {"GAIN", 0x02A0, PK_PCT, 35, 0, 60, nullptr}, {"PITCH", 0x02A1, PK_SHIFT, 12, -12, 24, nullptr}};
// SWELL X:$02B0 (strip_model.swell_params): +0 THR (level), +1 RATE (1 / fade-in samples)
static FxParam swellP[] = {
  {"THRESH", 0x02B0, PK_DB, -42, -70, -20, nullptr}, {"TIME", 0x02B1, PK_RISE, 450, 50, 3000, nullptr, 25}};
// STRIP input stage X:$0270 (strip_model.strip_params; on / off = X:$0207, the FX page's STRIP row): gate, de-esser,
// leveler, makeup, drive, then one EQ biquad (+5..+9: b0/2 b1/2 b2/2 -a1/2 -a2/2) built here from EQ + EQ GAIN
static const char *const EQ_TYPES[] = {"FLAT", "PRESENCE", "AIR", "LOW"};
static FxParam stripP[] = {
  {"GATE", 0x0270, PK_DB, -50, -80, -20, nullptr}, {"DE-ESS", 0x0271, PK_DB, -18, -40, 0, nullptr},
  {"COMP", 0x0272, PK_DB, -12, -40, 0, nullptr}, {"MAKEUP", 0x0273, PK_MK, 150, 100, 400, nullptr, 10},
  {"DRIVE", 0x0274, PK_DRV, 0, 0, 100, nullptr}, {"EQ", 0, PK_ENUM, 0, 0, 3, EQ_TYPES},   // drive x10
  {"EQ GAIN", 0, PK_SDB, 3, -10, 10, nullptr}};          // +-10 dB: a 10 kHz shelf at +12 overflows the /2 format
// GRAIN X:$02C0 (grain_model.params): +0 DPH = 1/L (follows SIZE), +1 L (samples), +2 RANGE (mask 2^n - 1, n = 11..15),
// +3 SCATTER, +4 WET, +5 DRY. 2L + RANGE stays inside REVERSE's 64K ring, so SIZE stops at 300 ms.
static const char *const GRAIN_RANGE[] = {"46 MS", "93 MS", "186 MS", "372 MS", "743 MS"};
static FxParam grainP[] = {
  {"SIZE", 0x02C1, PK_MS44, 110, 20, 300, nullptr, 5}, {"RANGE", 0x02C2, PK_POW2, 4, 0, 4, GRAIN_RANGE},
  {"SCATTER", 0x02C3, PK_ENUM, 1, 0, 1, OFF_ON}, {"WET", 0x02C4, PK_PCT, 80, 0, 100, nullptr},
  {"DRY", 0x02C5, PK_PCT, 40, 0, 100, nullptr}};
static uint32_t grainDph() { return q23(1.0f / (grainP[0].v * 441 / 10)); }   // 1 / L
// AMP X:$12C0 (dsp/amp.py; the words = dsp/model/amp_ref.ui_words, checked with the serial 'a' command). TYPE = the
// voicing (stage gains, Fender or Marshall tone stack) and loads its starting knobs. GAIN 70 = the type's own gains,
// each step moves stages 1 + 2 by 0.25 dB. With AMP playing, POT2 = GAIN and POT3 = TREBLE (pedal mode, potsToDsp).
static const char *const AMP_TYPES[] = {"CLEAN", "CRUNCH", "LEAD"};
static const int AMP_G[3][3] = {{6, 0, -6}, {20, 12, 0}, {30, 24, 12}};                  // stage gains, dB
static const int AMP_PRE[3][5] = {{50, 60, 60, -6, 30}, {50, 50, 60, 0, 50}, {60, 30, 70, 3, 60}};   // B M T DRV SAG
static FxParam ampP[] = {                     // CRUNCH = the defaults AMP loads itself (amp_ref.PRESET)
  {"TYPE", 0, PK_ENUM, 1, 0, 2, AMP_TYPES}, {"GAIN", 0, PK_KNOB, 70, 0, 100, nullptr},
  {"BASS", 0, PK_KNOB, 50, 0, 100, nullptr}, {"MID", 0, PK_KNOB, 50, 0, 100, nullptr},
  {"TREBLE", 0, PK_KNOB, 60, 0, 100, nullptr}, {"PRESENCE", 0, PK_SDB, 3, -12, 12, nullptr},
  {"RESONANCE", 0, PK_SDB, 3, 0, 12, nullptr}, {"DRIVE", 0, PK_SDB, 0, -12, 18, nullptr},
  {"SAG", 0, PK_PCT, 50, 0, 90, nullptr}, {"MASTER", 0, PK_PCT, 70, 0, 100, nullptr}};
enum { AG_GAIN = 1, AG_TMB = 2, AG_RES = 4, AG_PRES = 8, AG_DRV = 16, AG_SAG = 32, AG_MST = 64, AG_ALL = 127 };
static const uint8_t AMP_ROW_G[10] = {AG_ALL, AG_GAIN, AG_TMB, AG_TMB, AG_TMB, AG_PRES, AG_RES, AG_DRV, AG_SAG, AG_MST};

// Tone stack (amp_ref.tmb_sos, the same steps in the same order): Yeh & Smith's cubic, bilinear, the largest real pole
// by Newton from z = 1 -> first order (h, -h, pole) with the DC zero, the rest -> biquad b0 b1 b2 -a1 -a2, all /2.
// MID is held <= 0.99: at MID 1 / BASS 0 a pole sits on z = -1.
static int ampTmb(uint16_t *aa, uint32_t *w, int n) {
  double C1 = 470e-12, C2 = 22e-9, C3 = 22e-9, R1 = 220e3, R2 = 1e6, R3 = 22e3, R4 = 33e3;     // Marshall
  if (ampP[0].v == 0) { C1 = 250e-12; C2 = 20e-9; C3 = 20e-9; R1 = 250e3; R2 = 1e6; R3 = 25e3; R4 = 56e3; }   // Fender
  double l = ampP[2].v / 100.0, m = min(ampP[3].v / 100.0, 0.99), t = ampP[4].v / 100.0;
  double b1 = t*C1*R1 + m*C3*R3 + l*(C1*R2 + C2*R2) + (C1*R3 + C2*R3);
  double b2 = (t*(C1*C2*R1*R4 + C1*C3*R1*R4) - m*m*(C1*C3*R3*R3 + C2*C3*R3*R3)
               + m*(C1*C3*R1*R3 + C1*C3*R3*R3 + C2*C3*R3*R3) + l*(C1*C2*R1*R2 + C1*C2*R2*R4 + C1*C3*R2*R4)
               + l*m*(C1*C3*R2*R3 + C2*C3*R2*R3) + (C1*C2*R1*R3 + C1*C2*R3*R4 + C1*C3*R3*R4));
  double b3 = (l*m*(C1*C2*C3*R1*R2*R3 + C1*C2*C3*R2*R3*R4) - m*m*(C1*C2*C3*R1*R3*R3 + C1*C2*C3*R3*R3*R4)
               + m*(C1*C2*C3*R1*R3*R3 + C1*C2*C3*R3*R3*R4) + t*C1*C2*C3*R1*R3*R4 - t*m*C1*C2*C3*R1*R3*R4
               + t*l*C1*C2*C3*R1*R2*R4);
  double a1 = (C1*R1 + C1*R3 + C2*R3 + C2*R4 + C3*R4) + m*C3*R3 + l*(C1*R2 + C2*R2);
  double a2 = (m*(C1*C3*R1*R3 - C2*C3*R3*R4 + C1*C3*R3*R3 + C2*C3*R3*R3) + l*m*(C1*C3*R2*R3 + C2*C3*R2*R3)
               - m*m*(C1*C3*R3*R3 + C2*C3*R3*R3) + l*(C1*C2*R2*R4 + C1*C2*R1*R2 + C1*C3*R2*R4 + C2*C3*R2*R4)
               + (C1*C2*R1*R4 + C1*C3*R1*R4 + C1*C2*R3*R4 + C1*C2*R1*R3 + C1*C3*R3*R4 + C2*C3*R3*R4));
  double a3 = (l*m*(C1*C2*C3*R1*R2*R3 + C1*C2*C3*R2*R3*R4) - m*m*(C1*C2*C3*R1*R3*R3 + C1*C2*C3*R3*R3*R4)
               + m*(C1*C2*C3*R3*R3*R4 + C1*C2*C3*R1*R3*R3 - C1*C2*C3*R1*R3*R4) + l*C1*C2*C3*R1*R2*R4
               + C1*C2*C3*R1*R3*R4);
  double c = 2.0 * 44100, c2 = c * c, c3 = c * c * c;
  double a0 = a3 * c3 + a2 * c2 + a1 * c + 1;
  double B0 = (b3 * c3 + b2 * c2 + b1 * c) / a0;
  double B1 = (-3 * b3 * c3 - b2 * c2 + b1 * c) / a0;
  double B2 = (3 * b3 * c3 - b2 * c2 - b1 * c) / a0;
  double A1 = (-3 * a3 * c3 - a2 * c2 + a1 * c + 3) / a0;
  double A2 = (3 * a3 * c3 - a2 * c2 - a1 * c + 3) / a0;
  double A3 = (-a3 * c3 + a2 * c2 - a1 * c + 1) / a0;
  double p = 1.0;
  for (int i = 0; i < 60; i++) {
    double st = (((p + A1) * p + A2) * p + A3) / ((3 * p + 2 * A1) * p + A2);
    p -= st;
    if (fabs(st) < 1e-15) break;
  }
  double e1 = A1 + p, e2 = A2 + p * e1, g1 = B1 + B0, g2 = B2 + g1, h = 8388607.0 / 8388608.0;
  double bq[5] = {B0 / h, g1 / h, g2 / h, -e1, -e2};
  for (int i = 0; i < 5; i++) { aa[n] = 0x12D0 + i; w[n++] = q23s(bq[i] / 2); }
  aa[n] = 0x12D5; w[n++] = 0x7FFFFF;                       // first order: h, -h, pole
  aa[n] = 0x12D6; w[n++] = 0x800001;
  aa[n] = 0x12D7; w[n++] = q23s(p);
  return n;
}

static int ampPeq(uint16_t a, double fc, double db, double qf, uint16_t *aa, uint32_t *w, int n) {   // RBJ peak, /2
  double A = pow(10.0, db / 40.0), wv = 2 * PI * fc / 44100.0, al = sin(wv) / (2 * qf), cs = cos(wv), d0 = 1 + al / A;
  double c[5] = {(1 + al * A) / d0, -2 * cs / d0, (1 - al * A) / d0, 2 * cs / d0, -(1 - al / A) / d0};
  for (int i = 0; i < 5; i++) { aa[n] = a + i; w[n++] = q23s(c[i] / 2); }
  return n;
}

static int ampFill(uint16_t *aa, uint32_t *w, int n, uint8_t g) {   // the AMP words of groups g (AG_ bits)
  if (g & AG_GAIN)
    for (int s = 0; s < 3; s++) {
      double db = min(AMP_G[ampP[0].v][s] + (s < 2 ? (ampP[1].v - 70) * 0.25 : 0.0), 30.0);   // /32 format: <= 30 dB
      aa[n] = 0x12C0 + s; w[n++] = q23s(pow(10.0, db / 20.0) / 32);
    }
  if (g & AG_TMB) n = ampTmb(aa, w, n);
  if (g & AG_RES) n = ampPeq(0x12D8, 100, ampP[6].v, 1.2, aa, w, n);
  if (g & AG_PRES) n = ampPeq(0x12DD, 3000, ampP[5].v, 0.5, aa, w, n);   // wide peak: a shelf overflows above +3 dB
  if (g & AG_DRV) { aa[n] = 0x12E2; w[n++] = q23s(pow(10.0, ampP[7].v / 20.0) / 8); }
  if (g & AG_SAG) { aa[n] = 0x12E3; w[n++] = q23s(ampP[8].v / 100.0); }
  if (g & AG_MST) { aa[n] = 0x12E6; w[n++] = q23s(ampP[9].v / 100.0); }
  return n;
}
struct FxParams { FxParam *p; int n; };

static FxParams fxParams(int fx) {
  if (fx == 6) return {ampP, 10};
  if (fx == 7) return {radioP, 4};
  if (fx == 8) return {formantP, 5};
  if (fx == 9) return {octaveP, 4};
  if (fx == 10) return {harmonyP, 5};
  if (fx == 11) return {doublerP, 5};
  if (fx == 12) return {reverbP, 7};
  if (fx == 13) return {delayP, 10};
  if (fx == 14) return {shimmerP, 2};
  if (fx == 15) return {swellP, 2};
  if (fx == 16) return {grainP, 5};
  if (fx == FX_STRIP) return {stripP, 7};
  return {nullptr, 0};
}

// STRIP EQ -> X:$0275-$0279, as strip_model.eq_coefs: PRESENCE = RBJ peak 4 kHz Q 0.7, AIR / LOW = shelves at
// 10 kHz / 150 Hz (strip_model.shelf); FLAT or 0 dB = b0 1, the rest 0
static int stripEqFill(uint16_t *aa, uint32_t *w, int n) {
  int t = stripP[5].v, g = stripP[6].v;
  double c[5] = {1, 0, 0, 0, 0};                         // b0 b1 b2 a1 a2, normalized
  if (t && g) {
    static const double F[4] = {0, 4000, 10000, 150};
    double A = pow(10.0, g / 40.0), wv = 2 * PI * F[t] / 44100.0, cs = cos(wv), sn = sin(wv);
    double b0, b1, b2, a0, a1, a2;
    if (t == 1) {
      double al = sn / (2 * 0.7);
      b0 = 1 + al * A; b1 = -2 * cs; b2 = 1 - al * A; a0 = 1 + al / A; a1 = -2 * cs; a2 = 1 - al / A;
    } else {
      double sa = 2 * sqrt(A) * (sn / 2 * sqrt(2.0));
      if (t == 2) {
        b0 = A * ((A + 1) + (A - 1) * cs + sa); b1 = -2 * A * ((A - 1) + (A + 1) * cs); b2 = A * ((A + 1) + (A - 1) * cs - sa);
        a0 = (A + 1) - (A - 1) * cs + sa; a1 = 2 * ((A - 1) - (A + 1) * cs); a2 = (A + 1) - (A - 1) * cs - sa;
      } else {
        b0 = A * ((A + 1) - (A - 1) * cs + sa); b1 = 2 * A * ((A - 1) - (A + 1) * cs); b2 = A * ((A + 1) - (A - 1) * cs - sa);
        a0 = (A + 1) + (A - 1) * cs + sa; a1 = -2 * ((A - 1) + (A + 1) * cs); a2 = (A + 1) + (A - 1) * cs - sa;
      }
    }
    c[0] = b0 / a0; c[1] = b1 / a0; c[2] = b2 / a0; c[3] = a1 / a0; c[4] = a2 / a0;
  }
  for (int i = 0; i < 5; i++) { aa[n] = 0x0275 + i; w[n++] = q23s(c[i] * (i < 3 ? 0.5 : -0.5)); }
  return n;
}

// STRIP's low cut X:$027A-$027E (strip_model.LC, same /2 format as the EQ): the vocal 100 Hz high-pass. The pedal
// board's gate writes it flat; every full STRIP push puts the vocal one back.
static int stripLcFill(uint16_t *aa, uint32_t *w, int n) {
  static const uint32_t LC[5] = {0x3F5BBE, 0x814884, 0x3F5BBE, 0x7EB5D7, 0xC146DE};
  for (int i = 0; i < 5; i++) { aa[n] = 0x027A + i; w[n++] = LC[i]; }
  return n;
}

static bool fxInPath(int fx) {
  if (menu.mode == 3) {                      // CHAIN: in the list (B1 bypasses the whole chain)
    for (int i = 0; i < menu.chainN; i++) if (menu.chain[i] == fx) return !menu.byp1;
    return false;
  }
  return (menu.fx1 == fx && !menu.byp1) || (menu.mode != 0 && menu.fx2 == fx && !menu.byp2);
}

// HARMONY voice v -> its 12-word map at X:$0244 / $0250 (harmony_model.diatonic_map: nearest scale degree at or below)
static int harmMapFill(int v, uint16_t *aa, uint32_t *w, int n) {
  const int8_t *iv = HARM_DEF[harmonyP[v].v];
  const uint8_t *sc = SCALE_STEPS[menu.scale == 2 ? 2 : 1];
  for (int pc = 0; pc < 12; pc++) {
    int off = iv[1];
    if (iv[0]) {
      int rel = (pc - menu.key + 12) % 12, deg = 0, best = 99;
      for (int d = 0; d < 7; d++) { int dist = (rel - sc[d] + 12) % 12; if (dist < best) { best = dist; deg = d; } }
      int k = deg + iv[1], oct = k >= 0 ? k / 7 : -((6 - k) / 7);                     // floor(k / 7)
      off = sc[((k % 7) + 7) % 7] + 12 * oct - sc[deg];
    }
    aa[n] = 0x0244 + 12 * v + pc;
    w[n++] = (uint32_t)off & 0xFFFFFF;
  }
  return n;
}

static void harmSend() {                     // both maps, e.g. after a key / scale change
  uint16_t aa[24];
  uint32_t w[24];
  int n = harmMapFill(1, aa, w, harmMapFill(0, aa, w, 0));
  onceWriteXLong(aa, w, n);
}

static int presetSpan(int fx) { return fx == 8 ? 2 : fx == 12 ? 5 : fx == 13 ? 9 : 0; }   // rows the preset row sets
static void presetRows(int fx, int pr) {
  if (fx == 8) { formantP[1].v = VOICE_F[pr]; formantP[2].v = VOICE_P[pr]; }
  if (fx == 12) for (int i = 0; i < 5; i++) reverbP[1 + i].v = REV_PRE[pr][i];
  if (fx == 13) for (int i = 0; i < 9; i++) delayP[1 + i].v = DLY_PRE[pr][i];
}
static uint32_t revDd2() { return q23(constrain(reverbP[2].v / 100.0f + 0.15f, 0.25f, 0.5f)); }   // DD2 follows DECAY

static uint32_t paramWord(const FxParam &p) {
  switch (p.kind) {
    case PK_ENUM: return (uint32_t)p.v;
    case PK_PCT: return q23(p.v / 100.0f);                                        // wet 0..100%
    case PK_TRIM: return p.v >= 200 ? 0x7FFFFF : (uint32_t)p.v * 0x400000 / 100;   // 100% = $400000 (as voiced)
    case PK_GAIN: return q23(p.v / 200.0f);                                        // GAIN2 = gain / 2
    case PK_RATIO: return q23(p.v / 200.0f);                                       // F2 = f / 2: 0.78 -> $31EB85
    case PK_SEMI: return q23(0.5f / powf(2.0f, p.v / 12.0f));                      // INVP2 = 1 / (2p): -12 -> $7FFFFF
    case PK_INV: return q23(1.0f - p.v / 100.0f);                                  // reverb KD = 1 - damping
    case PK_TICKS: return (uint32_t)((p.v * 2205 + 50) / 100);                     // ms -> ticks at 22.05 kHz
    case PK_INT: return (uint32_t)p.v;
    case PK_HZ: return q23(2.0f * PI * p.v / 10.0f / 22050.0f);                    // LFO step per tick
    case PK_MS44: return (uint32_t)(p.v * 441 / 10);                                // ms -> samples (truncated)
    case PK_POW2: return (1u << (11 + p.v)) - 1;                                     // GRAIN RANGE mask
    case PK_HZ44: return q23(2.0f * PI * p.v / 100.0f / 44100.0f);                 // LFO step per sample
    case PK_SHIFT: return q23s((powf(2.0f, p.v / 12.0f) - 1.0f) / 2048.0f);        // shifter step (harmony INCTAB)
    case PK_DB: return q23(powf(10.0f, p.v / 20.0f));                              // dBFS -> level
    case PK_RISE: return q23(1.0f / (p.v * 44.1f));                                // fade-in ms -> step per sample
    case PK_MK: return q23(p.v / 400.0f);                                          // makeup / 4
    case PK_DRV: return q23(p.v / 160.0f);                                         // drive / 16 (0 = off), v = x10
    case PK_SDB: case PK_KNOB: return 0;                                           // shown only (computed words)
  }
  return 0;
}

static void paramText(const FxParam &p, char *s, size_t n) {
  if (p.kind == PK_ENUM || p.kind == PK_POW2) snprintf(s, n, "%s", p.labels[p.v]);
  else if (p.kind == PK_RATIO) snprintf(s, n, "X%d.%02d", p.v / 100, p.v % 100);
  else if (p.kind == PK_SEMI || p.kind == PK_SHIFT) snprintf(s, n, "%+d ST", p.v);
  else if (p.kind == PK_DB) snprintf(s, n, "%d DB", p.v);
  else if (p.kind == PK_SDB) snprintf(s, n, "%+d DB", p.v);
  else if (p.kind == PK_RISE) snprintf(s, n, "%d MS", p.v);
  else if (p.kind == PK_MK) snprintf(s, n, "X%d.%02d", p.v / 100, p.v % 100);
  else if (p.kind == PK_DRV) { if (p.v) snprintf(s, n, "X%d.%d", p.v / 10, p.v % 10); else snprintf(s, n, "OFF"); }
  else if (p.kind == PK_TICKS || p.kind == PK_MS44) snprintf(s, n, "%d MS", p.v);
  else if (p.kind == PK_HZ44) snprintf(s, n, "%d.%02d HZ", p.v / 100, p.v % 100);
  else if (p.kind == PK_INT) snprintf(s, n, "%d", p.v);
  else if (p.kind == PK_HZ) snprintf(s, n, "%d.%d HZ", p.v / 10, p.v % 10);
  else if (p.kind == PK_KNOB) snprintf(s, n, "%d.%d", p.v / 10, p.v % 10);       // amp knob 0.0 .. 10.0
  else snprintf(s, n, "%d%%", p.v);
}

static int paramStep(const FxParam &p) {          // per encoder step
  if (p.step) return p.step;
  if (p.kind == PK_RATIO) return 2;
  return (p.kind == PK_PCT || p.kind == PK_TRIM || p.kind == PK_GAIN || p.kind == PK_INV || p.kind == PK_KNOB) ? 5 : 1;
}

static int editCursor = 0;
static bool editStrip = false;      // T5 pressed on the FX page's STRIP row
static int editFx() {               // STRIP, else FX1 if it has settings, else FX2 when it is in the chain
  if (editStrip) return FX_STRIP;
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
  else p.v = constrain(p.v + d * paramStep(p), p.lo, p.hi);
  if (fx == 6) {                                                // AMP: only the words of the group that changed
    if (editCursor == 0) {                                      // TYPE: its starting knobs
      static const uint8_t ROW[5] = {2, 3, 4, 7, 8};
      for (int i = 0; i < 5; i++) ampP[ROW[i]].v = AMP_PRE[p.v][i];
      ampP[1].v = 70;
    }
    uint16_t aa[24];
    uint32_t w[24];
    bool ok = onceWriteXLong(aa, w, ampFill(aa, w, 0, AMP_ROW_G[editCursor]));
    displayStatus(ok ? "SENT TO DSP" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
    return;
  }
  int span = presetSpan(fx);
  bool preset = span && editCursor == 0;
  if (preset && p.v < p.hi) presetRows(fx, p.v);                // VOICE / TYPE sets the rows under it
  if (span && !preset && editCursor <= span) ps.p[0].v = ps.p[0].hi;   // hand-tuned = CUSTOM
  uint16_t aa[16];
  uint32_t w[16];
  int n = 0;
  for (int i = preset ? 1 : editCursor; i <= (preset ? span : editCursor); i++)
    if (ps.p[i].addr) { aa[n] = ps.p[i].addr; w[n++] = paramWord(ps.p[i]); }
  if (fx == 10 && editCursor < 2) n = harmMapFill(editCursor, aa, w, n);   // VOICE 1 / 2: that voice's map
  if (fx == FX_STRIP && editCursor >= 5) n = stripEqFill(aa, w, n);        // EQ / EQ GAIN: the biquad
  if (fx == 16 && editCursor == 0) { aa[n] = 0x02C0; w[n++] = grainDph(); } // SIZE: DPH = 1 / L too
  if (fx == 12) { aa[n] = 0x0287; w[n++] = revDd2(); }
  bool ok = onceWriteXLong(aa, w, n);
  displayStatus(ok ? "SENT TO DSP" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
}

static void drawEdit(uint32_t now) {
  backdrop();
  int fx = editFx();
  th::header(fx == FX_STRIP ? "STRIP" : FX_NAMES[fx], now);
  FxParams ps = fxParams(fx);
  if (!ps.n) {
    th::text(60, 50, "NO SETTINGS", th::p15(th::STEEL_L), 1, 'm');
    th::text(60, 62, "FOR THIS EFFECT", th::p15(th::STEEL_L), 1, 'm');
    statusOr("T1:FX T2:TUNE");
    return;
  }
  char v[20];
  const int ROWS = 5;                                     // rows that fit above the status bar; the list scrolls
  int first = constrain(editCursor - 2, 0, max(0, ps.n - ROWS));
  for (int i = first; i < ps.n && i < first + ROWS; i++) {
    paramText(ps.p[i], v, sizeof v);
    th::row(26 + (i - first) * 16, ps.p[i].name, v, editCursor == i, false, now, th::slide(now, pageT0, i - first));
  }
  uint32_t ac = th::p15(th::YELLOW);                      // more rows above / below
  if (first > 0) th::cv.fillTriangle(117, 27, 119, 27, 118, 24, ac);
  if (first + ROWS < ps.n) th::cv.fillTriangle(117, 101, 119, 101, 118, 104, ac);
  if (fx == 10) {                                         // HARMONY: its voices follow the TUNE page's key
    snprintf(v, sizeof v, "KEY %s %s (T2)", KEY_NAMES[menu.key], menu.scale == 2 ? "MINOR" : "MAJOR");
    statusOr(v);
  } else if (fx == 6 && fxInPath(6)) statusOr("POT2:GAIN POT3:TREB");   // pedal mode
  else statusOr("KNOB:EDIT T6/B6:MOVE");
}

// Every effect's settings in one halt (after a boot, with the rest of the panel state)
static bool pushParams() {
  uint16_t aa[160];
  uint32_t w[160];
  int n = 0;
  if (menu.mode == 3) {                                   // CHAIN: the list
    aa[n] = 0x0200; w[n++] = menu.chainN;
    for (int i = 0; i < 6; i++) { aa[n] = 0x0201 + i; w[n++] = menu.chain[i]; }
  }
  for (int fx = 7; fx <= N_FX; fx++) {
    FxParams ps = fxParams(fx < N_FX ? fx : FX_STRIP);
    for (int i = 0; i < ps.n; i++)
      if (ps.p[i].addr) { aa[n] = ps.p[i].addr; w[n++] = paramWord(ps.p[i]); }
  }
  n = harmMapFill(1, aa, w, harmMapFill(0, aa, w, n));    // HARMONY maps (key from the TUNE page)
  n = stripLcFill(aa, w, stripEqFill(aa, w, n));
  aa[n] = 0x0283; w[n++] = q23(0.9995f);                  // reverb bandwidth (fixed, as reverb_model.params)
  aa[n] = 0x0287; w[n++] = revDd2();
  aa[n] = 0x02C0; w[n++] = grainDph();
  aa[n] = 0x0207; w[n++] = menu.strip;                    // STRIP on / off
  n = ampFill(aa, w, n, AG_ALL);                          // AMP (its first call loads defaults: ampFollow)
  return onceWriteXLong(aa, w, n);
}

// From controlsTick (every 50 ms): send when a pot moved more than 40 mV, at most every 100 ms (each send is one
// short halt of the DSP, so they are kept rare)
// Pedal mode: a pot that moves takes over AMP's GAIN / TREBLE (its words go out in the same halt); until then the
// EDIT page's values stay, so picking AMP never jumps.
static int potMapSig() { return (pedalPots() + 1) * 2 + fxInPath(6); }   // changes = resend the pot words

void potsToDsp(const int *mv) {
  static uint32_t last = 0;
  if (pedalPots() == 4) return;               // a sim on the board: the pots are its knobs (pedalTick)
  bool amp = fxInPath(6), moved[3], any = potMapSig() != potSig;
  for (int k = 0; k < 3; k++) { moved[k] = abs(mv[k] - potSent[k]) > 40; any = any || moved[k]; }
  if (!any || millis() - last < 100 || !dspAwake || learnIdx >= 0) return;
  last = millis();
  uint16_t aa[16];
  uint32_t w[16], v[4];
  potFill(mv, v);
  for (int k = 0; k < 4; k++) { aa[k] = POT_AA[k]; w[k] = v[k]; }
  int n = 4;
  uint8_t g = 0;
  if (amp && moved[1]) { ampP[1].v = constrain((mv[1] + 15) / 31, 0, 100); g |= AG_GAIN; }
  if (amp && moved[2]) { ampP[4].v = constrain((mv[2] + 15) / 31, 0, 100); g |= AG_TMB; }
  if (g) { n = ampFill(aa, w, n, g); uiDirty = true; }
  if (onceWriteXLong(aa, w, n)) { for (int k = 0; k < 3; k++) potSent[k] = mv[k]; potSig = potMapSig(); }
}

// Serial 'a': "a<type> <gain> <bass> <mid> <treble> <presence> <resonance> <drive> <sag> <master>" prints the AMP words
// the panel computes for those settings (checked against dsp/model/amp_ref.ui_words); a trailing " !" also puts them on
// the AMP page and writes them to the DSP (they only stay if AMP has run once since the DSP booted, see ampFollow).
void ampCmd(const char *ln) {
  int v[10], keep[10];
  if (sscanf(ln, "%d %d %d %d %d %d %d %d %d %d", v, v + 1, v + 2, v + 3, v + 4, v + 5, v + 6, v + 7, v + 8, v + 9) != 10) {
    Serial.println("AMP: need 10 values");
    return;
  }
  for (int i = 0; i < 10; i++) { keep[i] = ampP[i].v; ampP[i].v = constrain(v[i], ampP[i].lo, ampP[i].hi); }
  uint16_t aa[24];
  uint32_t w[24], t0 = micros();
  int n = ampFill(aa, w, 0, AG_ALL);
  t0 = micros() - t0;
  Serial.print("AMPW");
  for (int k = 0; k < n; k++) Serial.printf(" %04X=%06lX", aa[k], (unsigned long)w[k]);
  Serial.printf(" (%lu us)\n", (unsigned long)t0);
  if (strchr(ln, '!')) {
    bool ok = onceWriteXLong(aa, w, n);
    Serial.printf("AMP written: %s\n", ok ? "ok" : "FAILED");
    uiDirty = true;
  } else for (int i = 0; i < 10; i++) ampP[i].v = keep[i];
}

// AMP's first call after a DSP boot loads its own defaults over X:$12C0: after anything that can put AMP in the path,
// send the panel's AMP settings and the pedal-mode pot words (one halt; nothing when AMP is not playing)
static void ampFollow() {
  if (!fxInPath(6)) return;
  uint16_t aa[28];
  uint32_t w[28], v[4];
  int n = ampFill(aa, w, 0, AG_ALL);
  potFill(sysMv, v);
  for (int k = 0; k < 4; k++) { aa[n] = POT_AA[k]; w[n++] = v[k]; }
  if (onceWriteXLong(aa, w, n)) { for (int k = 0; k < 3; k++) potSent[k] = sysMv[k]; potSig = potMapSig(); }
}

// ---- Presets (presets.h; T4 = PRESET page): CHAIN mode + the preset's writes, all in one halt. TUNE's snap map and
// HARMONY's maps are recomputed for the TUNE page's key; the EDIT pages are set from the writes (screen = sound).
static int s24(uint32_t v) { return (int32_t)(v << 8) >> 8; }

static void paramDecode(uint16_t a, uint32_t v) {     // a written word -> the EDIT row that writes it (nearest value)
  for (int fx = 7; fx <= N_FX; fx++) {
    FxParams ps = fxParams(fx < N_FX ? fx : FX_STRIP);
    for (int i = 0; i < ps.n; i++) {
      FxParam &p = ps.p[i];
      if (!p.addr || p.addr != a) continue;
      int best = p.v, bd = 0x7FFFFFFF;
      for (int c = p.lo; c <= p.hi && bd; c++) {
        p.v = c;
        int d = abs(s24(paramWord(p)) - s24(v));
        if (d < bd) { bd = d; best = c; }
      }
      p.v = best;
      return;
    }
  }
}

static void stripEqDecode(const uint32_t *eq) {       // the 5 EQ words -> EQ + EQ GAIN (nearest)
  int g0 = stripP[6].v, bt = 0, bg = g0, bd = 0x7FFFFFFF;
  uint16_t aa[5];
  uint32_t w[5];
  for (int t = 0; t < 4 && bd; t++)
    for (int g = t ? -10 : g0; g <= (t ? 10 : g0) && bd; g++) {
      if (t && !g) continue;
      stripP[5].v = t; stripP[6].v = g;
      stripEqFill(aa, w, 0);
      int d = 0;
      for (int i = 0; i < 5; i++) d += abs(s24(w[i]) - s24(eq[i]));
      if (d < bd) { bd = d; bt = t; bg = g; }
    }
  stripP[5].v = bt; stripP[6].v = bg;
}

static void presetMatch(int fx) {                     // VOICE / TYPE row: the preset its rows match, else CUSTOM
  FxParams ps = fxParams(fx);
  int span = presetSpan(fx), saved[10];
  for (int i = 1; i <= span; i++) saved[i - 1] = ps.p[i].v;
  for (int pr = 0; pr < ps.p[0].hi; pr++) {
    presetRows(fx, pr);
    bool same = true;
    for (int i = 1; i <= span; i++) same = same && ps.p[i].v == saved[i - 1];
    if (same) { ps.p[0].v = pr; return; }
  }
  for (int i = 1; i <= span; i++) ps.p[i].v = saved[i - 1];
  ps.p[0].v = ps.p[0].hi;
}

static void presetDecode(int i) {                     // the panel state of preset i (no DSP writes)
  const PresetDef &p = PRESETS[i];
  menu.mode = 3;
  menu.byp1 = false;
  menu.chainN = p.chainN;
  memcpy(menu.chain, p.chain, 6);
  uint32_t eq[5];
  bool hasEq = false;
  for (int k = 0; k < p.nw; k++) {
    uint16_t a = p.wa[k];
    if (a == 0x0207) menu.strip = p.wv[k] & 1;
    else if (a >= 0x0275 && a <= 0x0279) { eq[a - 0x0275] = p.wv[k]; hasEq = true; }
    else if (a >= 0x0210) paramDecode(a, p.wv[k]);
  }
  if (hasEq) stripEqDecode(eq);
  presetMatch(8); presetMatch(12); presetMatch(13);
  if (p.tuneSpeed >= 0) {
    menu.speed = p.tuneSpeed;
    if (p.tuneChrom) menu.scale = 0;
    else if (menu.scale == 0) menu.scale = 1;            // snap to the key: a CHROMATIC page becomes MAJOR
  }
  if (p.v1 >= 0) harmonyP[0].v = p.v1;
  if (p.v2 >= 0) harmonyP[1].v = p.v2;
}

static int presetSavedIdx() {                         // the last loaded preset (NVS), -1 = none
  Preferences pr;
  pr.begin("ui", true);
  int v = pr.getInt("preset", -1);
  pr.end();
  return v;
}

static void presetSave() {
  if (presetSavedIdx() == menu.preset) return;
  Preferences pr;
  pr.begin("ui", false);
  pr.putInt("preset", menu.preset);
  pr.end();
}

static bool applyPreset(int i) {
  const PresetDef &p = PRESETS[i];
  presetDecode(i);
  static uint16_t aa[128];
  static uint32_t w[128];
  int n = 0;
  for (int k = 0; k < p.nw; k++) { aa[n] = p.wa[k]; w[n++] = p.wv[k]; }
  if (p.tuneSpeed >= 0) {                               // TUNE: speed + snap map for the TUNE page's key / scale
    uint8_t ta[13];
    uint32_t tv[13];
    tuneFill(ta, tv);
    for (int k = 0; k < 13; k++) { aa[n] = ta[k]; w[n++] = tv[k]; }
  }
  for (int k = 0; k < p.chainN; k++)                    // HARMONY: both maps in the key
    if (p.chain[k] == 10) { n = harmMapFill(1, aa, w, harmMapFill(0, aa, w, n)); break; }
  bool ok = onceWriteXLong(aa, w, n);
  if (ok) { menu.preset = i; presetDirty = false; presetSave(); uiMode = MODE_PRESETS; ampFollow(); }
  Serial.printf("PRESET %02d %s: %d writes %s\n", p.n, p.name, n, ok ? "ok" : "FAILED");
  displayStatus(ok ? "PRESET LOADED" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
  return ok;
}

// PRESET page: level 0 = the loaded preset (the knob loads the next / previous once it rests 150 ms), 1 = the types,
// 2 = the presets of one type (enter loads)
static int presetLevel = 0, presetType = 0, presetCur = 0, presetPending = -1;
static uint32_t presetAt = 0;

static int presetTypeList(int t, int *idx) {          // PRESETS indexes of type t, in number order
  int n = 0;
  for (int i = 0; i < N_PRESETS; i++) if (PRESETS[i].type == t) idx[n++] = i;
  return n;
}

void presetTick() {                                   // every loop
  if (presetPending < 0 || millis() - presetAt < 150) return;
  int i = presetPending;
  presetPending = -1;
  applyPreset(i);
  uiDirty = true;
}

static void presetKnob(int d) {
  if (presetLevel == 0) {
    int cur = presetPending >= 0 ? presetPending : menu.preset;
    presetPending = cur < 0 ? (d > 0 ? 0 : N_PRESETS - 1) : wrapv(cur + d, N_PRESETS);
    presetAt = millis();
  } else {
    int idx[N_PRESETS];
    presetCur = wrapv(presetCur + d, presetLevel == 1 ? N_PTYPES : presetTypeList(presetType, idx));
  }
}

static void presetEnter() {
  int idx[N_PRESETS];
  if (presetLevel == 0) {
    int cur = presetPending >= 0 ? presetPending : menu.preset;
    navGo(PAGE_PRESET, 1);
    presetCur = cur >= 0 ? PRESETS[cur].type : 0;
  } else if (presetLevel == 1) {
    int n = presetTypeList(presetType = presetCur, idx);
    navGo(PAGE_PRESET, 2);
    presetCur = 0;
    for (int r = 0; r < n; r++) if (idx[r] == menu.preset) presetCur = r;
  } else {
    if (presetCur < presetTypeList(presetType, idx)) { presetPending = -1; applyPreset(idx[presetCur]); }
    navGo(PAGE_PRESET, 0);
  }
  pageT0 = millis();
}

// PRESETS mode always shows a preset that plays: the one loaded last (NVS), else 01
static void presetOpen() {
  navGo(PAGE_PRESET, 0);
  if (menu.preset < 0 && presetPending < 0) {
    int sp = presetSavedIdx();
    applyPreset(sp >= 0 && sp < N_PRESETS ? sp : 0);
  }
  if (menu.preset >= 0) uiMode = MODE_PRESETS;
}

static void drawPreset(uint32_t now) {
  backdrop();
  char v[40];
  if (presetLevel == 0) {
    th::header("PRESET", now);
    int i = presetPending >= 0 ? presetPending : menu.preset;
    if (i < 0) {
      th::metal(60, 46, "NO PRESET", 1, th::WHITE, th::YELLOW, 'm');
      th::text(60, 62, "TURN THE KNOB", th::p15(th::STEEL_L), 1, 'm');
      statusOr("KNOB:LOAD ENT:LIST");
      return;
    }
    const PresetDef &p = PRESETS[i];
    snprintf(v, sizeof v, "%02d", p.n);
    th::metal(5, 25, v, 3, th::WHITE, th::YELLOW);
    th::text(119, 27, PRESET_TYPES[p.type], th::p15(th::STEEL_L), 1, 'r');   // clear of the number (x 5..41)
    if (presetPending >= 0) th::text(116, 38, "LOADING", th::p15(th::YELLOW), 1, 'r');
    else if (menu.mode == 3 && menu.byp1) th::text(116, 38, "BYPASSED", th::p15(th::RED), 1, 'r');
    else if (presetDirty) th::text(116, 38, "EDITED", th::p15(th::ORANGE), 1, 'r');
    th::metal(60, 54, p.name, 1, th::WHITE, th::YELLOW, 'm');
    snprintf(v, sizeof v, "%s", p.strip ? "STR" : "");
    for (int k = 0; k < p.chainN; k++) {
      if (v[0]) strlcat(v, ">", sizeof v);
      strlcat(v, p.chain[k] < N_FX ? FX_SHORT[p.chain[k]] : "?", sizeof v);
    }
    int len = strlen(v);
    if (len <= 20) th::text(60, 70, v, th::p15(th::ORANGE), 1, 'm');
    else {                                              // split at the '>' nearest the middle
      int cut = len / 2;
      while (cut > 0 && v[cut] != '>') cut--;
      th::text(60, 77, v + cut, th::p15(th::ORANGE), 1, 'm');
      v[cut] = 0;
      th::text(60, 68, v, th::p15(th::ORANGE), 1, 'm');
    }
    if (p.note[0]) {                                    // the pixel font has no lower case
      int k = 0;
      for (; p.note[k] && k < 20; k++) v[k] = toupper(p.note[k]);
      v[k] = 0;
      th::text(60, 90, v, th::p15(th::ASH), 1, 'm');
    }
    statusOr("KNOB:NEXT ENT:LIST");
    return;
  }
  int idx[N_PRESETS];
  int n = presetLevel == 1 ? N_PTYPES : presetTypeList(presetType, idx);
  th::header(presetLevel == 1 ? "TYPES" : PRESET_TYPES[presetType], now);
  const int ROWS = 5;
  int first = constrain(presetCur - 2, 0, max(0, n - ROWS));
  for (int r = first; r < n && r < first + ROWS; r++) {
    int y = 26 + (r - first) * 16, dx = th::slide(now, pageT0, r - first);
    if (presetLevel == 1) {
      int ix[N_PRESETS];
      snprintf(v, sizeof v, "%d", presetTypeList(r, ix));
      th::row(y, PRESET_TYPES[r], v, presetCur == r, false, now, dx);
    } else {
      const PresetDef &p = PRESETS[idx[r]];
      snprintf(v, sizeof v, "%02d %s", p.n, p.name);
      th::row(y, v, idx[r] == menu.preset ? "*" : "", presetCur == r, false, now, dx);
    }
  }
  uint32_t ac = th::p15(th::YELLOW);                      // more rows above / below
  if (first > 0) th::cv.fillTriangle(117, 27, 119, 27, 118, 24, ac);
  if (first + ROWS < n) th::cv.fillTriangle(117, 101, 119, 101, 118, 104, ac);
  statusOr(presetLevel == 1 ? "ENT:OPEN R2:BACK" : "ENT:LOAD R2:BACK");
}

// ---- Navigation (declared at the top)
static void navSet(int page, int level) {
  uiPage = page;
  if (page == PAGE_PRESET) {
    presetLevel = level;
    if (level == 1) presetCur = presetType;      // back on the type list: on the type you were in
  }
  pageT0 = millis();
}

static void navGo(int page, int level) {
  if (page == uiPage && (page != PAGE_PRESET || level == presetLevel)) return;
  for (int i = 0; i < navN; i++)                 // already on the path: cut back to it
    if (navStack[i].page == page && (page != PAGE_PRESET || navStack[i].level == level)) {
      navN = i;
      navSet(page, level);
      return;
    }
  if (navN < 10) navStack[navN++] = {(uint8_t)uiPage, (uint8_t)presetLevel};
  navSet(page, level);
}

static void navBack() {
  if (navN > 0) { NavPos p = navStack[--navN]; navSet(p.page, p.level); }
  else if (uiPage != PAGE_MAIN) navSet(PAGE_MAIN, 0);
}

// ---- PEDAL board: the guitar pedal sims (pedals_dsp.h, generated by tools/gen_pedals.py; dsp/PEDALS.md), then AMP.
// The knob (or T6 / B6) swaps pedals; the sound follows once the knob rests. The pots are the pedal's first three
// knobs, left to right: a pot takes over its knob only once it moves, and a knob keeps what it was set to. ENTER = the
// knob list: T6 / B6 pick a knob, the encoder steps it, or turn any pot and the knob snaps to it. B1 = the footswitch.
// SETTINGS > MASTER is the output level. Knob settings are kept per pedal (NVS "ui"/"pdpos").
#include "pedals_dsp.h"

enum { SRC_POT1, SRC_POT2, SRC_POT3, SRC_AMP };  // SRC_AMP + row = an ampP row
struct PedalKnob { const char *label; uint8_t src; };
struct PedalDef { uint8_t fx; const char *name; uint32_t col; uint8_t nk; PedalKnob k[6]; };
static const PedalDef AMP_PEDAL = {6, "AMP", 0xE01818, 6, {{"LEVEL", SRC_POT1}, {"GAIN", SRC_AMP + 1}, {"BASS", SRC_AMP + 2},
                                   {"MID", SRC_AMP + 3}, {"TREB", SRC_AMP + 4}, {"PRES", SRC_AMP + 5}}};
static const int N_PEDALS = PD_N + 1;          // the sims, then AMP
const int BOARD_FX = 1000;                      // idlePedal(): BOARD_FX + i = board pedal i
static int pedalIdx = 0;                        // TUBE SCREAMER first (NVS "ui"/"pedal" after that)
static int pedalPrev = -1, pedalPending = -1, pedalDir = 1;
static uint32_t pedalAt = 0, pedalSwapT = 0;
static int pdPlaying = -1;                      // the sim the DSP plays (its pick went through), -1 = none
static bool pdByp = false;                      // B1: the sim is bypassed (CLEAN), its state kept
static uint8_t pdPos[PD_N][6];                  // knob positions 0..100 per pedal
static bool pdLoaded = false;
static uint32_t pdSaveAt = 0;                   // a pending NVS save (2 s after the last change)
static uint8_t pdDirty = 0;                     // knobs whose words still have to go out (bit = knob)
static uint32_t pdSendAt = 0;
static int pknobCur = 0;                        // the knob list's cursor
static int pdPotRef[3], pdPotMv[3];             // a pot takes over once it leaves where it was when armed
static bool pdPotOwn[3];
static bool gateOn = false;                     // B2 on the board: the input gate (NVS "ui"/"gate")
static int gateDb = -50;                        // its threshold, -80..-20 dB (the knob list's last row; "ui"/"gthr")
static bool gateDirty = false;

// The input gate = STRIP as a gate only (before the pedal): no de-esser, leveler, drive, EQ or low cut (the vocal
// 100 Hz cut would thin a low E). STRIP X:$0270-$027E: GATE, DEESS, COMP, MK/4, DRIVE, EQ (5), LC (5); X:$0207 on.
static int gateFill(uint16_t *a, uint32_t *v, int n) {
  static const uint32_t W[15] = {0, 0x7FFFFF, 0x7FFFFF, 0x200000, 0, 0x400000, 0, 0, 0, 0, 0x400000, 0, 0, 0, 0};
  for (int i = 0; i < 15; i++) { a[n] = 0x0270 + i; v[n++] = W[i]; }
  v[n - 15] = q23(powf(10.0f, gateDb / 20.0f));
  a[n] = 0x0207; v[n++] = gateOn;
  return n;
}

static void gateSet(bool on, int db) {
  db = constrain(db, -80, -20);
  if (on == gateOn && db == gateDb) return;
  gateOn = on;
  gateDb = db;
  gateDirty = true;                               // goes out from pedalTick
  pdSaveAt = millis() + 2000;
  uiDirty = true;
}

static void gateToggle() {                      // B2 on a sim
  gateSet(!gateOn, gateDb);
  char s[24];
  snprintf(s, sizeof s, gateOn ? "GATE ON %d DB" : "GATE OFF", gateDb);
  displayStatus(s, gateOn ? 0x30D060 : th::STEEL_L);
}

static const char *pedalName(int i) { return i < PD_N ? PD_PEDALS[i].name : AMP_PEDAL.name; }
static uint32_t pedalCol(int i) { return i < PD_N ? PD_PEDALS[i].col : AMP_PEDAL.col; }
static int pedalNk(int i) { return i < PD_N ? PD_PEDALS[i].nk : AMP_PEDAL.nk; }
static const char *plateName(int i) {           // the name plate fits ~11 characters
  return i < PD_N && !strcmp(PD_PEDALS[i].name, "TUBE SCREAMER") ? "TS-808" : pedalName(i);
}

static const char *knobShort(const char *l) {   // under a drawn knob: 5 characters at most
  static const char *const SHORT[][2] = {{"VOLUME", "VOL"}, {"DISTORTION", "DIST"}, {"SUSTAIN", "SUST"}, {"MIDDLE", "MID"},
      {"MIDFREQ", "FREQ"}, {"TREBLE", "TREB"}, {"OUTPUT", "OUT"}, {"INTENSITY", "INTEN"}, {"FEEDBACK", "FDBK"},
      {"PRE-DLY", "PRE"}, {"SHIMMER", "SHIM"}, {"MANUAL", "MAN"}, {"REVERB", "REV"}, {"BOTTOM", "BOTTM"}, {"FILTER", "FILTR"}};
  for (auto &s : SHORT) if (!strcmp(l, s[0])) return s[1];
  return l;
}

static void pdLoad() {                          // knob settings, MASTER and the last pedal from NVS
  if (pdLoaded) return;
  pdLoaded = true;
  for (int i = 0; i < PD_N; i++)
    for (int k = 0; k < PD_PEDALS[i].nk; k++) pdPos[i][k] = PD_PEDALS[i].k[k].def;
  Preferences pr;
  pr.begin("ui", true);
  if (pr.isKey("pdpos") && pr.getBytesLength("pdpos") == sizeof pdPos) pr.getBytes("pdpos", pdPos, sizeof pdPos);
  masterPct = constrain(pr.getInt("master", 40), 0, 100);
  pedalIdx = constrain(pr.getInt("pedal", 0), 0, N_PEDALS - 1);
  gateOn = pr.getBool("gate", false);
  gateDb = constrain(pr.getInt("gthr", -50), -80, -20);
  pr.end();
}

static void pdSave() {
  Preferences pr;
  pr.begin("ui", false);
  pr.putBytes("pdpos", pdPos, sizeof pdPos);
  pr.putInt("master", masterPct);
  pr.putInt("pedal", pedalIdx);
  pr.putBool("gate", gateOn);
  pr.putInt("gthr", gateDb);
  pr.end();
}

static uint32_t masterWord() {                  // MASTER 0..100 -> X:$3C: 40 dB audio taper like POT 1, 0-1 = off
  float p = masterPct / 100.0f;
  return p < 0.02f ? 0 : q23(powf(10.0f, 2.0f * (p - 1.0f)));
}

static void masterSet(int pct) {                // SETTINGS > MASTER: heard at once on the board
  masterPct = constrain(pct, 0, 100);
  pdSaveAt = millis() + 2000;
  if (uiMode == MODE_PEDAL && pdPlaying >= 0) {
    uint16_t a = 0x3C;
    uint32_t v = masterWord();
    onceWriteXLong(&a, &v, 1);
  }
}

static int pedalPots() {        // -1 = not on the board; 4 = a sim (the pots are its knobs, the output stage MASTER); AMP: 0
  if (uiMode != MODE_PEDAL) return -1;
  if (pedalIdx < PD_N) return pdPlaying == pedalIdx ? 4 : -1;
  return menu.mode == 0 && menu.fx1 == AMP_PEDAL.fx ? 0 : -1;
}

float pedalKnobVal(const PedalKnob &k) {          // AMP's knobs, 0..1 for the drawing
  if (k.src <= SRC_POT3) return constrain(sysMv[k.src] / 3100.0f, 0.0f, 1.0f);
  const FxParam &p = ampP[k.src - SRC_AMP];
  return (p.v - p.lo) / (float)(p.hi - p.lo);
}

static float boardKnobVal(int i, int k) { return i < PD_N ? pdPos[i][k] / 100.0f : pedalKnobVal(AMP_PEDAL.k[k]); }
static const char *boardKnobLabel(int i, int k) { return knobShort(i < PD_N ? PD_PEDALS[i].k[k].label : AMP_PEDAL.k[k].label); }
static bool boardByp(int i) { return i < PD_N ? pdByp : menu.byp1; }

// One knob table's words at the knobs' positions (1-D: val[step * nw + w], 2-D: val[(s0 * steps1 + s1) * nw + w])
static int pdTabRow(const PdDef &p, int t, const uint8_t *pos, uint16_t *a, uint32_t *v) {
  const PdTab &tb = p.tab[t];
  int row = (pos[tb.k[0]] * (tb.steps[0] - 1) + 50) / 100;
  if (tb.nk == 2) row = row * tb.steps[1] + (pos[tb.k[1]] * (tb.steps[1] - 1) + 50) / 100;
  for (int w = 0; w < tb.nw; w++) { a[w] = tb.addr[w]; v[w] = tb.val[row * tb.nw + w]; }
  return tb.nw;
}

// Pick a sim: route to CLEAN, write its param block, knob tables and curves (chunks of 128 words a halt), then INITF,
// the output stage (all wet, tone open, MASTER), STRIP off and the routing in the last halt: nothing half-written plays,
// and the engine re-inits on its next frame (DIRT X:$097F / MOD X:$0D5F = 0), so the old pedal's tail never sounds.
static uint16_t pkA[800];
static uint32_t pkV[800];

static bool pdPick(int i) {
  pdLoad();
  const PdDef &p = PD_PEDALS[i];
  uint16_t ra[3] = {0x20, 0x21, 0x3C};
  uint32_t rv[3] = {0, 0, 0};                     // CLEAN and muted: the halts below then repeat silence, not a buzz
  if (!onceWriteXLong(ra, rv, 3)) return false;
  delayMicroseconds(300);                         // ~13 samples: the mute reaches the DAC before the next halt
  pdPlaying = -1;
  uint16_t fa[48];
  uint32_t fv[48];
  int n = 0, nf = 0;
  auto put = [&](uint16_t a, uint32_t v) {
    if (a == 0x097F || a == 0x0D5F) { fa[nf] = a; fv[nf++] = v; }
    else if (n < 800) { pkA[n] = a; pkV[n++] = v; }
  };
  for (int j = 0; j < p.ninit; j++) put(p.ia[j], p.iv[j]);
  for (int t = 0; t < p.ntab; t++) {
    uint16_t a[8];
    uint32_t v[8];
    int m = pdTabRow(p, t, pdPos[i], a, v);
    for (int w = 0; w < m; w++) put(a[w], v[w]);
  }
  for (int c = 0; c < p.ncurve; c++)
    for (int j = 0; j < 257; j++) put(p.curve[c].addr + j, p.curve[c].val[j]);
  for (int s = 0; s < n; s += 128)
    if (!onceWriteXLong(pkA + s, pkV + s, min(128, n - s))) return false;
  auto fin = [&](uint16_t a, uint32_t v) { fa[nf] = a; fv[nf++] = v; };
  nf = gateFill(fa, fv, nf);                      // STRIP = the input gate only (on with B2), never the vocal chain
  fin(0x2F, 0); fin(0x3D, 0x7FFFFF); fin(0x3E, 0x7FFFFF); fin(0x3C, masterWord());
  if (p.nfx == 1) { fin(0x20, 0); fin(0x21, p.fx[0]); }
  else { fin(0x0200, p.nfx); for (int k = 0; k < p.nfx; k++) fin(0x0201 + k, p.fx[k]); fin(0x20, 3); }
  if (!onceWriteXLong(fa, fv, nf)) return false;
  pdPlaying = i;
  pdByp = false;
  pdDirty = 0;
  gateDirty = false;
  menu.strip = gateOn;
  return true;
}

static void pdSendKnob(int i, int k) {          // a knob's table rows (1-8 long X writes each), one halt
  const PdDef &p = PD_PEDALS[i];
  uint16_t a[32];
  uint32_t v[32];
  int n = 0;
  for (int t = 0; t < p.ntab && n <= 24; t++)
    if (p.tab[t].k[0] == k || (p.tab[t].nk == 2 && p.tab[t].k[1] == k)) n += pdTabRow(p, t, pdPos[i], a + n, v + n);
  if (n) onceWriteXLong(a, v, n);
}

static void pdSet(int k, int pos) {             // a knob of the shown sim moves (pot or encoder)
  int i = pedalIdx;
  if (i < PD_N && k == PD_PEDALS[i].nk) {         // the knob list's GATE row: far left = off
    gateSet(pos >= 3, -80 + pos * 60 / 100);
    return;
  }
  if (i >= PD_N || k < 0 || k >= PD_PEDALS[i].nk) return;
  pos = constrain(pos, 0, 100);
  if (pdPos[i][k] == pos) return;
  pdPos[i][k] = pos;
  pdSaveAt = millis() + 2000;
  if (pdPlaying == i) pdDirty |= 1 << k;          // goes out from pedalTick, at most every 25 ms
  uiDirty = true;
}

static void pdPotsArm() {                       // the pots let go: each takes over again only once it moves
  for (int p = 0; p < 3; p++) { pdPotRef[p] = pdPotMv[p] = sysMv[p]; pdPotOwn[p] = false; }
}

static void pdBypass() {                        // B1 on a sim = its footswitch: CLEAN <-> the pedal (state kept)
  const PdDef &p = PD_PEDALS[pdPlaying];
  uint16_t a[2] = {0x20, 0x21};
  uint32_t v[2] = {0, 0};
  int n = 2;
  if (pdByp && p.nfx == 1) v[1] = p.fx[0];
  if (pdByp && p.nfx > 1) { v[0] = 3; n = 1; }    // the chain list is still in X:$0200..
  bool ok = onceWriteXLong(a, v, n);
  if (ok) pdByp = !pdByp;
  displayStatus(!ok ? "DSP NOT ANSWERING" : pdByp ? "PEDAL BYPASSED" : "PEDAL ON", ok ? 0x30D060 : th::RED);
  uiDirty = true;
}

static void pedalApply(int idx) {                 // play board pedal idx
  uiMode = MODE_PEDAL;
  menu.preset = -1;
  pdSaveAt = millis() + 2000;                     // remembered as the last pedal
  if (idx < PD_N) {                               // a sim: the ESP's mode / FX1 say CLEAN (ids 17+ have no FX page)
    menu.mode = 0; menu.fx1 = 0; menu.byp1 = false;
    bool ok = pdPick(idx);
    pdPotsArm();
    displayStatus(ok ? PD_PEDALS[idx].name : "DSP NOT ANSWERING", ok ? PD_PEDALS[idx].col : th::RED);
    return;
  }
  pdPlaying = -1;
  const PedalDef &pd = AMP_PEDAL;                 // AMP: SINGLE + effect 6, the pots its LEVEL / GAIN / TREBLE
  menu.mode = 0; menu.fx1 = pd.fx; menu.byp1 = false;
  uint8_t aa[6] = {0x20, 0x21, POT_AA[0], POT_AA[1], POT_AA[2], POT_AA[3]};
  uint32_t v[6] = {0, pd.fx};
  potFill(sysMv, v + 2);
  bool ok = onceWriteXMany(aa, v, 6);
  if (ok) { for (int k = 0; k < 3; k++) potSent[k] = sysMv[k]; potSig = potMapSig(); }
  ampFollow();
  displayStatus(ok ? pd.name : "DSP NOT ANSWERING", ok ? pd.col : th::RED);
}

static void pedalOpen() {
  pdLoad();
  navGo(PAGE_PEDAL);
  pedalPrev = -1;
  pedalPending = -1;
  if (uiMode == MODE_PEDAL && pedalIdx < PD_N && pdPlaying == pedalIdx) { pdPotsArm(); return; }   // already playing
  pedalApply(pedalIdx);
}

static void pedalKnob(int d) {
  pedalPrev = pedalIdx;
  pedalIdx = wrapv(pedalIdx + d, N_PEDALS);
  pedalDir = d > 0 ? 1 : -1;
  pedalSwapT = millis();
  animUntil = pedalSwapT + 400;
  pedalPending = pedalIdx;
  pedalAt = millis();
}

void pedalTick() {                                // every loop: pedal swaps, the pots, knob words, the NVS save
  uint32_t now = millis();
  if (pedalPending >= 0 && now - pedalAt >= 250) {      // the sound follows once the knob rests
    int i = pedalPending;
    pedalPending = -1;
    pedalApply(i);
    uiDirty = true;
  }
  bool board = uiMode == MODE_PEDAL && pedalIdx < PD_N && pedalPending < 0 && (uiPage == PAGE_PEDAL || uiPage == PAGE_PKNOB);
  for (int p = 0; board && p < 3; p++) {
    int mv = sysMv[p];
    if (!pdPotOwn[p]) {
      if (abs(mv - pdPotRef[p]) < 150) continue;        // not moved yet: the knob keeps its setting
      pdPotOwn[p] = true;
    }
    if (abs(mv - pdPotMv[p]) < 20) continue;            // ADC jitter
    pdPotMv[p] = mv;
    int pos = constrain((mv * 100 + 1550) / 3100, 0, 100);
    pdSet(uiPage == PAGE_PKNOB ? pknobCur : p, pos);    // the knob list: any pot snaps the chosen knob
  }
  if (pdDirty && pdPlaying >= 0 && now - pdSendAt >= 25) {
    pdSendAt = now;
    for (int k = 0; k < 6; k++)
      if (pdDirty & (1 << k)) pdSendKnob(pdPlaying, k);
    pdDirty = 0;
  }
  if (gateDirty && pdPlaying >= 0 && uiMode == MODE_PEDAL && now - pdSendAt >= 25) {
    pdSendAt = now;
    gateDirty = false;
    uint16_t a[16];
    uint32_t v[16];
    if (onceWriteXLong(a, v, gateFill(a, v, 0))) menu.strip = gateOn;
  }
  if (pdSaveAt && (int32_t)(now - pdSaveAt) >= 0) { pdSaveAt = 0; pdSave(); }
}

// The knob list (ENTER on a sim): every knob as a row
static void pknobOpen() {
  navGo(PAGE_PKNOB);
  pknobCur = constrain(pknobCur, 0, pedalNk(pedalIdx));   // the last row is GATE
  pdPotsArm();
}

static void pknobMove(int d) {
  pknobCur = wrapv(pknobCur + d, pedalNk(pedalIdx) + 1);
  pdPotsArm();                                    // the knob left behind keeps what the pot set
}

static void pknobStep(int d) {                  // the encoder: 2 per click, switches toggle, mode knobs step
  if (pedalIdx >= PD_N) return;
  if (pknobCur == PD_PEDALS[pedalIdx].nk) {       // GATE: 1 dB a click; past -80 = off, a click up from off = on
    if (!gateOn) { if (d > 0) gateSet(true, gateDb); }
    else if (gateDb + d < -80) gateSet(false, gateDb);
    else gateSet(true, gateDb + d);
    return;
  }
  const PdKnob &k = PD_PEDALS[pedalIdx].k[pknobCur];
  int pos = pdPos[pedalIdx][pknobCur];
  if (k.steps <= 12) {
    int s = (pos * (k.steps - 1) + 50) / 100;
    s = k.steps == 2 ? (s + (d & 1)) % 2 : constrain(s + d, 0, k.steps - 1);
    pos = s * 100 / (k.steps - 1);
  } else pos += 2 * d;
  pdSet(pknobCur, pos);
}

static void pknobText(const PdKnob &k, int pos, char *s, int n) {
  if (k.steps == 2) snprintf(s, n, pos >= 50 ? "ON" : "OFF");
  else if (k.steps <= 12) snprintf(s, n, "%d", (pos * (k.steps - 1) + 50) / 100 + 1);
  else snprintf(s, n, "%d", pos);
}

static void drawPknob(uint32_t now) {
  backdrop();
  if (pedalIdx >= PD_N) return;
  const PdDef &p = PD_PEDALS[pedalIdx];
  th::header(plateName(pedalIdx), now);
  int rows = p.nk + 1, first = constrain(pknobCur - 4, 0, max(0, rows - 5));
  for (int i = first; i < rows && i < first + 5; i++) {
    char v[12];
    if (i < p.nk) pknobText(p.k[i], pdPos[pedalIdx][i], v, sizeof v);
    else if (gateOn) snprintf(v, sizeof v, "%d DB", gateDb);
    else snprintf(v, sizeof v, "OFF");
    th::row(24 + (i - first) * 17, i < p.nk ? p.k[i].label : "GATE", v, i == pknobCur, false, now,
            th::slide(now, pageT0, i - first));
  }
  statusOr(pdByp ? "BYPASSED (B1)" : pknobCur == p.nk ? "INPUT GATE, B2: ON/OFF" : "POT:SNAP T6/B6:MOVE");
}

// ---- MODE ring: VOCAL FX, PRESETS, PEDAL, SETTINGS, SYSTEM (ring3d.h draws it)
static const char *const MAIN_NAMES[5] = {"VOCAL FX", "PRESETS", "PEDAL", "SETTINGS", "SYSTEM"};
static int ringTarget = 0;                        // unbounded: the ring turns the short way
static float ringPos = 0;
static uint32_t ringArriveT = 0, ringLastDraw = 0;

static void mainMove(int d) {
  ringTarget += d;
  ringArriveT = millis() + 350;                   // the arrival spin starts as the turn settles
  animUntil = millis() + 1600;
}

static void mainEnter() {
  switch (wrapv(ringTarget, 5)) {
    case 0: navGo(PAGE_FX); break;
    case 1: presetOpen(); break;
    case 2: pedalOpen(); break;
    case 3: navGo(PAGE_TUNE); break;
    default: navGo(PAGE_SYS);
  }
}

static void drawMain(uint32_t now) {
  float dt = ringLastDraw ? (now - ringLastDraw) : 0;
  ringLastDraw = now;
  ringPos += (ringTarget - ringPos) * (1 - expf(-dt / 150.0f));
  if (fabsf(ringTarget - ringPos) < 0.002f) ringPos = ringTarget;
  float arrive = now < ringArriveT ? 0 : constrain((now - ringArriveT) / 1100.0f, 0.0f, 1.0f);
  arrive = 1 - (1 - arrive) * (1 - arrive) * (1 - arrive);
  if (ringArriveT == 0) arrive = 1;
  r3::drawRing(now, ringPos - 5 * floorf(ringTarget / 5.0f), uiMode, arrive, MAIN_NAMES);
  char s[24];                                     // what is playing
  if (uiMode == MODE_PRESETS && menu.preset >= 0) snprintf(s, sizeof s, "> %02d %s", PRESETS[menu.preset].n, PRESETS[menu.preset].name);
  else if (uiMode == MODE_PEDAL) snprintf(s, sizeof s, "> %s", pedalName(pedalIdx));
  else if (menu.mode == 0) snprintf(s, sizeof s, "> %s", menu.byp1 ? "BYPASS" : FX_NAMES[menu.fx1]);
  else snprintf(s, sizeof s, "> %s%s%s", FX_SHORT[menu.fx1], menu.mode == 1 ? "+" : ">", FX_SHORT[menu.fx2]);
  statusOr(s);
}

// At ESP start (e.g. after an OTA reboot the DSP keeps playing): take over the DSP's mode / FX so the screen shows
// what is actually playing. Values out of range (stock firmware running) are ignored.
void uiAdoptDsp() {
  uint8_t aa[3] = {0x20, 0x21, 0x22};
  uint32_t v[3];
  if (!onceReadXMany(aa, v, 3)) return;
  if (v[0] > 3 || v[1] >= (uint32_t)N_FX || v[2] >= (uint32_t)N_FX) return;
  menu.mode = v[0]; menu.fx1 = v[1]; menu.fx2 = v[2];
  uint16_t la[8] = {0x0207, 0x0200, 0x0201, 0x0202, 0x0203, 0x0204, 0x0205, 0x0206};   // STRIP flag, the chain
  uint32_t lv[8];
  if (onceReadXLong(la, lv, 8)) {
    if (lv[0] <= 1) menu.strip = lv[0];
    if (menu.mode == 3 && lv[1] >= 1 && lv[1] <= 6) {
      menu.chainN = lv[1];
      for (int i = 0; i < 6; i++) menu.chain[i] = lv[2 + i] < (uint32_t)N_FX ? lv[2 + i] : 0;
      int sp = presetSavedIdx();               // the preset loaded last: take it back when the chain matches
      if (sp >= 0 && sp < N_PRESETS && PRESETS[sp].chainN == menu.chainN &&
          !memcmp(PRESETS[sp].chain, menu.chain, menu.chainN)) {
        presetDecode(sp);
        menu.strip = lv[0] == 1;
        menu.preset = sp;
        uiMode = MODE_PRESETS;
        ringTarget = 1;
        ringPos = 1;
      }
    }
  }
  Serial.printf("DSP state adopted: mode=%d fx1=%d fx2=%d strip=%d preset=%d\n", menu.mode, menu.fx1, menu.fx2,
                menu.strip, menu.preset >= 0 ? PRESETS[menu.preset].n : 0);
}

static void stripSet(bool on) {            // the FX page's STRIP row: the vocal settings (the board's gate may have
  uint16_t aa[16];                         // left its own), then on / off
  uint32_t w[16];
  int n = 0;
  for (int i = 0; i < 5; i++) { aa[n] = stripP[i].addr; w[n++] = paramWord(stripP[i]); }
  n = stripLcFill(aa, w, stripEqFill(aa, w, n));
  aa[n] = 0x0207; w[n++] = on;
  bool ok = onceWriteXLong(aa, w, n);
  if (ok) menu.strip = on;
  displayStatus(ok ? (on ? "STRIP ON" : "STRIP OFF") : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
}

// The whole panel state to the DSP in one halt: mode, FX1/FX2 (bypassed = CLEAN), tune, pots. A freshly booted kernel
// starts on its own defaults, so after every boot this makes the sound match the screen and the knobs.
bool uiPushAll() {
  bool pr = menu.preset >= 0 && !presetDirty;    // an unedited preset goes out exactly as stored (after the rest)
  if (pr) menu.byp1 = false;
  uint8_t aa[20] = {0x20, 0x21, 0x22};
  uint32_t v[20] = {(uint32_t)(menu.mode == 3 && menu.byp1 ? 0 : menu.mode), (uint32_t)(menu.byp1 ? 0 : menu.fx1),
                    (uint32_t)(menu.byp2 ? 0 : menu.fx2)};
  tuneFill(aa + 3, v + 3);
  int mv[3];
  for (int k = 0; k < 3; k++) mv[k] = analogReadMilliVolts(PIN_POT[k]);
  memcpy(aa + 16, POT_AA, 4);
  potFill(mv, v + 16);
  bool ok = onceWriteXMany(aa, v, 20) && pushParams() && (!pr || applyPreset(menu.preset));
  if (ok && pedalPots() == 4) ok = pdPick(pdPlaying);   // a sim on the board: pick it again
  if (ok) { for (int k = 0; k < 3; k++) potSent[k] = mv[k]; potSig = potMapSig(); }
  displayStatus(ok ? "PANEL -> DSP" : "DSP NOT ANSWERING", ok ? 0x30D060 : th::RED);
  return ok;
}

// Change the selected value by d (encoder steps or K_R1)
static void uiChange(int d) {
  if (uiPage == PAGE_MAIN) { mainMove(d); uiShow(); return; }
  if (uiPage == PAGE_PEDAL) { pedalKnob(d); uiShow(); return; }
  if (uiPage == PAGE_PKNOB) { pknobStep(d); uiShow(); return; }
  if (uiPage == PAGE_EDIT) { editChange(d); if (menu.preset >= 0) presetDirty = true; uiShow(); return; }
  if (uiPage == PAGE_PRESET) { presetKnob(d); uiShow(); return; }
  int c = uiPage == PAGE_TUNE ? tuneCur : menu.cursor;
  if (uiPage == PAGE_FX) {
    if (c < 3) { menu.preset = -1; uiMode = MODE_VOCAL; }               // a manual setup: no preset any more
    if ((c == 1 || c == 2) && menu.mode == 3) {                          // FX 1 / FX 2 leave the chain
      menu.mode = c == 1 ? 0 : 1;
      menu.byp1 = false;
      send(0x20, menu.mode);
    }
    if (c == 0) { menu.mode = wrapv(menu.mode + d, N_MODES); menu.byp1 = false; send(0x20, menu.mode); }
    if (c == 1) { menu.fx1 = fxStep(menu.fx1, d); if (!menu.byp1) send(0x21, menu.fx1); }
    if (c == 2) { menu.fx2 = fxStep(menu.fx2, d); if (!menu.byp2) send(0x22, menu.fx2); }
    if (c == 3 && (d & 1)) { stripSet(!menu.strip); if (menu.preset >= 0) presetDirty = true; }   // every step toggles
    if ((c == 1 && menu.fx1 == 4) || (c == 2 && menu.fx2 == 4)) tuneSend();  // TUNE picked: push its settings
    if ((c == 1 && menu.fx1 == 10) || (c == 2 && menu.fx2 == 10)) harmSend(); // HARMONY: maps in the current key
    if (c < 3) ampFollow();                                              // AMP: its settings + pedal-mode pots
  } else if (uiPage == PAGE_TUNE && c == 5) {
    masterSet(masterPct + 2 * d);                        // MASTER: the pedal board's output (saved)
  } else if (uiPage == PAGE_TUNE && c == 4) {
    bg::setTheme(bg::theme + d);                         // THEME: menu colours (saved), MATCH SCENE first
  } else if (uiPage == PAGE_TUNE && c == 3) {
    r3::build();
    bg::set(bg::sel + d);                                // SCENE: the ring's background (saved)
  } else if (uiPage == PAGE_TUNE) {
    if (c == 0) menu.key = wrapv(menu.key + d, 12);
    if (c == 1) menu.scale = wrapv(menu.scale + d, 3);
    if (c == 2) menu.speed = constrain(menu.speed + d, 0, 10);
    if (c > 0 && menu.preset >= 0) presetDirty = true;   // the key is not part of a preset; scale / speed are
    tuneSend();
    if (c < 2 && fxInPath(10)) harmSend();                // HARMONY's diatonic voices follow the key
  }
  uiShow();
}

static int editMem[N_FX + 1];                    // EDIT cursor per effect (STRIP = the last slot)
static int editMemIdx(int fx) { return fx == FX_STRIP ? N_FX : constrain(fx, 0, N_FX - 1); }

static void cursorMove(int d) {
  if (uiPage == PAGE_SYS) return;
  if (uiPage == PAGE_MAIN) { mainMove(d); uiShow(); return; }
  if (uiPage == PAGE_PEDAL) { pedalKnob(d); uiShow(); return; }
  if (uiPage == PAGE_PKNOB) { pknobMove(d); uiShow(); return; }
  if (uiPage == PAGE_PRESET) { presetKnob(d); uiShow(); return; }
  if (uiPage == PAGE_EDIT) {
    int n = fxParams(editFx()).n;
    if (n) editCursor = wrapv(editCursor + d, n);
    editMem[editMemIdx(editFx())] = editCursor;
    uiShow();
    return;
  }
  if (uiPage == PAGE_TUNE) tuneCur = wrapv(tuneCur + d, 6);
  else menu.cursor = wrapv(menu.cursor + d, 4);                         // FX: MODE, FX 1, FX 2, STRIP
  uiShow();
}

static void editOpen() {                          // T5 / enter on the pedal board: the effect's settings
  if ((uiPage == PAGE_PEDAL || uiPage == PAGE_PKNOB) && pedalIdx < PD_N) { pknobOpen(); return; }   // a sim: its knobs
  editStrip = uiPage == PAGE_FX && menu.cursor == 3;
  navGo(PAGE_EDIT);
  int n = fxParams(editFx()).n;
  editCursor = n ? constrain(editMem[editMemIdx(editFx())], 0, n - 1) : 0;
}

static void bypass(int which) {
  if (pedalPots() == 4) {                    // a sim on the board: B1 is its footswitch
    if (which == 1) pdBypass(); else gateToggle();   // B2: the input gate
    return;
  }
  if (menu.mode == 3) {                      // CHAIN: B1 bypasses the whole chain (SINGLE + CLEAN), STRIP stays
    if (which != 1) { displayStatus("CHAIN: B1 BYPASSES", th::STEEL_L); return; }
    menu.byp1 = !menu.byp1;
    uint8_t aa[2] = {0x20, 0x21};
    uint32_t v[2] = {menu.byp1 ? 0u : 3u, 0};
    bool ok = onceWriteXMany(aa, v, menu.byp1 ? 2 : 1);
    if (!ok) menu.byp1 = !menu.byp1;
    displayStatus(!ok ? "DSP NOT ANSWERING" : menu.byp1 ? "CHAIN BYPASSED" : "CHAIN ON", ok ? 0x30D060 : th::RED);
    ampFollow();
    uiDirty = true;
    return;
  }
  bool &b = which == 1 ? menu.byp1 : menu.byp2;
  b = !b;
  send(which == 1 ? 0x21 : 0x22, b ? 0 : (which == 1 ? menu.fx1 : menu.fx2));  // bypass = CLEAN in that slot
  ampFollow();
  if (uiPage == PAGE_FX) uiShow();
}

static void freezeToggle() {                 // B3: REVERB's FREEZE (input off, the tail rings on)
  if (!fxInPath(12)) { displayStatus("NO REVERB TO FREEZE", th::STEEL_L); return; }
  FxParam &f = reverbP[6];
  f.v = !f.v;
  uint16_t aa = f.addr;
  uint32_t w = f.v;
  bool ok = onceWriteXLong(&aa, &w, 1);
  if (!ok) f.v = !f.v;
  displayStatus(!ok ? "DSP NOT ANSWERING" : f.v ? "FREEZE ON" : "FREEZE OFF", !ok ? th::RED : f.v ? 0x2E8BFF : 0x30D060);
  uiDirty = true;
}

void uiButton(int b) {
  if (faceOn) return;              // first touch only wakes the face
  if (!liveOn) uiShow();           // a serial command had the screen: take it back first
  if (uiPage == PAGE_TEST) { testPress(b); return; }
  switch (b) {
    case K_T1: navGo(PAGE_FX); uiShow(); break;
    case K_T2: navGo(PAGE_TUNE); uiShow(); break;
    case K_T3: navGo(PAGE_SYS); uiShow(); break;
    case K_T4: presetOpen(); uiShow(); break;
    case K_T5: editOpen(); uiShow(); break;
    case K_T6: cursorMove(-1); break;
    case K_B6: cursorMove(1); break;
    case K_R1: case K_B4: case K_B5:                         // ENTER: open (ring, pedal, preset list), else value +1
      if (uiPage == PAGE_SYS) testStart();
      else if (uiPage == PAGE_MAIN) { mainEnter(); uiShow(); }
      else if (uiPage == PAGE_PEDAL) { editOpen(); uiShow(); }
      else if (uiPage == PAGE_PRESET) { presetEnter(); uiShow(); }
      else uiChange(1);
      break;
    case K_R2: navBack(); uiShow(); break;                   // EXIT: one step back along the way you came
    case K_B1: bypass(1); break;
    case K_B2: bypass(2); break;
    case K_B3: freezeToggle(); break;
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
  if (uiPage != PAGE_FX && uiPage != PAGE_TUNE) navGo(PAGE_FX);
  if (k == '[') cursorMove(-1);
  else if (k == ']') cursorMove(1);
  else if (k == '-') uiChange(-1);
  else if (k == '=') uiChange(1);
}

void menuDraw() { navGo(PAGE_FX); uiShow(); }

// Which pedal the idle screen shows (or -1 = vocal: the face sings): FX1, else FX2 when it is in the chain
int idlePedal() {
  if (uiMode == MODE_PEDAL) return BOARD_FX + pedalIdx;           // the pedal board's pedal
  if (menu.mode == 3) {                      // CHAIN: its first pedal-type effect
    for (int i = 0; i < menu.chainN; i++) if (menu.chain[i] < N_FX && FX_PEDAL[menu.chain[i]]) return menu.chain[i];
    return -1;
  }
  if (FX_PEDAL[menu.fx1]) return menu.fx1;
  if (menu.mode != 0 && FX_PEDAL[menu.fx2]) return menu.fx2;
  return -1;
}
