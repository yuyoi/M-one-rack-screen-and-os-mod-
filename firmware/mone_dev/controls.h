// Control inputs: 3 pots, 2 resistor ladders (all ADC1), EC11 encoder without switch.
// Live readout on screen rows 0-3 whenever liveOn is set. Any serial command takes the rows over; 'i' gives them back.
#pragma once

const int PIN_POT[3] = {5, 6, 7};          // wipers; outer lugs 3V3 / GND
const int PIN_LADDER[2] = {1, 2};          // own 10k to 3V3 each, buttons pull down through their own resistor
const int PIN_ENC_A = 38, PIN_ENC_B = 39;  // common pin to GND
const int PIN_BTN[9] = {48, 47, 21, 20, 19, 40, 41, 42, 14};  // direct buttons (pin -> button -> GND, internal pullup); any order
const int N_DIRECT = sizeof(PIN_BTN) / sizeof(PIN_BTN[0]);
const int LADDER_MARGIN_MV[2] = {60, 60};  // press = this far below the tracked idle (L1 has one button left, ~1650 mV)
const int LADDER_AVG[2] = {64, 16};        // samples per reading: L1 has 2 buttons, so it can afford the quiet one
static int idleMv[2] = {3100, 3100};

int ladderMv(int k) {                      // averaged: 16 samples ~10 mV jitter, 64 samples a few mV
  int sum = 0;
  for (int i = 0; i < LADDER_AVG[k]; i++) sum += analogReadMilliVolts(PIN_LADDER[k]);
  return sum / LADDER_AVG[k];
}

bool liveOn = true;
bool faceOn = false;                       // idle face is on screen (face.h); the live rows stay hidden meanwhile
uint32_t lastActivity = 0;                 // last time any control moved
int actLook = 0;                           // where the face glances: -1 = pots (left of screen), +1 = buttons/encoder

void faceActivity(int dir) { lastActivity = millis(); actLook = dir; }
static int encSteps = 0;                   // quadrature transitions; one detent = 4
static uint8_t encPrev = 0;
static int encAcc = 0;                     // 1 = step taken, waiting to get back to the detent
bool encLog = false;                       // raw A/B transitions to serial (debug; 'E' toggles)
static int shown[6] = {-9999, -9999, -9999, -9999, -9999, -9999};
static int ladState[2] = {-1, -1};         // 1 = pressed

void controlsBegin() {
  pinMode(PIN_ENC_A, INPUT_PULLUP);
  pinMode(PIN_ENC_B, INPUT_PULLUP);
  for (int p : PIN_BTN) pinMode(p, INPUT_PULLUP);
  encPrev = (digitalRead(PIN_ENC_A) << 1) | digitalRead(PIN_ENC_B);
  analogSetAttenuation(ADC_11db);          // 0..~3.1 V
  for (int k = 0; k < 2; k++) {            // idle level, nothing pressed at power-on
    int sum = 0;
    for (int i = 0; i < 4; i++) sum += ladderMv(k);
    idleMv[k] = sum / 4;
    Serial.printf("LADDER%d idle %d mV\n", k + 1, idleMv[k]);
  }
}

// One step per detent, decided by the FIRST FALLING edge when the knob leaves the detent (both pins high):
// A falls first = +1, B falls first = -1. Rising edges are ignored: the TC board slows A's rise (RC), so the
// rise order is wrong turning right (logged 2026-10-16: right = 11>01>00>01>11, which a full decoder nets to 0).
// Falls are fast (contact to GND), so they are reliable. Re-armed once both pins are high again.
void encPoll() {
  uint8_t s = (digitalRead(PIN_ENC_A) << 1) | digitalRead(PIN_ENC_B);
  if (s == encPrev) return;
  if (encLog) Serial.printf("ENC %lu ms  %d%d -> %d%d\n", millis(), encPrev >> 1, encPrev & 1, s >> 1, s & 1);
  if (encPrev == 3 && encAcc == 0) {       // leaving the detent
    if (s == 1) { encSteps += 4; encAcc = 1; }        // 11 -> 01: A fell first
    else if (s == 2) { encSteps -= 4; encAcc = 1; }   // 11 -> 10: B fell first
  }
  if (s == 3) encAcc = 0;                  // back in a detent: re-arm
  encPrev = s;
}

// 'V': raw readout for remote checks (pots and ladders in mV, ladder idle levels, encoder count)
void cmdValues() {
  Serial.printf("VALUES pots %d %d %d mV | ladder1 %d (idle %d) ladder2 %d (idle %d) mV | enc %d\n",
                analogReadMilliVolts(PIN_POT[0]), analogReadMilliVolts(PIN_POT[1]), analogReadMilliVolts(PIN_POT[2]),
                ladderMv(0), idleMv[0], ladderMv(1), idleMv[1], encSteps / 4);
}

void liveRedraw() { for (int &v : shown) v = -9999; liveOn = true; faceOn = false; lastActivity = millis(); }

void btnEvent(int src, int val);           // buttons.h: src 1/2 = ladder (settled mV), 3 = direct (GPIO number)
bool rowsVisible();                        // ui (menu.h): the SYSTEM page with the live rows is on screen
void testPots(const int *v);               // ui (menu.h): pot bars on the button test page

