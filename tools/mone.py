"""Capture the M-One flash through the ESP32-S3 J5 dumper.

  py -3.10 mone_dump.py COM7 test          # smoke test: sync + first 64 bytes
  py -3.10 mone_dump.py COM7 dump out.bin  # full dump (run twice, compare md5)
  py -3.10 mone_dump.py check out.bin      # sanity-check a saved dump
  py -3.10 mone_dump.py COM7 wifi          # store WiFi SSID/password on the ESP (asks, password hidden)
  py -3.10 mone_dump.py ota [mone.local]   # build + flash the firmware over WiFi
  py -3.10 mone_dump.py COM7 boot [dspdir]  # load autotune.hex + vocal.hex (+ its SRAM tables) + os.hex + codec_on.hex over J8, codec on + outputs unmuted, then the OS
Any COM7 above can be socket://mone.local:23 (or socket://<ip>:23): the same serial line over WiFi, no USB.
"""
import hashlib
import os
import struct
import sys
import time
import zlib

def open_port(name):                     # COMx, or socket://mone.local:23 (serial over WiFi)
    import serial
    s = serial.serial_for_url(name, do_not_open=True)
    s.baudrate, s.timeout = 115200, 5
    s.dtr = s.rts = False  # don't toggle the auto-reset lines (keeps the ESP running across runs)
    s.open()
    time.sleep(0.5)
    s.reset_input_buffer()
    return s

