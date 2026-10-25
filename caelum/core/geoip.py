"""Rough location from the IP address (Settings → Detect), over HTTPS, with a fallback service."""

from .net import get_json

_MAX_OFFSET = 14 * 3600   # UTC+14 (Kiribati) is the furthest a timezone goes


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid(lat, lon, tz, offset):
    """The reply as {lat, lon, timezone, offset (s)}, or None if any field is missing or out of range."""
    if not (_number(lat) and _number(lon) and _number(offset)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -_MAX_OFFSET <= offset <= _MAX_OFFSET):
        return None
    tz = tz if isinstance(tz, str) else ''
    return {'lat': float(lat), 'lon': float(lon), 'timezone': tz[:64], 'offset': int(offset)}


def parse_ipwhois(d):
    """https://ipwho.is reply."""
    if not isinstance(d, dict) or d.get('success') is not True:
        return None
    tz = d.get('timezone') if isinstance(d.get('timezone'), dict) else {}
    return _valid(d.get('latitude'), d.get('longitude'), tz.get('id'), tz.get('offset'))


def parse_ipapi(d):
    """https://ipapi.co reply; its UTC offset is a '+hhmm' string."""
    if not isinstance(d, dict) or d.get('error'):
        return None
    off = d.get('utc_offset')
    if not (isinstance(off, str) and len(off) == 5 and off[0] in '+-' and off[1:].isdigit()):
        return None
    seconds = (int(off[1:3]) * 3600 + int(off[3:5]) * 60) * (1 if off[0] == '+' else -1)
    return _valid(d.get('latitude'), d.get('longitude'), d.get('timezone'), seconds)


_SERVICES = (
    ('https://ipwho.is/?fields=success,latitude,longitude,timezone', parse_ipwhois),
    ('https://ipapi.co/json/', parse_ipapi),
)


def detect_location():
    """{lat, lon, timezone, offset} from the first service that answers sensibly, else None."""
    for url, parse in _SERVICES:
        try:
            loc = parse(get_json(url, timeout=10))
        except Exception:
            continue
        if loc:
            return loc
    return None
