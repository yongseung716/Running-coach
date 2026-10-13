import io
import zipfile
import unittest
from datetime import datetime, timezone

import test_api
from test_api import process_one
from fit_fixture import make_fit


class AdvancedAPITests(unittest.TestCase):
    setUp = test_api.APITests.setUp
    tearDown = test_api.APITests.tearDown
    signup = test_api.APITests.signup
    other = test_api.APITests.other
    upload = test_api.APITests.upload

    def test_fit_upload_worker_private_download_export(self):
        self.signup()
        data = make_fit()
        response = self.client.post('/runs', files={'file': ('activity.fit', data, 'application/octet-stream')})
        self.assertEqual(response.status_code, 202, response.text)
        run = response.json()
        self.assertEqual(run['file_format'], 'fit')
        self.assertTrue(process_one())
        self.assertEqual(self.client.get(f"/runs/{run['id']}").json()['analysis']['metrics']['power_w']['avg'], 276)
        self.assertEqual(self.client.get(f"/runs/{run['id']}/file").content, data)
        with zipfile.ZipFile(io.BytesIO(self.client.get('/account/export').content)) as z:
            self.assertEqual(z.read(f"fit/{run['id']}.fit"), data)
        self.assertEqual(self.client.delete(f"/runs/{run['id']}").status_code, 200)

    def test_owner_only_feedback_notes_route_reanalysis(self):
        self.signup()
        run = self.upload()
        process_one()
        bob = self.other('Bob')
        for endpoint in ['feedback', 'route']:
            self.assertEqual(bob.get(f"/runs/{run['id']}/{endpoint}").status_code, 404)
        self.assertEqual(bob.patch(f"/runs/{run['id']}/notes", json={'rpe': 2}).status_code, 404)
        self.assertEqual(bob.post(f"/runs/{run['id']}/reanalyze").status_code, 404)
        result = self.client.patch(f"/runs/{run['id']}/notes", json={'training_type': 'easy', 'rpe': 8, 'note': 'Test fixture'})
        self.assertEqual(result.status_code, 200)
        report = self.client.get(f"/runs/{run['id']}/feedback").json()
        self.assertTrue(any('체감 강도' in v['text'] for v in report['opportunities']))
        self.assertEqual(self.client.post(f"/runs/{run['id']}/reanalyze").status_code, 202)
        self.assertEqual(self.client.post(f"/runs/{run['id']}/reanalyze").status_code, 409)
        process_one()
        self.assertEqual(self.client.get(f"/runs/{run['id']}").json()['workout_notes']['rpe'], 8)

    def test_profile_benchmarks_validation_and_catalog(self):
        self.signup()
        today = datetime.now(timezone.utc).date().isoformat()
        result = self.client.patch('/profile/athlete-settings', json={'hr_max': 190, 'benchmark_5k_min': 25, 'benchmark_5k_date': today})
        self.assertEqual(result.status_code, 200, result.text)
        library = self.client.get('/training/catalog').json()
        self.assertEqual(library['reference']['pace_sec_km'], 300)
        self.assertEqual(self.client.patch('/profile/athlete-settings', json={'hr_max': 160, 'lthr': 180}).status_code, 422)
        self.assertEqual(self.client.patch('/profile/athlete-settings', json={'benchmark_5k_min': 25}).status_code, 422)
        # Old clients saving name/goal must not erase calibration settings.
        self.client.patch('/profile', json={'display_name': 'Alice', 'runs_per_week': 3})
        self.assertEqual(self.client.get('/profile').json()['athlete_settings']['hr_max'], 190)

    def test_all_types_edit_persistence_and_completed_day_guard(self):
        self.signup()
        plan = self.client.post('/plans').json()
        path = f"/plans/{plan['id']}/days/0"
        for kind in ['interval', 'tempo', 'steady', 'lsd', 'easy', 'rest']:
            result = self.client.patch(path, json={'type': kind, 'mode': 'rpe', 'duration_min': 15})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['prescription']['days'][0]['type'], kind)
        self.client.patch(path, json={'type': 'easy', 'mode': 'rpe'})
        self.client.put(path + '/completion', json={})
        self.assertEqual(self.client.patch(path, json={'type': 'tempo'}).status_code, 409)
        self.client.delete(path + '/completion')
        self.assertEqual(self.client.patch(path, json={'type': 'interval', 'mode': 'rpe', 'repetitions': 6}).status_code, 200)
        self.assertEqual(self.client.post('/plans').json()['prescription']['days'][0]['type'], 'interval')

    def test_cross_user_plan_edit_and_injected_analysis_rejected(self):
        self.signup()
        plan = self.client.post('/plans').json()
        run = self.upload()
        bob = self.other('Bob')
        self.assertEqual(bob.patch(f"/plans/{plan['id']}/days/0", json={'type': 'interval'}).status_code, 404)
        self.assertEqual(self.client.patch(f"/runs/{run['id']}/notes", json={'analysis': {'distance_km': 50}}).status_code, 422)
        self.assertEqual(self.client.patch(f"/plans/{plan['id']}/days/0", json={'type': 'interval', 'repetitions': -1}).status_code, 422)