def read_exact(s, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = s.read(n - len(buf))
        if not chunk:
            raise SystemExit('timeout after %d of %d bytes' % (len(buf), n))
        buf += chunk
    return bytes(buf)

def check(data):
    print('size %d  md5 %s' % (len(data), hashlib.md5(data).hexdigest()))
    count = int.from_bytes(data[0:3], 'little')
    addr = int.from_bytes(data[3:6], 'little')
    print('Mode-1 boot record: count=%d words  load P:$%06X' % (count, addr))
    ok = 0 < count < 0x8000 and addr < 0x10000
    print('  plausible' if ok else '  NOT a plausible boot record (wiring/encoding issue?)')
    if len(set(data)) <= 2:
        print('  dump is constant (bus not read?)')
    n = len(data)
    while n > 0x8000 and data[:n // 2] == data[n // 2:n]:
        n //= 2
    if n < len(data):
        print('  mirrored: real chip size is %d KB' % (n // 1024))

def ota(host):
    import glob, subprocess, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    sketch = next(d for d in (os.path.join(here, '..', 'firmware', 'mone_dev'), os.path.join(here, 'mone_dumper')) if os.path.isdir(d))
    out = os.path.join(tempfile.gettempdir(), 'mone_build')
    subprocess.check_call(['arduino-cli', 'compile', '--fqbn', 'esp32:esp32:esp32s3', '--build-path', out, sketch])
    binf = [f for f in glob.glob(os.path.join(out, '*.ino.bin'))][0]
    espota = sorted(glob.glob(os.path.expanduser('~/AppData/Local/Arduino15/packages/esp32/hardware/esp32/*/tools/espota.py')))[-1]
    subprocess.check_call([sys.executable, espota, '-i', host, '-f', binf, '-r'])

def main():
    a = sys.argv[1:]
    if a and a[0] == 'check':
        check(open(a[1], 'rb').read())
        return
    if a and a[0] == 'ota':  # ota [host]: build the firmware and flash it over WiFi (default host mone.local)
        ota(a[1] if len(a) > 1 else 'mone.local')
        return
    if len(a) < 2:
        raise SystemExit(__doc__)
    s = open_port(a[0])
    if a[1] == 'wifi':  # wifi: store SSID/password on the ESP (NVS), it reboots onto them
        import getpass
        ssid = input('SSID: ')
        pw = getpass.getpass('password: ')
        s.write(b'W' + ssid.encode() + b'\t' + pw.encode() + b'\n')
        print(s.readline().decode(errors='replace').strip())
        end = time.time() + 15
        while time.time() < end:
            line = s.readline().decode(errors='replace').rstrip()
            if line.startswith('WIFI'):
                print(line)
                if 'up' in line: break
        return
    if a[1] in ('test', 'probe', 'stock', 'miso', 'sweep', 'jprobe', 'jid', 'regs', 'screen', 'spimode'):
        s.write({'test': b't', 'probe': b'p', 'stock': b'r', 'miso': b'm', 'sweep': b'w', 'jprobe': b'q', 'jid': b'j', 'regs': b'o', 'screen': b'c', 'spimode': b'M'}[a[1]])
        end = time.time() + (120 if a[1] == 'stock' else 15)
        while time.time() < end:
            line = s.readline().decode(errors='replace').rstrip()
            if line:
                print(line)
        return
    if a[1] == 'key':  # key CHARS  e.g. key ]=  (menu: [ ] cursor, - = value, F = draw FX page)
        s.write(a[2].encode())
        time.sleep(0.4 + 0.3 * len(a[2]))
        print(s.read(4000).decode(errors='replace').strip())
        return
    if a[1] == 'boot':  # boot [dspdir]: load autotune + os + codec_on, start codec_on (it starts the OS); needs the stock boot first
        d = a[2] if len(a) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dsp')
        start = None
        for name in ('autotune.hex', 'vocal.hex', 'vocal_tab.hex', 'vocal2.hex', 'vocal2_tab.hex', 'vocal3.hex', 'vocal3_tab.hex', 'amp.hex', 'amp_tab.hex', 'os.hex',
                     'codec_on.hex'):  # last one = start address
            lines = open(os.path.join(d, name)).read().split('\n')
            s.write(b'L%06X %s\n' % (int(lines[0], 16), lines[1].strip().encode()))
            start = int(lines[0], 16)
            end = time.time() + 30
            while time.time() < end:
                line = s.readline().decode(errors='replace').rstrip()
                if line.startswith(('LOADED', 'LOAD ')):
                    print(name, '->', line)
                    if 'OK' not in line: raise SystemExit('load failed, not starting')
                    break
            else:
                raise SystemExit('%s: no answer from the ESP' % name)
        s.write(b'G%06X\n' % start)
        print(s.readline().decode(errors='replace').rstrip())
        time.sleep(0.5)                      # the kernel clears its buffers, then sets its own defaults
        s.write(b'U\n')                      # ESP sends its panel state (mode, FX, bypass, tune): sound = screen
        end = time.time() + 10
        while time.time() < end:
            line = s.readline().decode(errors='replace').rstrip()
            if line.startswith('PUSH'):
                print(line)
                break
        else:
            print('no answer to U (old ESP firmware?): the DSP runs its defaults, SINGLE / HEAVY')
        return
    if a[1] in ('load', 'go'):  # load file.hex (line1 = base hex, line2 = words) | go ADDR
        if a[1] == 'load':
            lines = open(a[2]).read().split('\n')
            s.write(b'L%06X %s\n' % (int(lines[0], 16), lines[1].strip().encode()))
        else:
            s.write(b'G%06X\n' % int(a[2], 16))
        end = time.time() + 20
        while time.time() < end:
            line = s.readline().decode(errors='replace').rstrip()
            if line:
                print(line)
                if line.startswith(('LOADED', 'GO', 'LOAD ')): break
        return
    if a[1] in ('dump', 'jdump', 'pmem', 'xmem', 'ymem'):
        out = a[2]
        if a[1] in ('pmem', 'xmem', 'ymem'):  # pmem|xmem|ymem out.bin START COUNT (hex words)
            s.write(b'%s%06X%06X\n' % (a[1][0].upper().encode(), int(a[3], 16), int(a[4], 16)))
        else:
            s.write(b'd' if a[1] == 'dump' else b'D')
        hdr = read_exact(s, 8)
        if hdr != b'MONEDUMP':
            raise SystemExit('bad header %r (NOSYNC = dumper did not start)' % hdr)
        n = struct.unpack('<I', read_exact(s, 4))[0]
        t = time.time()
        data = bytearray()
        while len(data) < n:
            data += read_exact(s, min(65536, n - len(data)))
            print('\r%6d / %d KB  %.0f s' % (len(data) // 1024, n // 1024, time.time() - t), end='')
        print()
        crc = struct.unpack('<I', read_exact(s, 4))[0]
        if crc != zlib.crc32(data):
            raise SystemExit('CRC mismatch on the USB link, run again')
        open(out, 'wb').write(data)
        print('saved', out)
        if a[1] in ('dump', 'jdump'):
            check(bytes(data))

main()
