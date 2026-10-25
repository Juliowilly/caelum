import unittest

from caelum.core.weather import merge_weather

OM_DRY = {'total': 95, 'low': 60, 'mid': 40, 'high': 10, 'precip': 0.0, 'snow': False, 'wmo': 3,
          'ts': '2026-10-25T13:15'}
MET_RAIN = {'total': 90, 'precip': 1.0, 'snow': False, 'wmo': 65, 'ts': '2026-10-25T13:00:00Z',
            'temp': 29.0, 'humidity': 80, 'wind_speed': 4.0, 'wind_dir': 220.0, 'symbol': 'heavyrain',
            'forecast': [], 'hourly_forecast': [], 'daily_forecast': [{'date': '2026-10-25'}]}


class MergeWeatherTest(unittest.TestCase):
    def test_current_rain_follows_open_meteo(self):
        # 25 Oct 2026, Lomé: MET's 2-hour-old forecast said heavy rain, Open-Meteo's now said dry
        w = merge_weather(OM_DRY, MET_RAIN)
        self.assertEqual(w['precip'], 0.0)
        self.assertEqual(w['wmo'], 3)

    def test_open_meteo_rain_shows(self):
        w = merge_weather(dict(OM_DRY, precip=2.5, wmo=63), dict(MET_RAIN, precip=0.0, wmo=3))
        self.assertEqual(w['precip'], 2.5)
        self.assertEqual(w['wmo'], 63)

    def test_met_fills_in_without_open_meteo(self):
        w = merge_weather(None, MET_RAIN)
        self.assertEqual(w['precip'], 1.0)
        self.assertEqual(w['wmo'], 65)

    def test_met_still_gives_temperature_wind_and_forecast(self):
        w = merge_weather(OM_DRY, MET_RAIN)
        self.assertEqual((w['temp'], w['wind_speed'], w['wind_dir']), (29.0, 4.0, 220.0))
        self.assertEqual(w['daily_forecast'], MET_RAIN['daily_forecast'])


if __name__ == '__main__':
    unittest.main()
