"""Weather fetching (Open-Meteo, MET Norway) and merging."""

from .net import coord, get_json

_NO_CLOUDS = {
    'total': 0, 'low': 0, 'mid': 0, 'high': 0,
    'precip': 0.0, 'snow': False, 'wmo': 0, 'ts': '',
    'temp': None, 'humidity': None,
    'wind_speed': 0.0, 'wind_dir': 0.0,
    'symbol': '', 'forecast': [], 'daily_forecast': [], 'hourly_forecast': [],
}

# ─── Weather condition label / accent colour (shared by forecast & weekly) ────
_WX_LABEL = {
    'clearsky': 'Clear', 'fair': 'Fair',
    'partlycloudy': 'Part. Cloudy', 'cloudy': 'Cloudy', 'fog': 'Fog',
    'lightrain': 'Light Rain', 'rain': 'Rain', 'heavyrain': 'Heavy Rain',
    'lightsleet': 'Sleet', 'sleet': 'Sleet',
    'lightsnow': 'Light Snow', 'snow': 'Snow', 'heavysnow': 'Heavy Snow',
    'lightrainshowers': 'Showers', 'rainshowers': 'Showers',
    'heavyrainshowers': 'Hvy Showers', 'lightsnowshowers': 'Snow Shwrs',
    'snowshowers': 'Snow Shwrs', 'thunderstorm': 'Thunder',
    'rainandthunder': 'Storm', 'heavyrainandthunder': 'Heavy Storm',
    'lightsleetshowers': 'Sleet Shwrs', 'sleetshowers': 'Sleet Shwrs',
}
_WX_ACCENT = {
    'clearsky': (1.00, 0.92, 0.45), 'fair': (1.00, 0.88, 0.55),
    'partlycloudy': (0.78, 0.88, 1.00), 'cloudy': (0.68, 0.78, 0.95),
    'fog': (0.72, 0.80, 0.85),
    'lightrain': (0.50, 0.82, 1.00), 'rain': (0.38, 0.68, 1.00),
    'heavyrain': (0.28, 0.55, 1.00),
    'lightsleet': (0.70, 0.85, 1.00), 'sleet': (0.65, 0.80, 1.00),
    'lightsnow': (0.82, 0.92, 1.00), 'snow': (0.78, 0.90, 1.00),
    'heavysnow': (0.72, 0.86, 1.00),
    'lightrainshowers': (0.55, 0.80, 1.00), 'rainshowers': (0.45, 0.72, 1.00),
    'heavyrainshowers': (0.35, 0.62, 1.00),
    'thunderstorm': (0.90, 0.62, 1.00), 'rainandthunder': (0.85, 0.50, 1.00),
    'heavyrainandthunder': (0.80, 0.40, 1.00),
}

# ─── Weather ─────────────────────────────────────────────────────────────────

_WMO_PRECIP = {
    51: 0.2, 53: 0.5, 55: 1.2,
    56: 0.3, 57: 0.8,
    61: 0.4, 63: 1.5, 65: 4.0,
    66: 0.4, 67: 1.5,
    71: 0.3, 73: 0.8, 75: 2.0,
    80: 0.5, 81: 2.0, 82: 5.0,
    85: 0.3, 86: 1.0,
    95: 3.0, 96: 4.0, 99: 5.0,
}

def fetch_open_meteo(lat, lon):
    """Fetch cloud layers and precipitation from Open-Meteo (no key needed)."""
    url = (f"https://api.open-meteo.com/v1/forecast"
           f"?latitude={coord(lat)}&longitude={coord(lon)}"
           f"&current=cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high"
           f",precipitation,snowfall,weather_code")
    try:
        data       = get_json(url, timeout=8)
        c          = data['current']
        code       = int(c.get('weather_code', 0))
        raw_precip = float(c.get('precipitation', 0.0))
        precip     = raw_precip if raw_precip > 0 else _WMO_PRECIP.get(code, 0.0)
        snow       = float(c.get('snowfall', 0.0)) > 0.0 or code in (71, 73, 75, 77, 85, 86)
        total      = int(c.get('cloud_cover',     0))
        low        = int(c.get('cloud_cover_low',  0))
        mid        = int(c.get('cloud_cover_mid',  0))
        high       = int(c.get('cloud_cover_high', 0))
        if precip > 0 and total == 0:
            total = 60; low = 60
        return {
            'total': total, 'low': low, 'mid': mid, 'high': high,
            'precip': precip, 'snow': snow, 'wmo': code,
            'ts': c.get('time', ''),
        }
    except Exception:
        return None

