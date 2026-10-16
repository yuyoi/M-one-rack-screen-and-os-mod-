// WiFi + ArduinoOTA. Credentials live in NVS (never in the source): set them once over USB with
//   python tools/mone.py COMx wifi        (asks for SSID and password, sends "W<ssid>\t<pass>\n")
// Then flash over the air:  python tools/mone.py ota  (or espota.py -i mone.local -f build.bin)
#pragma once
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <Preferences.h>

static bool otaUp = false;

void wifiStart() {
  Preferences p;
  p.begin("wifi", true);
  String ssid = p.getString("ssid", ""), pass = p.getString("pass", "");
  p.end();
  if (!ssid.length()) return;
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("mone");
  WiFi.setSleep(false);  // modem-sleep current bursts dip 3V3 and flicker the backlight
  WiFi.begin(ssid.c_str(), pass.c_str());
}

void wifiShow() {           // row 4 of the SYSTEM page: IP + signal (dBm: -50 great, -70 ok, -80 weak)
  if (!rowsVisible()) return;
  if (otaUp) {
    char v[32];
    int r = WiFi.RSSI();
    snprintf(v, sizeof v, "%s %ddBm", WiFi.localIP().toString().c_str(), r);
    displayRow(4, "WIFI", v, r > -70 ? C_GRN : (r > -80 ? C_YEL : C_RED));
  }
  else displayRow(4, "WIFI", WiFi.getMode() == WIFI_STA ? "connecting..." : "not set (mone.py wifi)", C_GREY);
}

// Call every loop: brings OTA up once WiFi connects, then services it
void otaTick() {
  if (otaUp) {
    ArduinoOTA.handle();
    static uint32_t lastShow = 0;            // signal strength on the SYSTEM page, every 2 s
    if (millis() - lastShow > 2000) { lastShow = millis(); wifiShow(); }
    return;
  }
  if (WiFi.status() != WL_CONNECTED) return;
  ArduinoOTA.setHostname("mone");
  ArduinoOTA.onStart([]() { liveOn = false; displayStatus("OTA update...", C_YEL); });
  ArduinoOTA.onProgress([](unsigned int done, unsigned int total) {
    static int lastPct = -1;
    int pct = done * 100 / total;
    if (pct / 5 != lastPct / 5) { char b[24]; snprintf(b, sizeof b, "OTA %d%%", pct); displayStatus(b, C_YEL); lastPct = pct; }
  });
  ArduinoOTA.onEnd([]() { displayStatus("OTA done, rebooting", C_GRN); });
  ArduinoOTA.onError([](ota_error_t e) { char b[24]; snprintf(b, sizeof b, "OTA error %u", e); displayStatus(b, C_RED); });
  ArduinoOTA.begin();
  otaUp = true;
  for (int k = 0; k < 2; k++) idleMv[k] = ladderMv(k);  // WiFi on sinks the ladder idle ~40 mV: re-measure
  String ip = WiFi.localIP().toString();
  Serial.printf("WIFI up %s (mone.local), OTA ready\n", ip.c_str());
  wifiShow();
}

// W<ssid>\t<pass>\n : save credentials and reboot onto them
void cmdWifi() {
  String l = Serial.readStringUntil('\n');
  l.trim();
  int t = l.indexOf('\t');
  if (t < 1) { Serial.println("WIFI usage: W<ssid><TAB><pass>"); return; }
  Preferences p;
  p.begin("wifi", false);
  p.putString("ssid", l.substring(0, t));
  p.putString("pass", l.substring(t + 1));
  p.end();
  Serial.println("WIFI saved, rebooting");
  delay(200);
  ESP.restart();
}
