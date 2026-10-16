"""Fetch the DSP56300 opcode table and build tools/opcodes56300.json for dis56k.py.

The table comes from the GPL-3.0 dsp56300 emulator (github.com/dsp56300/dsp56300, opcodeinfo.h).
It is downloaded and converted locally and never committed, so this repo stays MIT.

    python tools/fetch_opcodes.py
"""
import json
import os
import re
import urllib.request

URL = 'https://raw.githubusercontent.com/dsp56300/dsp56300/dsp56300/source/dsp56kEmu/opcodeinfo.h'
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    src = urllib.request.urlopen(URL, timeout=60).read().decode('utf-8', 'replace')
    rows = re.findall(r'OpcodeInfo\(([A-Za-z_0-9]+),\s*"([01a-zA-Z?]{24})",\s*"([^"]*)"(?:,\s*([A-Za-z]+))?', src)
    rows = [list(r) for r in rows if r[0] not in ('ResolveCache', 'Parallel')]
    if len(rows) < 200:
        raise SystemExit('only %d opcodes parsed - upstream format changed?' % len(rows))
    out = os.path.join(HERE, 'opcodes56300.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=0)
    print('wrote %s (%d opcodes)' % (out, len(rows)))


if __name__ == '__main__':
    main()
