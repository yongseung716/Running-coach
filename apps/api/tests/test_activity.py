import io
import unittest
import zipfile

from coach.activity import analyze_activity, prepare_upload, private_route
from coach.analysis import GPXError
from fit_fixture import make_fit


class ActivityTests(unittest.TestCase):
    def test_fit_dynamics_units_and_device_provenance(self):
        result = analyze_activity(make_fit(), 'fit')
        self.assertEqual(result['distance_km'], 1.5)
        self.assertEqual(result['pace_sec_km'], 400)
        self.assertEqual(result['metrics']['cadence_spm']['avg'], 166)
        self.assertEqual(result['metrics']['stride_length_m']['avg'], .96)
        self.assertEqual(result['metrics']['vertical_oscillation_cm']['avg'], 8.4)
        self.assertEqual(result['metrics']['ground_contact_ms']['avg'], 259)
        self.assertEqual(result['metrics']['power_w']['avg'], 276)
        self.assertEqual(result['device_summary']['aerobic_training_effect'], 3)
        self.assertEqual(result['device_summary']['elapsed_seconds'], 610)
        self.assertEqual(result['elapsed_seconds'], 600)
        self.assertEqual(result['laps'][0]['distance_km'], 1.5)
        self.assertNotIn('lat', result['series'][0])
        self.assertEqual(sum(result['heart_rate_seconds'].values()), 600)

    def test_indoor_fit_without_gps_uses_recorded_distance(self):
        result = analyze_activity(make_fit(indoor=True), 'fit')
        self.assertEqual(result['distance_km'], 1.5)
        self.assertEqual(result['pace_sec_km'], 400)
        self.assertFalse(any(private_route(make_fit(indoor=True), 'fit')['segments']))

    def test_invalid_crc_signature_and_wrong_sport(self):
        data = bytearray(make_fit()); data[-1] ^= 1
        for invalid in (bytes(data), b'not a FIT'):
            with self.assertRaises(GPXError):
                analyze_activity(invalid, 'fit')
        with self.assertRaises(GPXError):
            analyze_activity(make_fit(sport=2), 'fit')

    def test_zip_unwrap_preserves_exact_original_fit(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('garmin/activity.fit', make_fit())
        data, fmt = prepare_upload(stream.getvalue(), 'original.zip')
        self.assertEqual(data, make_fit())
        self.assertEqual(fmt, 'fit')

    def test_zip_rejects_multiple_and_non_fit_files(self):
        for contents in [['a.gpx'], ['a.fit', 'b.fit']]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                for name in contents:
                    z.writestr(name, make_fit())
            with self.assertRaises(GPXError):
                prepare_upload(stream.getvalue(), 'activity.zip')

    def test_missing_gpx_extensions_are_not_fabricated(self):
        from pathlib import Path
        data = (Path(__file__).resolve().parents[3] / 'samples/steady-2km.gpx').read_bytes()
        result = analyze_activity(data)
        self.assertIsNone(result['metrics']['power_w']['avg'])
        self.assertEqual(result['device_summary'], {})
        self.assertNotIn('calories_kcal', result)

    def test_route_is_separate_and_has_bounded_points(self):
        route = private_route(make_fit(), 'fit')
        self.assertAlmostEqual(route['segments'][0][-1]['lon'], .01349, places=4)
        self.assertEqual(route['privacy'], 'owner_only_no_external_map_tiles')
