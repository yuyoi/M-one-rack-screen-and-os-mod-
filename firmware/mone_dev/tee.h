// Serial over WiFi: TCP port 23 mirrors the serial line both ways (one client at a time), so every command,
// log and dump works with no USB cable:  python tools/mone.py socket://mone.local:23 jid
// Included first in the .ino: after this, "Serial" in every file means Tee (UART + TCP).
#pragma once
#include <Arduino.h>
#include <WiFi.h>

class TeeStream : public Stream {
 public:
  explicit TeeStream(HardwareSerial &h) : hw(h) {}
  void begin(unsigned long baud) { hw.begin(baud); }
  void poll() {                                   // call every loop: starts the server, takes a new client
    if (!started && WiFi.status() == WL_CONNECTED) { server.begin(); server.setNoDelay(true); started = true; }
    if (started && server.hasClient()) {
      if (client) client.stop();
      client = server.accept();
    }
  }
  int available() override { return hw.available() + (client ? client.available() : 0); }
  int read() override { return hw.available() ? hw.read() : (client ? client.read() : -1); }
  int peek() override { return hw.available() ? hw.peek() : (client ? client.peek() : -1); }
  size_t write(uint8_t c) override { return write(&c, 1); }
  size_t write(const uint8_t *b, size_t n) override {
    hw.write(b, n);
    if (client && client.connected()) client.write(b, n);
    return n;
  }
  void flush() override { hw.flush(); }

 private:
  HardwareSerial &hw;
  WiFiServer server{23};
  WiFiClient client;
  bool started = false;
};

TeeStream Tee(Serial0);
#undef Serial
#define Serial Tee
