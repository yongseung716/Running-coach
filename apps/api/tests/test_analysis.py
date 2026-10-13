import math
import unittest
from pathlib import Path

from coach.analysis import GPXError, analyze


def gpx(points, more_segments=None):
    def segment(nodes):
        return '<trkseg>' + ''.join(f'<trkpt lat="{lat}" lon="{lon}">{extras}</trkpt>' for lat, lon, extras in nodes) + '</trkseg>'
    return ('<gpx><trk>' + segment(points) + ''.join(segment(s) for s in (more_segments or [])) + '</trk></gpx>').encode()


def stamp(second, hr=None, ele=None):
    return f'<time>2026-01-01T06:{second//60:02d}:{second%60:02d}Z</time>' + (f'<extensions><hr>{hr}</hr></extensions>' if hr else '') + (f'<ele>{ele}</ele>' if ele is not None else '')


class AnalysisTests(unittest.TestCase):
    def test_known_distance_pace_split_and_reproducibility(self):
        data = (Path(__file__).resolve().parents[3] / 'samples/steady-2km.gpx').read_bytes()
        result = analyze(data)
        self.assertEqual(result, analyze(data))
        self.assertAlmostEqual(result['distance_km'], 6371008.8 * math.radians(.02) / 1000, delta=.001)
        self.assertAlmostEqual(result['pace_sec_km'], 359.73, delta=.1)
        self.assertEqual(result['elapsed_seconds'], 800)
        self.assertEqual(result['avg_heart_rate'], 140)
        self.assertEqual(result['heart_rate_coverage'], 1)
        self.assertEqual(len(result['splits']), 3)
        self.assertTrue(result['splits'][-1]['partial'])
        self.assertAlmostEqual(sum(s['distance_km'] for s in result['splits']), result['distance_km'], delta=.001)
        self.assertEqual(result['ascent_m'], 18)
        self.assertNotIn('lat', str(result))

    def test_no_time_does_not_invent_pace(self):
        result = analyze(gpx([(0, 0, ''), (0, .001, '')]))
        self.assertGreater(result['distance_km'], 0)
        self.assertIsNone(result['pace_sec_km'])
        self.assertIsNone(result['moving_seconds'])
        self.assertIsNone(result['ascent_m'])
        self.assertFalse(result['timing_complete'])

    def test_no_connection_between_segments(self):
        result = analyze(gpx([(0, 0, stamp(0)), (0, .001, stamp(60))], [[(20, 20, stamp(120)), (20, 20.001, stamp(180))]]))
        self.assertLess(result['distance_km'], .23)
        self.assertEqual(len(result['splits']), 1)

    def test_gps_spike_excluded(self):
        result = analyze(gpx([(0, 0, stamp(0)), (0, .001, stamp(40)), (30, 30, stamp(41)), (0, .002, stamp(42))]))
        self.assertAlmostEqual(result['distance_km'], .111, delta=.001)
        self.assertTrue(any('급변' in w for w in result['warnings']))

    def test_reversed_and_duplicate_time(self):
        for end in (0, 20):
            result = analyze(gpx([(0, 0, stamp(20)), (0, .001, stamp(end))]))
            self.assertIsNone(result['pace_sec_km'])

    def test_weighted_heart_rate_and_missing_coverage(self):
        result = analyze(gpx([(0, 0, stamp(0, 100)), (0, .001, stamp(30, 200)), (0, .002, stamp(120, None))]))
        self.assertEqual(result['avg_heart_rate'], 150)
        self.assertEqual(result['heart_rate_coverage'], .25)

    def test_invalid_hr_excluded_and_warning(self):
        result = analyze(gpx([(0, 0, stamp(0, 999)), (0, .001, stamp(60, 140))]))
        self.assertIsNone(result['avg_heart_rate'])
        self.assertTrue(any('심박' in w for w in result['warnings']))

    def test_stationary_no_infinity(self):
        result = analyze(gpx([(0, 0, stamp(0)), (0, 0, stamp(60))]))
        self.assertEqual(result['distance_km'], 0)
        self.assertIsNone(result['pace_sec_km'])

    def test_reject_malformed_invalid_coordinates_and_xml_entities(self):
        for data in (b'<html/>', b'not XML', gpx([(999, 0, ''), (0, 0, '')]),
                     gpx([(0, 'NaN', ''), (0, 0, '')]),
                     b'<!DOCTYPE gpx [<!ENTITY secret SYSTEM "file:///etc/passwd">]><gpx>&secret;</gpx>'):
            with self.subTest(data=data[:30]):
                with self.assertRaises(GPXError):
                    analyze(data)

    def test_timezone_required(self):
        result = analyze(gpx([(0, 0, '<time>2026-01-01T00:00:00</time>'), (0, .001, stamp(60))]))
        self.assertIsNone(result['pace_sec_km'])

    def test_oversize_and_single_point_rejected(self):
        for data in (b'x' * (10*1024*1024+1), gpx([(0, 0, stamp(0))])):
            with self.assertRaises(GPXError):
                analyze(data)

    def test_elevation_gap_not_bridged(self):
        result = analyze(gpx([(0, 0, stamp(0, ele=0)), (0, .001, stamp(60)), (0, .002, stamp(120, ele=100))]))
        self.assertEqual(result['ascent_m'], 0)

    def test_empty_time_is_missing_instead_of_crashing(self):
        result = analyze(gpx([(0, 0, '<time/>'), (0, .001, stamp(60))]))
        self.assertFalse(result['timing_complete'])
        self.assertIsNone(result['pace_sec_km'])

    def test_gpx_comments_processing_instructions_and_time_whitespace(self):
        data = gpx([(0, 0, '<time> 2026-01-01T06:00:00Z </time><!-- device comment -->'),
                    (0, .001, stamp(60))])
        result = analyze(data.replace(b'<trk>', b'<trk><?device recorded?>'))
        self.assertTrue(result['timing_complete'])
        self.assertAlmostEqual(result['distance_km'], .111, delta=.001)

    def test_out_of_range_elevation_is_missing(self):
        result = analyze(gpx([(0, 0, stamp(0, ele=0)), (0, .001, stamp(60, ele=1e99))]))
        self.assertEqual(result['ascent_m'], 0)
        self.assertTrue(any('범위 밖 고도' in w for w in result['warnings']))


if __name__ == '__main__':
    unittest.main()
