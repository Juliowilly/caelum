"""
Is it raining (or snowing) where the user is, right now? Asks the free sources from the most
to the least accurate and keeps the first that covers the place:
  1. MET Norway Nowcast — radar + stations, every 5 min (Nordic countries);
  2. RainViewer — national weather radars, worldwide where they exist;
  3. the nearest airport's METAR — observed by people/sensors at the runway, within 30 km.
None means no observation covers the place: then the forecast models decide (merge_weather).
"""

from . import metar, radar


def _airport(lat, lon):
    obs = metar.nearest(metar.fetch_metar(lat, lon) or [], lat, lon)
    if obs is None:
        return None
    return dict(obs, source='airport')     # with station and km


SOURCES = (radar.met_nowcast, radar.rainviewer, _airport)


def observe(lat, lon):
    """
    {precip (mm/h), snow, thunder (None if unknown), source ('met_radar', 'rainviewer' or
    'airport', with station and km)} from the best source, or None.
    """
    for source in SOURCES:
        obs = source(lat, lon)
        if obs is not None:
            return obs
    return None
