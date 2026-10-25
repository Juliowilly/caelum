import unittest

from caelum.core.metar import nearest, parse
from caelum.core.weather import merge_weather

OM_DRY = {'total': 95, 'low': 60, 'mid': 40, 'high': 10, 'precip': 0.0, 'snow': False, 'wmo': 3,
          'ts': '2026-10-25T13:15'}
MET_RAIN = {'total': 90, 'precip': 1.0, 'snow': False, 'wmo': 65, 'ts': '2026-10-25T13:00:00Z',
            'temp': 29.0, 'humidity': 80, 'wind_speed': 4.0, 'wind_dir': 220.0, 'symbol': 'heavyrain',
            'forecast': [], 'hourly_forecast': [], 'daily_forecast': [{'date': '2026-10-25'}]}
DRY_OBS  = {'precip': 0.0, 'snow': False, 'thunder': False, 'station': 'DXXX', 'km': 5.0, 'time': 0.0}
RAIN_OBS = dict(DRY_OBS, precip=2.5)

# Lomé airport, 25 Oct 2026: a normal report and a garbled one (two METARs run together, Q110)
LOME_1230 = 'METAR DXXX 251230Z 19010KT 160V230 9999 FEW017 32/25 Q1011 NOSIG'
LOME_1300 = 'METAR DXXX 251300Z 19011KT 150V210 9999 FEW017 32/26 Q110 DRRRYMYX SAAO20 DRRN 251300 METAR '


class MergeWeatherTest(unittest.TestCase):
    def test_airport_dry_beats_forecast_rain(self):
        # 25 Oct 2026, Lomé: MET's forecast said heavy rain, the airport saw none
        w = merge_weather(OM_DRY, MET_RAIN, DRY_OBS)
        self.assertEqual(w['precip'], 0.0)
        self.assertEqual(w['wmo'], 3)

    def test_airport_rain_shows_when_models_are_dry(self):
        w = merge_weather(OM_DRY, dict(MET_RAIN, precip=0.0, wmo=3), RAIN_OBS)
        self.assertEqual(w['precip'], 2.5)
        self.assertEqual(w['wmo'], 63)

    def test_airport_thunder(self):
        w = merge_weather(OM_DRY, MET_RAIN, dict(RAIN_OBS, thunder=True, precip=8.0))
        self.assertEqual(w['wmo'], 99)

    def test_without_airport_met_forecast_decides(self):
        w = merge_weather(dict(OM_DRY, precip=3.0, wmo=63), dict(MET_RAIN, precip=0.0, wmo=3))
        self.assertEqual(w['precip'], 0.0)
        w = merge_weather(OM_DRY, MET_RAIN)
        self.assertEqual((w['precip'], w['wmo']), (1.0, 65))

    def test_open_meteo_alone(self):
        w = merge_weather(dict(OM_DRY, precip=3.0, wmo=63), None)
        self.assertEqual(w['precip'], 3.0)

    def test_met_still_gives_temperature_wind_and_forecast(self):
        w = merge_weather(OM_DRY, MET_RAIN, DRY_OBS)
        self.assertEqual((w['temp'], w['wind_speed'], w['wind_dir']), (29.0, 4.0, 220.0))
        self.assertEqual(w['daily_forecast'], MET_RAIN['daily_forecast'])


class MetarParseTest(unittest.TestCase):
    def test_dry_report(self):
        self.assertEqual(parse(LOME_1230), {'precip': 0.0, 'snow': False, 'thunder': False})

    def test_garbled_report_is_rejected(self):
        self.assertIsNone(parse(LOME_1300))
        self.assertIsNone(parse('not a metar'))
        self.assertIsNone(parse(None))

    def test_rain_intensities(self):
        base = 'METAR DXXX 251300Z 19011KT 9999 {} BKN017 26/24 Q1011'
        self.assertEqual(parse(base.format('-RA'))['precip'], 0.5)
        self.assertEqual(parse(base.format('RA'))['precip'], 2.5)
        self.assertEqual(parse(base.format('+SHRA'))['precip'], 8.0)
        self.assertEqual(parse(base.format('DZ'))['precip'], 0.3)

    def test_thunder_and_snow(self):
        base = 'METAR ENGM 251300Z 19011KT 9999 {} BKN017 01/00 Q1011'
        self.assertTrue(parse(base.format('TSRA'))['thunder'])
        self.assertTrue(parse(base.format('VCTS TS'))['thunder'])
        self.assertTrue(parse(base.format('-SN'))['snow'])

    def test_vicinity_trend_recent_and_remarks_are_not_now(self):
        base = 'METAR DXXX 251300Z 19011KT 9999 {} 26/24 Q1011'
        for tail in ('VCSH', 'RERA', 'NOSIG TEMPO RA', 'RMK RAB05'):
            self.assertEqual(parse(base.format(tail))['precip'], 0.0, tail)


class MetarNearestTest(unittest.TestCase):
    NOW = 1792933200.0     # 2026-10-25 13:00 UTC

    def rep(self, lat, lon, age_min, raw=LOME_1230, icao='DXXX'):
        return {'icaoId': icao, 'lat': lat, 'lon': lon, 'obsTime': self.NOW - age_min * 60, 'rawOb': raw}

    def test_latest_good_report_of_the_airport(self):
        reports = [self.rep(6.166, 1.254, 0, LOME_1300), self.rep(6.166, 1.254, 30),
                   self.rep(6.166, 1.254, 60, LOME_1230.replace('NOSIG', 'RA'))]
        obs = nearest(reports, 6.1375, 1.2123, now=self.NOW)
        self.assertEqual((obs['station'], obs['precip']), ('DXXX', 0.0))   # 12:30 report, not the garbled 13:00
        self.assertLess(obs['km'], 6)

    def test_too_far_or_too_old(self):
        self.assertIsNone(nearest([self.rep(6.9, 1.25, 0)], 6.1375, 1.2123, now=self.NOW))
        self.assertIsNone(nearest([self.rep(6.166, 1.254, 120)], 6.1375, 1.2123, now=self.NOW))
        self.assertIsNone(nearest([], 6.1375, 1.2123, now=self.NOW))
        self.assertIsNone(nearest(None, 6.1375, 1.2123, now=self.NOW))

    def test_nearer_airport_wins(self):
        far = self.rep(6.35, 1.25, 0, LOME_1230.replace('NOSIG', 'RA'), 'FAR1')
        near = self.rep(6.15, 1.22, 20, icao='NEAR')
        self.assertEqual(nearest([far, near], 6.1375, 1.2123, now=self.NOW)['station'], 'NEAR')


if __name__ == '__main__':
    unittest.main()
