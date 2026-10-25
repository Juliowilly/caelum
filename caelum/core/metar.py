"""
Observed weather from the nearest airport: METAR reports (every 30–60 min, from the weather
station on the runway) through the US Aviation Weather Center's free API. Unlike the forecast
models, they say whether it is actually raining now.
"""

import math
import re
import time

from .net import coord, get_json

MAX_KM  = 30.0          # an airport farther than this says little about the rain where the user is
MAX_AGE = 90 * 60       # older reports are stale (stations report every 30 or 60 min)
_URL = 'https://aviationweather.gov/api/data/metar?bbox={},{},{},{}&format=json&hours=3'
_BOX = 0.30             # degrees of latitude around the user to search (~33 km)

# Present-weather group: intensity, descriptor, precipitation — e.g. -RA, +TSRA, SHRA, DZ, -SN
_WX = re.compile(r'^(?P<int>[-+])?(?P<desc>SH|TS|FZ)?(?P<precip>(?:DZ|RA|SN|SG|PL|GR|GS|UP)+)$')
_HEAD = re.compile(r'^(?:METAR|SPECI)(?: COR)? [A-Z0-9]{4} \d{6}Z ')
# Rough rates (mm/h) for the intensities a METAR gives
_RATE = {'DZ': (0.1, 0.3, 0.6), 'other': (0.5, 2.5, 8.0)}


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def parse(raw):
    """
    What a METAR says is falling now: {precip (mm/h), snow, thunder}, or None if the report is
    malformed. Remarks (RMK …), the trend (NOSIG, BECMG, TEMPO) and recent weather (RERA) are
    not the present weather and are ignored.
    """
    if not isinstance(raw, str) or not _HEAD.match(raw) or raw.count('METAR') + raw.count('SPECI') > 1:
        return None
    obs = {'precip': 0.0, 'snow': False, 'thunder': False}
    for tok in raw.split()[3:]:
        if tok in ('RMK', 'NOSIG', 'BECMG', 'TEMPO'):
            break
        if tok == 'TS' or tok == '+TS' or tok == '-TS':
            obs['thunder'] = True
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
    return obs


def nearest(reports, lat, lon, now=None):
    """
    The latest usable report of the nearest airport within MAX_KM, as
    {station, km, time, precip, snow, thunder}; None if there is none.
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
