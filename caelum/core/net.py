"""HTTPS JSON requests shared by the weather, place-name and location lookups."""

import json
import urllib.request

from .. import __version__

USER_AGENT = f'caelum/{__version__} https://github.com/Juliowilly/caelum'
_MAX_BYTES = 4 * 1024 * 1024   # the largest reply (MET Norway's 10-day forecast) is ~150 kB


def coord(v):
    """
    A latitude/longitude as sent to online services: 2 decimals, about 1 km. Enough for the
    weather and the town name, without pointing at the user's house (4 decimals is ~11 m).
    """
    return f'{round(v, 2) + 0.0:.2f}'   # + 0.0 turns -0.0 into 0.0


def get_bytes(url, timeout=10, headers=None):
    """GET url (HTTPS only) and return the body. Raises on any failure."""
    if not url.startswith('https://'):
        raise ValueError(f'refusing a plain-HTTP request: {url}')
    req = urllib.request.Request(url, headers=dict(headers or {}, **{'User-Agent': USER_AGENT}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(_MAX_BYTES + 1)
    if len(body) > _MAX_BYTES:
        raise ValueError('reply too large')
    return body


def get_json(url, timeout=10, headers=None):
    """GET url (HTTPS only) and parse the JSON reply. Raises on any failure."""
    return json.loads(get_bytes(url, timeout, headers))
