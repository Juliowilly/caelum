"""
Precipitation measured by weather radar, where there is radar:
  - MET Norway Nowcast 2.0: radar + stations every 5 min, for the Nordic countries;
  - RainViewer: a worldwide composite of national radars (Europe, the Americas, Japan,
    Australia, parts of Asia and Africa…), read from its map tiles.
Each returns {precip (mm/h), snow, thunder: None (radar can't tell), source: 'met_radar' |
'rainviewer'} (Nowcast adds the measured air: temp, humidity, wind) or None when the place isn't
covered or the request failed.
"""

import functools
import json
import math
import os
import struct
import time
import zlib

from .net import coord, get_bytes, get_json

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'radar_colors.json')
MIN_DBZ = 15            # below: drizzle too light to matter, or clutter
MAX_AGE = 30 * 60       # a radar frame older than this is no longer "now"


def rate_from_dbz(dbz):
    """Rain rate (mm/h) for a radar reflectivity, Marshall–Palmer (Z = 200 R^1.6)."""
    if dbz < MIN_DBZ:
        return 0.0
    return (10 ** (dbz / 10) / 200) ** (1 / 1.6)


# ─── MET Norway Nowcast (Nordic radar) ───────────────────────────────────────

# Rough box around its radar network; outside it the service answers 422 anyway
_NORDIC = (54.0, 72.0, 3.0, 32.0)


def met_nowcast(lat, lon):
    la0, la1, lo0, lo1 = _NORDIC
    if not (la0 <= lat <= la1 and lo0 <= lon <= lo1):
        return None
    try:
        d = get_json(f'https://api.met.no/weatherapi/nowcast/2.0/complete?lat={coord(lat)}&lon={coord(lon)}')
        props = d['properties']
        if props['meta'].get('radar_coverage') != 'ok':
            return None
        now = props['timeseries'][0]['data']['instant']['details']
        rate = float(now['precipitation_rate'])
        temp = float(now['air_temperature'])
        air = {'temp': temp, 'humidity': float(now['relative_humidity']),
               'wind_speed': float(now['wind_speed']), 'wind_dir': float(now['wind_from_direction'])}
    except Exception:
        return None
    # Nowcast's temperature and wind are station measurements spread over the map, so they
    # come along as observed too
    return {'precip': rate, 'snow': rate > 0 and temp <= 1.0, 'thunder': None,
            'source': 'met_radar', 'air': air}


# ─── RainViewer (worldwide radar composite) ──────────────────────────────────

_ZOOM = 7               # the largest zoom the free API serves: ~1 km per pixel near the equator
_COVERAGE_TTL = 24 * 3600


@functools.lru_cache(maxsize=1)
def _palette():
    with open(_DATA) as f:
        d = json.load(f)
    table = {}
    for kind in ('rain', 'snow'):
        for rgba, dbz in d[kind].items():
            table[bytes.fromhex(rgba)] = (dbz, kind == 'snow')
    return table


def _tile(lat, lon):
    """Tile (x, y) at _ZOOM holding the point, and the pixel inside it."""
    n = 2 ** _ZOOM
    x = (lon + 180.0) / 360.0 * n
    lat = max(-85.0, min(85.0, lat))
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(x) % n, int(y), int((x % 1) * 256), int((y % 1) * 256)


def png_pixels(data, x0, y0, r=1):
    """
    RGBA bytes of the pixels within r of (x0, y0) in an 8-bit, non-interlaced PNG (grey, RGB,
    palette, grey+alpha or RGBA). Values are as stored, not premultiplied. Raises ValueError
    on anything else.
    """
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    pos, idat, plte, trns = 8, [], b'', b''
    w = h = ctype = None
    while pos < len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b'IHDR':
            w, h, depth, ctype, _c, _f, interlace = struct.unpack('>IIBBBBB', chunk)
            if depth != 8 or interlace or ctype not in (0, 2, 3, 4, 6):
                raise ValueError('unsupported PNG')
        elif kind == b'PLTE':
            plte = chunk
        elif kind == b'tRNS':
            trns = chunk
        elif kind == b'IDAT':
            idat.append(chunk)
        elif kind == b'IEND':
            break
    if w is None:
        raise ValueError('no IHDR')
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b''.join(idat))
    stride = w * bpp
    last = min(h - 1, y0 + r)
    prev = bytearray(stride)
    rows = {}
    for y in range(last + 1):                   # filters chain row to row: decode from the top
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        if y >= y0 - r:
            rows[y] = bytes(line)
        prev = line
    out = []
    for y in range(max(0, y0 - r), last + 1):
        for x in range(max(0, x0 - r), min(w - 1, x0 + r) + 1):
            px = rows[y][x * bpp:(x + 1) * bpp]
            if ctype == 6:
                out.append(px)
            elif ctype == 2:
                out.append(px + b'\xff')
            elif ctype == 3:
                i = px[0]
                out.append(plte[3 * i:3 * i + 3] + (trns[i:i + 1] if i < len(trns) else b'\xff'))
            elif ctype == 4:
                out.append(px[:1] * 3 + px[1:])
            else:
                out.append(px * 3 + b'\xff')
    return out


_coverage = {}          # (x, y, px, py) → (checked at, covered)


def _covered(host, x, y, px, py):
    """Is the point inside RainViewer's radar coverage? (transparent = covered, black = not)"""
    key = (x, y, px, py)
    hit = _coverage.get(key)
    if hit and time.time() - hit[0] < _COVERAGE_TTL:
        return hit[1]
    png = get_bytes(f'{host}/v2/coverage/0/256/{_ZOOM}/{x}/{y}/0/0_0.png')
    covered = all(p[3] == 0 for p in png_pixels(png, px, py, 1))
    _coverage[key] = (time.time(), covered)
    return covered


def rainviewer(lat, lon):
    try:
        maps = get_json('https://api.rainviewer.com/public/weather-maps.json')
        host = maps['host']
        frame = maps['radar']['past'][-1]
        if time.time() - float(frame['time']) > MAX_AGE:
            return None
        x, y, px, py = _tile(lat, lon)
        if not _covered(host, x, y, px, py):
            return None
        png = get_bytes(f"{host}{frame['path']}/256/{_ZOOM}/{x}/{y}/2/1_1.png")
        pixels = png_pixels(png, px, py, 1)     # 3×3 px: about 3 km around the user
    except Exception:
        return None
    palette = _palette()
    rates, kinds = [], {False: 0, True: 0}
    for p in pixels:
        dbz, is_snow = palette.get(bytes(p), (None, False)) if p[3] else (None, False)
        rate = rate_from_dbz(dbz) if dbz is not None else 0.0
        rates.append(rate)
        if rate > 0:
            kinds[is_snow] += 1
    rate = sum(rates) / len(rates)
    if rate < 0.1:
        rate = 0.0          # a stray light pixel in the neighbourhood, not rain on the user
    return {'precip': round(rate, 2), 'snow': kinds[True] > kinds[False], 'thunder': None,
            'source': 'rainviewer'}