# MET Norway symbol → approximate WMO code (for downstream logic)
_MET_SYMBOL_WMO = {
    'clearsky': 0, 'fair': 1, 'partlycloudy': 2, 'cloudy': 3,
    'fog': 45, 'lightrain': 61, 'rain': 63, 'heavyrain': 65,
    'lightsleet': 66, 'sleet': 67,
    'lightsnow': 71, 'snow': 73, 'heavysnow': 75,
    'lightrainshowers': 80, 'rainshowers': 81, 'heavyrainshowers': 82,
    'lightsnowshowers': 85, 'snowshowers': 86,
    'thunderstorm': 95, 'rainandthunder': 95, 'heavyrainandthunder': 99,
}

def fetch_met_norway(lat, lon):
    """Fetch from MET Norway LocationForecast 2.0 (no API key — User-Agent required)."""
    url = (f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
           f"?lat={coord(lat)}&lon={coord(lon)}")
    try:
        data    = get_json(url, timeout=10)
        series  = data['properties']['timeseries']
        entry   = series[0]
        ts      = entry['time']
        instant = entry['data']['instant']['details']
        next1   = entry['data'].get('next_1_hours') or entry['data'].get('next_6_hours', {})
        symbol  = next1.get('summary', {}).get('symbol_code', '')
        symbol_base = symbol.split('_')[0] if symbol else ''
        precip  = float(next1.get('details', {}).get('precipitation_amount', 0.0))
        snow    = any(s in symbol_base for s in ('snow', 'sleet'))
        wmo     = _MET_SYMBOL_WMO.get(symbol_base, 0)

        # Hourly forecast: full timeseries (up to 4 days) + next-8 shortcut
        def _parse_hourly(fe):
            fi   = fe['data']['instant']['details']
            fn1  = fe['data'].get('next_1_hours') or fe['data'].get('next_6_hours', {})
            fsym = fn1.get('summary', {}).get('symbol_code', '')
            return {
                'ts':     fe['time'],
                'temp':   float(fi.get('air_temperature', 0.0)),
                'wind':   float(fi.get('wind_speed', 0.0)),
                'precip': float(fn1.get('details', {}).get('precipitation_amount', 0.0)),
                'symbol': (fsym.split('_')[0] if fsym else ''),
                'cloud':  int(fi.get('cloud_area_fraction', 0)),
            }
        forecast         = [_parse_hourly(fe) for fe in series[1:9]]
        hourly_forecast  = [_parse_hourly(fe) for fe in series[1:97]]

        # Daily forecast: group by UTC date, pick noon entry for symbol
        day_map = {}
        for fe in series:
            d = fe['time'][:10]
            day_map.setdefault(d, []).append(fe)
        daily_forecast = []
        for date_str in sorted(day_map.keys())[:8]:
            day_ents = day_map[date_str]
            noon = min(day_ents,
                       key=lambda e: abs(int(e['time'][11:13]) - 12))
            n12  = noon['data'].get('next_12_hours', {})
            n1   = noon['data'].get('next_1_hours', {})
            sym  = (n12.get('summary', {}).get('symbol_code') or
                    n1.get('summary', {}).get('symbol_code', ''))
            sym_b = sym.split('_')[0] if sym else ''
            temps  = [float(e['data']['instant']['details'].get('air_temperature', 0))
                      for e in day_ents]
            precip_sum = sum(
                float(e['data'].get('next_1_hours', {}).get('details', {})
                      .get('precipitation_amount', 0))
                for e in day_ents)
            daily_forecast.append({
                'date':     date_str,
                'temp_max': round(max(temps), 1) if temps else 0.0,
                'temp_min': round(min(temps), 1) if temps else 0.0,
                'symbol':   sym_b,
                'precip':   round(precip_sum, 1),
            })

        return {
            'total':      int(instant.get('cloud_area_fraction', 0)),
            'temp':       float(instant.get('air_temperature', 0.0)),
            'humidity':   float(instant.get('relative_humidity', 0.0)),
            'wind_speed': float(instant.get('wind_speed', 0.0)),
            'wind_dir':   float(instant.get('wind_from_direction', 0.0)),
            'precip':     precip,
            'snow':       snow,
            'wmo':        wmo,
            'symbol':         symbol_base,
            'ts':             ts,
            'forecast':        forecast,
            'hourly_forecast': hourly_forecast,
            'daily_forecast':  daily_forecast,
        }
    except Exception:
        return None

