// Control inputs: 3 pots, 2 resistor ladders (all ADC1), EC11 encoder without switch.
// Live readout on screen rows 0-3 whenever liveOn is set. Any serial command takes the rows over; 'i' gives them back.
#pragma once
#include <soc/soc.h>
#include <soc/gpio_reg.h>

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
static volatile int encSteps = 0;          // quadrature transitions; one detent = 4 (updated by the pin interrupt)
static volatile uint8_t encPrev = 0;
static volatile int encAcc = 0;            // 1 = step taken, waiting to get back to the detent
bool encLog = false;                       // step count to serial (debug; 'E' toggles)
static int shown[6] = {-9999, -9999, -9999, -9999, -9999, -9999};
static int ladState[2] = {-1, -1};         // 1 = pressed

// Encoder pins straight from the GPIO input register (IRAM-safe: digitalRead lives in flash). Both pins are >= 32.
static inline uint8_t encRead() {
  uint32_t in = REG_READ(GPIO_IN1_REG);
  return (((in >> (PIN_ENC_A - 32)) & 1) << 1) | ((in >> (PIN_ENC_B - 32)) & 1);
}

// One step per detent. The FIRST FALLING edge when the knob leaves the detent (both pins high) gives the direction:
// A falls first = +1, B falls first = -1. Rising edges are ignored: the TC board slows A's rise (RC), so the
// rise order is wrong turning right (logged 2026-10-16: right = 11>01>00>01>11, which a full decoder nets to 0).
// The step only COUNTS once both pins are low (00) and >= 150 us after that first fall: a real click always gets
// there, a noise spike never does (2026-10-17: screen pushes put spikes on the slow A pin, 30-40 false steps per
// click on the MODE ring). Re-armed once both pins are high again.
// Runs on every pin change (interrupt), so steps are never lost while a screen frame is being pushed.
static volatile int8_t encDir = 0;         // direction of the first fall since the detent, 0 = none yet
static volatile uint32_t encLeave = 0;     // CPU cycle count at that fall
void IRAM_ATTR encIsr() {
  uint8_t s = encRead();
  if (s == encPrev) return;
  uint32_t now = esp_cpu_get_cycle_count();
  if (encPrev == 3 && encAcc == 0) {       // leaving the detent: remember which pin fell first
    if (s == 1) { encDir = 1; encLeave = now; }          // 11 -> 01: A fell first
    else if (s == 2) { encDir = -1; encLeave = now; }    // 11 -> 10: B fell first
  }
  if (s == 0 && encDir && encAcc == 0 && now - encLeave > 150 * 240) {   // both low, and not a spike (240 MHz)
    encSteps = encSteps + 4 * encDir;
    encAcc = 1;
  }
  if (s == 3) { encAcc = 0; encDir = 0; }  // back in a detent: re-arm
  encPrev = s;
}

void controlsBegin() {
  pinMode(PIN_ENC_A, INPUT_PULLUP);
  pinMode(PIN_ENC_B, INPUT_PULLUP);
  for (int p : PIN_BTN) pinMode(p, INPUT_PULLUP);
  encPrev = encRead();
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), encIsr, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_B), encIsr, CHANGE);
  analogSetAttenuation(ADC_11db);          // 0..~3.1 V
  for (int k = 0; k < 2; k++) {            // idle level, nothing pressed at power-on
    int sum = 0;
    for (int i = 0; i < 4; i++) sum += ladderMv(k);
    idleMv[k] = sum / 4;
    Serial.printf("LADDER%d idle %d mV\n", k + 1, idleMv[k]);
  }
}

// Debug only now (the interrupt does the decoding): 'E' logs each step
void encPoll() {
  static int last = 0;
  if (encLog && encSteps != last) { Serial.printf("ENC %lu ms  step %d\n", millis(), encSteps / 4); last = encSteps; }
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
void potsToDsp(const int *mv);             // ui (menu.h): volume / mix / tone to the DSP

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
  potsToDsp(v);
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
