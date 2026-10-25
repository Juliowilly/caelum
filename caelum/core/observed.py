"""
The weather as observed now where the user is, from the most accurate free source that covers
the place, for each kind of data:
  rain    — MET Norway Nowcast (radar + stations, Nordic countries), else RainViewer (national
            radars, worldwide where they exist), else the nearest airport's METAR;
  sky     — the nearest airport's cloud layers (within 30 km);
  air     — temperature, humidity, wind: Nowcast, else the nearest airport.
A part is None when no observation covers it: then the forecast models decide (merge_weather).
"""

from . import metar, radar

# The sources, from the most accurate; tests replace them
nowcast, rainviewer = radar.met_nowcast, radar.rainviewer


def airport(lat, lon):
    """The nearest airport's latest report (metar.nearest), or None."""
    return metar.nearest(metar.fetch_metar(lat, lon) or [], lat, lon)


def observe(lat, lon):
    """
    {'rain': {precip, snow, thunder (None if unknown), source},
     'sky':  {layers, sensed_top, source},
     'air':  {temp, humidity, wind_speed, wind_dir, source},
     'station': (icao, km) of the airport used, if any} — each part None if not observed.
    Sources: 'met_radar', 'rainviewer', 'airport'.
    """
    out = {'rain': None, 'sky': None, 'air': None, 'station': None}
    nordic = nowcast(lat, lon)
    if nordic is not None:
        out['rain'] = {k: nordic[k] for k in ('precip', 'snow', 'thunder', 'source')}
        out['air'] = dict(nordic['air'], source='met_radar')
    if out['rain'] is None:
        out['rain'] = rainviewer(lat, lon)
    field = airport(lat, lon)
    if field is not None:
        out['station'] = (field['station'], field['km'])
        if out['rain'] is None:
            out['rain'] = {'precip': field['precip'], 'snow': field['snow'],
                           'thunder': field['thunder'], 'source': 'airport'}
        elif out['rain']['thunder'] is None:
            out['rain'] = dict(out['rain'], thunder=field['thunder'])   # radar can't see lightning
        out['sky'] = {'layers': field['layers'], 'sensed_top': field['sensed_top'], 'source': 'airport'}
        if out['air'] is None and field['temp'] is not None:
            out['air'] = {'temp': field['temp'], 'humidity': field['humidity'],
                          'wind_speed': field['wind_speed'], 'wind_dir': field['wind_dir'],
                          'source': 'airport'}
    return out
