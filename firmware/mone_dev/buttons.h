// Front buttons by POSITION: T1-T6 top row, B1-B6 bottom row (left to right), R1/R2 right column (top/bottom).
// (enum names carry a K_ prefix: Arduino already defines T1.. and B1)
// Each one is a ladder level (ladder 1 or 2, settled mV) or a direct GPIO. The map is learned once on the device
// (first boot with no map, or serial 'K'): the screen asks for each position in turn; turning the encoder skips a
// position (dead button). Stored in NVS.
#pragma once
#include <Preferences.h>

enum { K_T1, K_T2, K_T3, K_T4, K_T5, K_T6, K_B1, K_B2, K_B3, K_B4, K_B5, K_B6, K_R1, K_R2, K_N };
static const char *BTN_NAMES[K_N] = {"T1", "T2", "T3", "T4", "T5", "T6", "B1", "B2", "B3", "B4", "B5", "B6", "R1", "R2"};
const int BTN_MATCH_MV = 80;               // a ladder press matches a learned level within this

struct BtnMap { int8_t src[K_N]; int16_t val[K_N]; uint8_t done; } btnMap;  // src: 0 none/skipped, 1/2 ladder, 3 GPIO
int learnIdx = -1;                          // >= 0 while learning

void uiButton(int b);                       // menu.h
void uiUnknown(int src, int val);           // menu.h: a press that matches no learned button
void uiShow();
int lastBtnSrc = 0, lastBtnVal = 0;         // source of the latest press (shown on the button test page)

void btnLoad() {
  Preferences p;
  p.begin("btn", true);
  size_t n = p.getBytes("map", &btnMap, sizeof btnMap);
  p.end();
  if (n != sizeof btnMap) memset(&btnMap, 0, sizeof btnMap);
}

void btnSave() {
  Preferences p;
  p.begin("btn", false);
  p.putBytes("map", &btnMap, sizeof btnMap);
  p.end();
}

bool btnMapped() { return btnMap.done == 1; }

// Panel sketch: 6 + 6 boxes and the right pair; done = green, current = yellow
// The 14 button tiles (learn screen + button test page): T1-T6 / B1-B6 rows, R1/R2 at the right
void drawTiles(int y0, int lit, uint16_t done, uint32_t litCol) {
  for (int i = 0; i < K_N; i++) {
    int x = i < 12 ? 2 + (i % 6) * 17 : 104, y = i < 6 ? y0 : (i < 12 ? y0 + 14 : (i == K_R1 ? y0 : y0 + 14));
    bool on = (done >> i) & 1;
    uint32_t c = i == lit ? litCol : (on ? 0x30D060 : th::STEEL_D);
    th::bevel(x, y, x + 15, y + 11, th::p15(c), th::p15(i == lit || on ? th::WHITE : th::STEEL), th::BLACK);
    th::text(x + 8, y + 3, BTN_NAMES[i], i == lit || on ? th::BLACK : th::p15(th::STEEL_L), 1, 'm');
  }
}

static void learnDraw() {
  if (!th::ready) return;
  th::cv.fillScreen(th::BLACK);
  th::header("LEARN", millis());
  drawTiles(26, learnIdx, learnIdx > 0 ? (1 << learnIdx) - 1 : 0, th::YELLOW);
  char b[16];
  snprintf(b, sizeof b, "PRESS %s", BTN_NAMES[learnIdx]);
  th::metal(60, 64, b, 2, th::WHITE, th::YELLOW, 'm');
  th::text(60, 86, "ONE AT A TIME", th::p15(th::STEEL_L), 1, 'm');
  th::status("PRESS ONCE KNOB:SKIP");
  th::present();
}

void btnLearnStart() {
  learnIdx = 0;
  memset(&btnMap, 0, sizeof btnMap);
  learnDraw();
  Serial.println("LEARN start: press T1..T6, B1..B6, R1, R2 (encoder = skip)");
}

// From controls.h: src 1/2 = ladder (val = settled mV), 3 = direct (val = GPIO)
void btnEvent(int src, int val) {
  if (learnIdx >= 0) {
    for (int i = 0; i < learnIdx; i++)
      if (btnMap.src[i] == src && (src == 3 ? btnMap.val[i] == val : abs(btnMap.val[i] - val) < 40)) {
        char m[32];
        snprintf(m, sizeof m, "same as %s - try again", BTN_NAMES[i]);
        displayStatus(m, C_RED);
        Serial.printf("LEARN %s: level %d already used by %s\n", BTN_NAMES[learnIdx], val, BTN_NAMES[i]);
        return;
      }
    btnMap.src[learnIdx] = src;
    btnMap.val[learnIdx] = val;
    Serial.printf("LEARN %s = %s %d\n", BTN_NAMES[learnIdx], src == 3 ? "GPIO" : (src == 1 ? "ladder1 mV" : "ladder2 mV"), val);
    if (++learnIdx == K_N) {
      learnIdx = -1;
      btnMap.done = 1;
      btnSave();
      Serial.println("LEARN done, saved");
      uiShow();
    } else {
      learnDraw();
    }
    return;
  }
  lastBtnSrc = src;
  lastBtnVal = val;
  int best = -1, bestD = 1 << 30;
  for (int i = 0; i < K_N; i++) {
    if (btnMap.src[i] != src) continue;
    int d = src == 3 ? (btnMap.val[i] == val ? 0 : 1 << 30) : abs(btnMap.val[i] - val);
    if (d < bestD) { bestD = d; best = i; }
  }
  if (best < 0 || bestD > (src == 3 ? 0 : BTN_MATCH_MV)) {
    Serial.printf("BTN unknown: %s %d (re-learn with K?)\n", src == 3 ? "GPIO" : "ladder", val);
    uiUnknown(src, val);
    return;
  }
  Serial.printf("KEY %s\n", BTN_NAMES[best]);
  uiButton(best);
}

// Encoder during learning: skip this position (dead / not fitted)
void btnLearnSkip() {
  Serial.printf("LEARN %s skipped\n", BTN_NAMES[learnIdx]);
  if (++learnIdx == K_N) { learnIdx = -1; btnMap.done = 1; btnSave(); Serial.println("LEARN done, saved"); uiShow(); }
  else learnDraw();
}