// Call every loop: polls the encoder; every 50 ms reads pots/ladders/buttons, turns presses into button events
// (ladders at release, with the settled level; direct pins at press) and refreshes the live rows if visible.
void controlsTick() {
  encPoll();
  static uint32_t last = 0;
  if (millis() - last < 50) return;
  last = millis();
  int v[6];
  for (int k = 0; k < 3; k++) v[k] = analogReadMilliVolts(PIN_POT[k]);
  for (int k = 0; k < 2; k++) v[3 + k] = ladderMv(k);

  static uint16_t btnPrev = 0;              // direct buttons: 50 ms sampling = built-in debounce
  uint16_t btn = 0;
  for (int k = 0; k < N_DIRECT; k++) if (!digitalRead(PIN_BTN[k])) btn |= 1 << k;
  for (int k = 0; k < N_DIRECT; k++)
    if (((btn & ~btnPrev) >> k) & 1) { faceActivity(1); btnEvent(3, PIN_BTN[k]); }
  btnPrev = btn;

  bool ladIdle[2];
  for (int k = 0; k < 2; k++) {
    // hysteresis: press below idle-m, release above idle-m/2; idle tracks slow drift (WiFi start sinks it ~40 mV)
    int m = LADDER_MARGIN_MV[k];
    // press: below idle-m for 2 readings in a row (100 ms, kills single noise blips); release: above idle-m/2
    static int below[2], frac[2];
    below[k] = v[3 + k] < idleMv[k] - m ? below[k] + 1 : 0;
    bool idle = ladState[k] == 1 ? v[3 + k] > idleMv[k] - m / 2 : below[k] < 2;
    // idle = slow running average (1/16 per reading, remainder carried) while resting near it; a big jump up
    // (WiFi start, warm-up) is taken at once
    if (v[3 + k] > idleMv[k] + 3 * m) idleMv[k] = v[3 + k];
    else if (idle && v[3 + k] > idleMv[k] - m / 2) {
      frac[k] += v[3 + k] - idleMv[k];
      idleMv[k] += frac[k] / 16;
      frac[k] %= 16;
    }
    static int pFirst[2], pSum[2], pN[2];
    static uint32_t pT[2];
    if (!idle) {
      if (ladState[k] == 1) { pSum[k] += v[3 + k]; pN[k]++; }        // first sample may be mid-edge: kept apart
      else { pFirst[k] = v[3 + k]; pSum[k] = 0; pN[k] = 0; pT[k] = millis(); }
    }
    bool drift = false;
    if (!idle && ladState[k] == 1 && millis() - pT[k] > 3000 && v[3 + k] > idleMv[k] - (m + 20 > 60 ? m + 20 : 60)) {
      idleMv[k] = v[3 + k];                 // "press" parked just under idle for 3 s = drift, not a finger
      Serial.printf("LADDER%d idle re-learned %d mV\n", k + 1, v[3 + k]);
      idle = true;
      drift = true;
    }
    if (ladState[k] == 1 && idle && !drift) {
      int lvl = pN[k] ? pSum[k] / pN[k] : pFirst[k];
      Serial.printf("LADDER%d released, held at %d mV\n", k + 1, lvl);
      btnEvent(k + 1, lvl);
    }
    if (!idle) faceActivity(1);
    ladState[k] = !idle;
    ladIdle[k] = idle;
  }

  static int potAct[3] = {-9999, -9999, -9999};   // activity for the idle face
  static int encAct = 0;
  for (int k = 0; k < 3; k++)
    if (abs(v[k] - potAct[k]) > 120) { if (potAct[k] != -9999) faceActivity(-1); potAct[k] = v[k]; }
  if (encSteps != encAct) { faceActivity(encSteps > encAct ? 1 : -1); encAct = encSteps; }

  testPots(v);
  if (!rowsVisible()) return;
  char b[40];
  if (abs(v[0] - shown[0]) > 60 || abs(v[1] - shown[1]) > 60 || abs(v[2] - shown[2]) > 60) {
    snprintf(b, sizeof b, "%3d%%  %3d%%  %3d%%", v[0] / 31, v[1] / 31, v[2] / 31);
    displayRow(0, "POTS", b, C_YEL);
    for (int k = 0; k < 3; k++) shown[k] = v[k];
  }
  for (int k = 0; k < 2; k++) {
    if (abs(v[3 + k] - shown[3 + k]) <= 20) continue;
    snprintf(b, sizeof b, ladIdle[k] ? "%4d mV  idle" : "%4d mV  PRESS", v[3 + k]);
    displayRow(1 + k, k ? "LADDER 2" : "LADDER 1", b, ladIdle[k] ? C_GREY : C_GRN);
    shown[3 + k] = v[3 + k];
  }
  int e = encSteps * 4 + encPrev;          // steps + raw A/B bits, so a pin toggle alone redraws too
  if (e != shown[5]) {
    snprintf(b, sizeof b, "%d   A=%d B=%d", encSteps / 4, encPrev >> 1, encPrev & 1);
    displayRow(3, "ENCODER", b, C_BLUE);
    shown[5] = e;
  }
}
