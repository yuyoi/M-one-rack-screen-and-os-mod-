// M-One OS UI: pages on the front controls; FX settings go live to the DSP kernel (dsp/os.py) over J8.
// Buttons by position (buttons.h):
//   T1 = FX page   T2 = TUNE page   T3 = SYSTEM page (live inputs, WiFi)
//   T6 / B6 = cursor up / down    encoder = change the selected value    R1 / B4 / B5 = enter (value +1)    R2 = back to FX
//   B1 / B2 = bypass FX1 / FX2 (toggle, works on any page)
//   SYSTEM page + enter = BUTTON TEST page (every button only lights its box there; R2 twice = back to FX)
// Serial keys from the PC do the same: '[' ']' cursor, '-' '=' value, 'F' FX page, 'T' button test.
#pragma once

bool onceWriteX(uint8_t aa, uint32_t value);  // in the .ino
bool onceWriteXMany(const uint8_t *aa, const uint32_t *value, int n);
bool onceReadXMany(const uint8_t *aa, uint32_t *value, int n);

enum { PAGE_FX, PAGE_TUNE, PAGE_SYS, PAGE_TEST };
int uiPage = PAGE_FX;

static const char *MODE_NAMES[] = {"SINGLE", "DOUBLE", "DBL-SINGLE"};
static const char *FX_NAMES[] = {"CLEAN", "HEAVY", "REVERSE", "COMP", "TUNE"};
static const char *KEY_NAMES[] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
static const char *SCALE_NAMES[] = {"CHROMATIC", "MAJOR", "MINOR"};
static const int N_MODES = 3, N_FX = 5;
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

static void menuItem(int row, const char *key, const char *val, bool sel, bool dim) {
  int y = 54 + row * 34;
  tft.fillRect(0, y, 240, 32, sel ? 0x202020 : C_BG);
  if (sel) tft.fillRect(0, y, 4, 32, C_YEL);
  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setTextDatum(middle_left);
  tft.setTextColor(dim ? 0x404040 : C_GREY);
  tft.drawString(key, 12, y + 16);
  tft.setFont(&fonts::FreeSansBold9pt7b);
  tft.setTextDatum(middle_right);
  tft.setTextColor(dim ? 0x404040 : (sel ? C_YEL : 0xFFFFFF));
  tft.drawString(val, 228, y + 16);
}

static void pageHeader(const char *title) {
  tft.fillScreen(C_BG);
  tft.fillRect(0, 0, 240, 44, C_YEL);
  tft.setTextColor(0x000000);
  tft.setFont(&fonts::FreeSansBold12pt7b);
  tft.setTextDatum(middle_center);
  tft.drawString(title, 120, 23);
  for (int i = 0; i < 3; i++) tft.fillCircle(212 + i * 9, 23, 3, i == uiPage ? 0x000000 : 0x806600);  // page dots
}

static void fxRouting() {          // signal-flow line under the items
  char a[16], b2[16], s[48];
  snprintf(a, sizeof a, "%s", menu.byp1 ? "-" : FX_NAMES[menu.fx1]);
  snprintf(b2, sizeof b2, "%s", menu.byp2 ? "-" : FX_NAMES[menu.fx2]);
  if (menu.mode == 0) snprintf(s, sizeof s, "IN > %s > OUT", a);
  else if (menu.mode == 1) snprintf(s, sizeof s, "IN > %s + %s > OUT", a, b2);
  else snprintf(s, sizeof s, "IN > %s > %s > OUT", a, b2);
  tft.setFont(&fonts::Font2);
  tft.setTextDatum(middle_center);
  tft.setTextColor(C_BLUE);
  tft.drawString(s, 120, 170);
}

// ---- Button test page: green = has worked, yellow = latest press, grey = not seen yet. Shows where the latest
// press came from (GPIO or ladder mV, "??" in red if it matches no learned button), the 3 pots and the encoder count.
static uint16_t testSeen = 0;              // bit per button
static int testLast = -1, testPrevKey = -1, testEnc = 0;
static int testPotShown[3] = {-9999, -9999, -9999};
static char testBig[8] = "", testSmall[32] = "";
static uint32_t testCol = C_GREY;

static void testTile(int i) {
  int x = i < 12 ? 6 + (i % 6) * 32 : 206, y = i < 6 ? 52 : (i < 12 ? 82 : (i == K_R1 ? 52 : 82));
  tft.fillRoundRect(x, y, 28, 26, 4, i == testLast ? C_YEL : ((testSeen >> i) & 1 ? C_GRN : 0x303030));
  tft.setFont(&fonts::Font2);
  tft.setTextDatum(middle_center);
  tft.setTextColor(i == testLast ? 0x000000 : 0xFFFFFF);
  tft.drawString(BTN_NAMES[i], x + 14, y + 13);
}

