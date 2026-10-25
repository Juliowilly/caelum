#!/usr/bin/env python3
"""
Build caelum/data/radar_colors.json: RainViewer's "Universal Blue" palette (the one its free
API serves) mapped back to radar reflectivity, so a tile pixel can be read as a rain rate.

Developer tool:  python3 packaging/make-radar-colors.py
"""

import csv
import io
import json
import os
import urllib.request

URL = 'https://www.rainviewer.com/files/rainviewer_api_colors_table.csv'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'caelum', 'data', 'radar_colors.json')


def main():
    with urllib.request.urlopen(URL, timeout=20) as r:
        rows = list(csv.reader(io.StringIO(r.read().decode())))
    col = rows[0].index('Universal Blue')
    # The table lists every dBZ (-32…95) twice: rain, then snow
    body = rows[1:]
    half = len(body) // 2
    out = {'source': URL, 'palette': 'Universal Blue', 'rain': {}, 'snow': {}}
    for kind, part in (('rain', body[:half]), ('snow', body[half:])):
        for r in part:
            rgba = r[col].lower().lstrip('#')
            if rgba[6:] != '00':                       # transparent: nothing there
                out[kind].setdefault(rgba, int(r[0]))  # first (lowest) dBZ for a colour
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write('\n')
    print(f"{len(out['rain'])} rain and {len(out['snow'])} snow colours → {OUT}")


if __name__ == '__main__':
    main()
