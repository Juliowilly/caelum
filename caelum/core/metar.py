"""
Observed weather from the nearest airport: METAR reports (every 30–60 min, from the weather
station on the runway) through the US Aviation Weather Center's free API. Unlike the forecast
models, they say what the sky, the rain, the wind and the temperature actually are now.
"""

import math
import re
import time

from .net import coord, get_json

MAX_KM  = 30.0          # an airport farther than this says little about the weather where the user is
MAX_AGE = 90 * 60       # older reports are stale (stations report every 30 or 60 min)
_URL = 'https://aviationweather.gov/api/data/metar?bbox={},{},{},{}&format=json&hours=3'
_BOX = 0.30             # degrees of latitude around the user to search (~33 km)

# Present-weather group: intensity, descriptor, precipitation — e.g. -RA, +TSRA, SHRA, DZ, -SN
_WX = re.compile(r'^(?P<int>[-+])?(?P<desc>SH|TS|FZ)?(?P<precip>(?:DZ|RA|SN|SG|PL|GR|GS|UP)+)$')
_HEAD = re.compile(r'^(?:METAR|SPECI)(?: COR)? [A-Z0-9]{4} \d{6}Z ')
# Rough rates (mm/h) for the intensities a METAR gives
_RATE = {'DZ': (0.1, 0.3, 0.6), 'other': (0.5, 2.5, 8.0)}
_WIND = re.compile(r'^(?P<dir>\d{3}|VRB)(?P<speed>\d{2,3})(?:G\d{2,3})?(?P<unit>KT|MPS|KMH)$')
_WIND_UNIT = {'KT': 0.5144, 'MPS': 1.0, 'KMH': 1 / 3.6}
_TEMP = re.compile(r'^(?P<t>M?\d{2})/(?P<d>M?\d{2})?$')
_CLOUD = re.compile(r'^(?P<cover>FEW|SCT|BKN|OVC)(?P<base>\d{3})(?:CB|TCU|///)?$')
# Oktas → cover: FEW 1–2, SCT 3–4, BKN 5–7, OVC 8
_COVER = {'FEW': 19, 'SCT': 44, 'BKN': 75, 'OVC': 100}
_ALL, _AUTO_TOP = 99999, 12000
# Sky-clear groups and the height (ft) up to which they vouch that there is no cloud:
# CAVOK / NSC say nothing about clouds above 5,000 ft; CLR / NCD are automatic stations
_CLEAR = {'CAVOK': 5000, 'NSC': 5000, 'SKC': _ALL, 'CLR': _AUTO_TOP, 'NCD': _AUTO_TOP}
_CLASSES = ((0, 6500), (6500, 20000), (20000, _ALL + 1))


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def humidity(temp, dew):
    """Relative humidity (%) from temperature and dew point (°C), Magnus formula."""
    def f(t):
        return math.exp(17.625 * t / (243.04 + t))
    return max(0.0, min(100.0, 100.0 * f(dew) / f(temp)))


def _deg(t):
    return -int(t[1:]) if t.startswith('M') else int(t)