static void testInfo(const char *big, const char *small, uint32_t col) {
  snprintf(testBig, sizeof testBig, "%s", big);
  snprintf(testSmall, sizeof testSmall, "%s", small);
  testCol = col;
  tft.fillRect(0, 112, 240, 56, C_BG);
  tft.setTextDatum(middle_center);
  tft.setFont(&fonts::FreeSansBold18pt7b);
  tft.setTextColor(col);
  tft.drawString(testBig, 120, 132);
  tft.setFont(&fonts::Font2);
  tft.setTextColor(C_GREY);
  tft.drawString(testSmall, 120, 159);
}

static void testSource(char *s, size_t n, int src, int val) {
  if (src == 3) snprintf(s, n, "direct pin, GPIO %d", val);
  else snprintf(s, n, "ladder %d, %d mV", src, val);
}

static void testStatus() {
  int n = 0;
  for (int i = 0; i < K_N; i++) n += (testSeen >> i) & 1;
  char s[40];
  snprintf(s, sizeof s, "%d/%d ok   knob %+d   R2 x2 = exit", n, K_N, testEnc);
  displayStatus(s, n == K_N ? C_GRN : C_GREY);
}

void testStart() {
  uiPage = PAGE_TEST;
  testSeen = 0;
  testLast = testPrevKey = -1;
  testEnc = 0;
  snprintf(testBig, sizeof testBig, "press");
  snprintf(testSmall, sizeof testSmall, "every button lights its box");
  testCol = C_GREY;
  uiShow();
}

static void testPress(int b) {
  if (b == K_R2 && testPrevKey == K_R2) { uiPage = PAGE_FX; menu.cursor = 0; uiShow(); return; }
  testPrevKey = b;
  int prev = testLast;
  testLast = b;
  testSeen |= 1 << b;
  if (prev >= 0 && prev != b) testTile(prev);
  testTile(b);
  char s[32];
  testSource(s, sizeof s, lastBtnSrc, lastBtnVal);
  testInfo(BTN_NAMES[b], s, C_YEL);
  testStatus();
}

// From btnEvent: a press that matches no learned button
void uiUnknown(int src, int val) {
  if (uiPage != PAGE_TEST || !liveOn || faceOn) return;
  testPrevKey = -1;
  char s[32];
  testSource(s, sizeof s, src, val);
  testInfo("??", s, C_RED);
}

// From controlsTick (every 50 ms): pot bars, redrawn when a pot moves
void testPots(const int *v) {
  if (uiPage != PAGE_TEST || !liveOn || faceOn || learnIdx >= 0) return;
  for (int k = 0; k < 3; k++) {
    if (abs(v[k] - testPotShown[k]) <= 30) continue;
    testPotShown[k] = v[k];
    int x = 6 + k * 78, w = 72, pct = constrain(v[k] / 31, 0, 100);
    char s[16];
    snprintf(s, sizeof s, "POT%d %d%%", k + 1, pct);
    tft.setFont(&fonts::Font2);
    tft.setTextDatum(top_left);
    tft.setTextPadding(w);
    tft.setTextColor(C_YEL, C_BG);
    tft.drawString(s, x, 172);
    tft.setTextPadding(0);
    tft.fillRect(x, 191, w, 10, 0x303030);
    tft.fillRect(x, 191, w * pct / 100, 10, C_YEL);
  }
}

// Draw the current page from scratch
void uiShow() {
  liveOn = true;
  faceOn = false;
  if (uiPage == PAGE_SYS) {
    displayBegin(); liveRedraw(); wifiShow();
    displayStatus("enter = button test", C_GREY);
    return;
  }
  if (uiPage == PAGE_TEST) {
    pageHeader("BUTTON TEST");
    for (int i = 0; i < K_N; i++) testTile(i);
    testInfo(testBig, testSmall, testCol);
    for (int &s : testPotShown) s = -9999;  // next controlsTick draws the bars
    testStatus();
    return;
  }
  char v[24];
  if (uiPage == PAGE_FX) {
    pageHeader("FX");
    menuItem(0, "MODE", MODE_NAMES[menu.mode], menu.cursor == 0, false);
    snprintf(v, sizeof v, menu.byp1 ? "%s  off" : "%s", FX_NAMES[menu.fx1]);
    menuItem(1, "FX 1", v, menu.cursor == 1, menu.byp1);
    snprintf(v, sizeof v, menu.byp2 ? "%s  off" : "%s", FX_NAMES[menu.fx2]);
    menuItem(2, "FX 2", v, menu.cursor == 2, menu.mode == 0 || menu.byp2);
    fxRouting();
    displayStatus("knob = change   K_T6/K_B6 = select", C_GREY);
  } else {
    pageHeader("TUNE");
    menuItem(0, "KEY", KEY_NAMES[menu.key], menu.cursor == 0, false);
    menuItem(1, "SCALE", SCALE_NAMES[menu.scale], menu.cursor == 1, false);
    snprintf(v, sizeof v, menu.speed >= 9 ? "%d  ROBOT" : (menu.speed <= 2 ? "%d  NATURAL" : "%d"), menu.speed);
    menuItem(2, "SPEED", v, menu.cursor == 2, false);
    bool on = menu.fx1 == 4 || (menu.mode != 0 && menu.fx2 == 4);
    displayStatus(on ? "knob = change   T6/B6 = select" : "set FX 1 or FX 2 to TUNE", C_GREY);
  }
}