def merge_weather(om, met, obs=None):
    """
    Merge Open-Meteo + MET Norway, taking the best of each source. `obs` is the best available
    observation of precipitation now (rain_now.observe: radar or an airport); when there is
    one, it decides whether it is raining, otherwise the forecasts do.
    """
    if om is None and met is None:
        return None
    result = dict(_NO_CLOUDS)
    if om is not None:
        result.update({
            'total': om['total'], 'low': om['low'],
            'mid':   om['mid'],   'high': om['high'],
            'precip': om['precip'], 'snow': om['snow'],
            'wmo': om['wmo'], 'ts': om.get('ts', ''),
        })
    if met is not None:
        # MET Norway: temperature, humidity, wind always preferred
        result['temp']       = met['temp']
        result['humidity']   = met['humidity']
        result['wind_speed'] = met['wind_speed']
        result['wind_dir']   = met['wind_dir']
        result['symbol']     = met['symbol']
        # Cloud total: average both sources for best estimate
        met_total = met['total']
        if om is not None:
            result['total'] = (om['total'] + met_total) // 2
        else:
            result['total'] = met_total
            result['low']   = 0; result['mid'] = met_total; result['high'] = 0
        # Without an observation, rain comes from MET Norway's forecast for the coming hour
        result['precip'] = met['precip']
        result['snow']   = met['snow']
        if met['wmo'] > 0:
            result['wmo'] = met['wmo']
        # Forecast and daily forecast come only from MET Norway
        result['forecast']        = met.get('forecast', [])
        result['hourly_forecast'] = met.get('hourly_forecast', [])
        result['daily_forecast']  = met.get('daily_forecast', [])
        # Combined timestamp for smart-skip: update when either source changes
        result['ts'] = (om.get('ts', '') if om else '') + '|' + met.get('ts', '')
    # Where "is it raining now" came from: met_radar | rainviewer | airport | met_forecast | om_forecast
    result['rain_source'] = 'met_forecast' if met is not None else 'om_forecast'
    result['rain_station'] = None
    if obs is not None:
        # Observed beats forecast: the models often miss (or invent) a shower
        result['precip'] = obs['precip']
        result['snow']   = obs['snow']
        result['wmo']    = _observed_wmo(obs, result['wmo'])
        result['rain_source'] = obs['source']
        if obs['source'] == 'airport':
            result['rain_station'] = (obs['station'], obs['km'])
        result['ts']    += f"|{obs['source']}:{obs['precip']}"
    if result['precip'] > 0 and result['total'] == 0:
        result['total'] = 60; result['low'] = 60
    return result


def _observed_wmo(obs, model_wmo):
    """
    WMO code for what is observed; dry, the model's code minus any rain or snow. Radar can't
    see lightning (thunder None): then a rain shower keeps the model's thunderstorm code.
    """
    p = obs['precip']
    if obs['thunder'] or (obs['thunder'] is None and p > 0 and model_wmo >= 95):
        return 99 if p >= 8 else (model_wmo if model_wmo >= 95 else 95)
    if p <= 0:
        return model_wmo if model_wmo < 51 else 3
    if obs['snow']:
        return 71 if p < 1 else (73 if p < 5 else 75)
    if p < 0.5:
        return 51 if p < 0.2 else 53
    return 61 if p < 1 else (63 if p < 5 else 65)