def parse(raw):
    """
    What a METAR reports now, or None if the report is malformed:
      precip (mm/h), snow, thunder — the present weather;
      temp, humidity, wind_speed (m/s), wind_dir (° it blows from; None if variable) — or None;
      layers [(cover %, base in ft)], auto (an automatic station), sensed_top (ft): the height
      up to which the report vouches for the sky (above it, clouds may be there unreported).
    Remarks (RMK …), the trend (NOSIG, BECMG, TEMPO) and recent weather (RERA) are not the
    present weather and are ignored.
    """
    if not isinstance(raw, str) or not _HEAD.match(raw) or raw.count('METAR') + raw.count('SPECI') > 1:
        return None
    obs = {'precip': 0.0, 'snow': False, 'thunder': False,
           'temp': None, 'humidity': None, 'wind_speed': None, 'wind_dir': None,
           'layers': [], 'auto': False, 'sensed_top': None}
    for tok in raw.split()[3:]:
        if tok in ('RMK', 'NOSIG', 'BECMG', 'TEMPO'):
            break
        if tok == 'AUTO':
            obs['auto'] = True
            continue
        if tok in ('TS', '+TS', '-TS'):
            obs['thunder'] = True
            continue
        m = _WIND.match(tok)
        if m:
            speed = int(m['speed']) * _WIND_UNIT[m['unit']]
            obs['wind_speed'] = round(speed, 1)
            obs['wind_dir'] = None if m['dir'] == 'VRB' or speed == 0 else float(m['dir'])
            continue
        m = _TEMP.match(tok)
        if m:
            obs['temp'] = float(_deg(m['t']))
            if m['d']:
                obs['humidity'] = round(humidity(obs['temp'], _deg(m['d'])))
            continue
        m = _CLOUD.match(tok)
        if m:
            obs['layers'].append((_COVER[m['cover']], int(m['base']) * 100))
            continue
        if tok in _CLEAR:
            obs['sensed_top'] = _CLEAR[tok]
            continue
        if tok.startswith('VV'):
            obs['layers'].append((100, 0))          # sky hidden by fog: an overcast at the ground
            continue
        m = _WX.match(tok)
        if not m:
            continue
        precip = m['precip']
        level = {'-': 0, None: 1, '+': 2}[m['int']]
        rate = _RATE['DZ' if precip == 'DZ' else 'other'][level]
        obs['precip'] = max(obs['precip'], rate)
        obs['snow'] = obs['snow'] or any(s in precip for s in ('SN', 'SG', 'PL'))
        obs['thunder'] = obs['thunder'] or m['desc'] == 'TS'
    if obs['sensed_top'] is None:
        # Observers report every significant layer; ceilometers only see the lower ~12,000 ft
        obs['sensed_top'] = _AUTO_TOP if obs['auto'] else _ALL
    return obs


def sky(obs, model):
    """
    Cloud cover (low, mid, high) in % from the report, keeping the model's value for any layer
    the report can't vouch for (above its sensed_top, e.g. cirrus over an automatic station).
    Layers: low < 6,500 ft (2 km), mid < 20,000 ft (6 km), high above.
    """
    out = []
    for (lo, hi), mod in zip(_CLASSES, model):
        seen = [c for c, base in obs['layers'] if lo <= base < hi]
        in_sight = (min(hi, obs['sensed_top']) - lo) / (hi - lo)
        if seen or in_sight >= 0.5:
            out.append(max(seen, default=0))        # the report covers (most of) this layer
        else:
            out.append(mod)                         # out of its sight: keep the model
    return tuple(out)


def nearest(reports, lat, lon, now=None):
    """
    The latest usable report of the nearest airport within MAX_KM, as parse() gives it plus
    station, km and time; None if there is none.
    """
    now = time.time() if now is None else now
    best = None
    for r in reports if isinstance(reports, list) else []:
        try:
            km = _km(lat, lon, float(r['lat']), float(r['lon']))
            t = float(r['obsTime'])
        except (KeyError, TypeError, ValueError):
            continue
        if km > MAX_KM or now - t > MAX_AGE:
            continue
        obs = parse(r.get('rawOb'))
        if obs is None:
            continue
        key = (round(km, 1), -t)        # nearest station, then its latest report
        if best is None or key < best[0]:
            best = (key, dict(obs, station=str(r.get('icaoId', ''))[:8], km=km, time=t))
    return best[1] if best else None


def fetch_metar(lat, lon):
    """
    Reports around (lat, lon): a list (possibly empty: no airport nearby), or None if the
    request failed. Coordinates go out rounded, like every other lookup.
    """
    la, lo = float(coord(lat)), float(coord(lon))
    url = _URL.format(coord(la - _BOX), coord(lo - _BOX / max(math.cos(math.radians(la)), 0.2)),
                      coord(la + _BOX), coord(lo + _BOX / max(math.cos(math.radians(la)), 0.2)))
    try:
        data = get_json(url, timeout=10)
    except ValueError:
        return []               # empty body: no station in the box
    except Exception:
        return None
    return data if isinstance(data, list) else []