static void send(uint8_t aa, int v) {
  bool ok = onceWriteX(aa, v);
  displayStatus(ok ? "sent to DSP" : "DSP not answering", ok ? C_GRN : C_RED);
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
  displayStatus(ok ? "tune sent to DSP" : "DSP not answering", ok ? C_GRN : C_RED);
}

// ---- Pots -> the kernel's output stage (normal / vocal mode): POT1 volume, POT2 dry/wet mix, POT3 tone.
// (A later pedal mode can hand the three pots to the effect itself.)
extern bool dspAwake;                        // face.h: the power switch says the DSP runs
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
  bool ok = onceWriteXMany(aa, v, 20);
  if (ok) for (int k = 0; k < 3; k++) potSent[k] = mv[k];
  displayStatus(ok ? "panel state sent to DSP" : "DSP not answering", ok ? C_GRN : C_RED);
  return ok;
}

// Change the selected value by d (encoder steps or K_R1)
static void uiChange(int d) {
  int c = menu.cursor;
  if (uiPage == PAGE_FX) {
    if (c == 0) { menu.mode = wrapv(menu.mode + d, N_MODES); uiShow(); send(0x20, menu.mode); }
    if (c == 1) { menu.fx1 = wrapv(menu.fx1 + d, N_FX); uiShow(); if (!menu.byp1) send(0x21, menu.fx1); }
    if (c == 2) { menu.fx2 = wrapv(menu.fx2 + d, N_FX); uiShow(); if (!menu.byp2) send(0x22, menu.fx2); }
    if ((c == 1 && menu.fx1 == 4) || (c == 2 && menu.fx2 == 4)) tuneSend();  // TUNE picked: push its settings
  } else if (uiPage == PAGE_TUNE) {
    if (c == 0) menu.key = wrapv(menu.key + d, 12);
    if (c == 1) menu.scale = wrapv(menu.scale + d, 3);
    if (c == 2) menu.speed = constrain(menu.speed + d, 0, 10);
    uiShow();
    tuneSend();
  }
}

static void cursorMove(int d) {
  if (uiPage == PAGE_SYS) return;
  menu.cursor = wrapv(menu.cursor + d, 3);
  uiShow();
}

static void bypass(int which) {
  bool &b = which == 1 ? menu.byp1 : menu.byp2;
  b = !b;
  if (uiPage == PAGE_FX) uiShow();
  send(which == 1 ? 0x21 : 0x22, b ? 0 : (which == 1 ? menu.fx1 : menu.fx2));  // bypass = CLEAN in that slot
}

void uiButton(int b) {
  if (faceOn) return;              // first touch only wakes the face
  if (!liveOn) uiShow();           // a serial command had the screen: take it back first
  if (uiPage == PAGE_TEST) { testPress(b); return; }
  switch (b) {
    case K_T1: uiPage = PAGE_FX; menu.cursor = 0; uiShow(); break;
    case K_T2: uiPage = PAGE_TUNE; menu.cursor = 0; uiShow(); break;
    case K_T3: uiPage = PAGE_SYS; uiShow(); break;
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
      snprintf(m, sizeof m, "%s: not assigned yet", BTN_NAMES[b]);
      displayStatus(m, C_GREY);
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
  if (uiPage == PAGE_TEST) { testEnc += d; testStatus(); return; }
  uiChange(d);
}

// Serial keys (PC): '[' ']' cursor, '-' '=' value
void menuKey(char k) {
  liveOn = true;
  if (uiPage == PAGE_SYS || uiPage == PAGE_TEST) uiPage = PAGE_FX;
  if (k == '[') cursorMove(-1);
  else if (k == ']') cursorMove(1);
  else if (k == '-') uiChange(-1);
  else if (k == '=') uiChange(1);
}

void menuDraw() { uiPage = PAGE_FX; uiShow(); }
