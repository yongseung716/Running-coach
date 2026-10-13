import io
import json
import os
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ['MODE'] = 'test'
from fastapi.testclient import TestClient
from sqlalchemy import select

from coach import auth, db as database, storage
from coach.config import Settings, settings
from coach.db import Completion, Run, session
from coach.main import _limits, app
from coach.worker import process_one

ORIGIN = {'Origin': 'http://localhost:3000'}
SAMPLE = Path(__file__).resolve().parents[3] / 'samples/steady-2km.gpx'


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ['DATA_DIR'] = self.temp.name
        os.environ['DATABASE_URL'] = f'sqlite:///{self.temp.name}/test.db'
        settings.cache_clear()
        if database._engine:
            database._engine.dispose()
        database._engine = None
        _limits.clear()
        self.client = TestClient(app, headers=ORIGIN)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        database._engine.dispose()
        database._engine = None
        self.temp.cleanup()

    def signup(self, name='Alice', client=None):
        client = client or self.client
        result = client.post('/auth/signup', json={'email': f'{name.lower()}@example.com', 'password': 'secure-test-password', 'display_name': name})
        self.assertEqual(result.status_code, 201, result.text)
        profile = client.get('/profile')
        self.assertEqual(profile.status_code, 200)
        return profile.json()['id']

    def other(self, name):
        client = TestClient(app, headers=ORIGIN)
        self.signup(name, client)
        return client

    def upload(self, client=None, data=None):
        result = (client or self.client).post('/runs', files={'file': ('fixture.gpx', data or SAMPLE.read_bytes(), 'application/gpx+xml')})
        self.assertEqual(result.status_code, 202, result.text)
        return result.json()

    def test_complete_local_lifecycle(self):
        user_id = self.signup()
        self.assertIn('HttpOnly', self.client.cookies.get('rc_access') and self.client.post('/auth/login', json={'email': 'alice@example.com', 'password': 'secure-test-password'}).headers['set-cookie'])
        update = self.client.patch('/profile', json={'display_name': 'Alice', 'goal_distance_km': 10, 'goal_time_min': 60, 'runs_per_week': 3})
        self.assertEqual(update.status_code, 200)
        run = self.upload()
        self.assertEqual(run['status'], 'queued')
        self.assertTrue(process_one())
        analysis = self.client.get(f"/runs/{run['id']}").json()
        self.assertEqual(analysis['status'], 'completed')
        self.assertGreater(analysis['analysis']['distance_km'], 2)
        self.assertEqual(self.upload()['id'], run['id'])
        self.assertEqual(self.client.get('/dashboard').json()['runs_28d'], 0)  # old fixture excluded
        plan_response = self.client.post('/plans')
        self.assertEqual(plan_response.status_code, 201, plan_response.text)
        plan = plan_response.json()
        self.assertEqual(self.client.post('/plans').json()['id'], plan['id'])
        path = f"/plans/{plan['id']}/days/0/completion"
        self.assertEqual(self.client.put(path, json={'run_id': run['id']}).status_code, 200)
        self.assertEqual(len(self.client.get('/plans').json()[0]['completions']), 1)
        export = self.client.get('/account/export')
        self.assertEqual(export.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            account = json.loads(archive.read('account.json'))
            self.assertEqual(account['profile']['id'], user_id)
            self.assertEqual(archive.read(f"gpx/{run['id']}.gpx"), SAMPLE.read_bytes())
        self.assertEqual(self.client.get(f"/runs/{run['id']}/file").content, SAMPLE.read_bytes())
        self.assertEqual(self.client.delete(f"/runs/{run['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/runs/{run['id']}").status_code, 404)
        self.assertIsNone(self.client.get('/plans').json()[0]['completions'][0]['run_id'])
        self.assertEqual(self.client.delete(path).status_code, 200)
        self.assertEqual(self.client.request('DELETE', '/account', json={'confirm': 'DELETE'}).status_code, 200)
        self.assertEqual(self.client.get('/profile').status_code, 401)
        self.assertFalse(any((Path(self.temp.name)/'files').rglob('*.gpx')))

    def test_crew_authorization_consent_and_owner_protection(self):
        alice_id = self.signup()
        crew = self.client.post('/crews', json={'name': 'Beta Crew'}).json()
        cid = crew['id']
        code = self.client.post(f'/crews/{cid}/invites').json()['code']
        bob = self.other('Bob')
        bob_id = bob.get('/profile').json()['id']
        self.assertEqual(bob.get(f'/crews/{cid}/summary').status_code, 403)
        self.assertEqual(bob.post('/crews/join', json={'code': code}).status_code, 200)
        self.assertEqual(bob.get(f'/crews/{cid}').status_code, 403)
        self.assertEqual(self.client.patch(f'/crews/{cid}/members/{bob_id}', json={'status':'active'}).status_code, 200)
        self.assertEqual(bob.post(f'/crews/{cid}/invites').status_code, 403)
        self.assertEqual(bob.patch(f'/crews/{cid}/members/{bob_id}', json={'role':'admin'}).status_code, 403)
        self.assertEqual(self.client.patch(f'/crews/{cid}/members/{bob_id}', json={'role':'admin'}).status_code, 200)
        self.assertEqual(bob.patch(f'/crews/{cid}/members/{alice_id}', json={'status':'rejected'}).status_code, 403)
        self.assertEqual(self.client.delete(f'/crews/{cid}/membership').status_code, 409)
        self.assertEqual(self.client.request('DELETE', '/account', json={'confirm':'DELETE'}).status_code, 409)
        self.assertTrue(bob.get(f'/crews/{cid}/summary').json()['suppressed'])
        self.assertEqual(bob.patch(f'/crews/{cid}/consent', json={'share_summary':True}).status_code, 200)
        self.assertEqual(bob.get(f'/crews/{cid}/summary').json()['consenting_members'], 1)
        self.assertEqual(self.client.post(f'/crews/{cid}/transfer', json={'user_id':bob_id}).status_code, 200)
        self.assertEqual(self.client.delete(f'/crews/{cid}/membership').status_code, 200)

    def test_operator_cannot_read_other_member_details_or_files(self):
        self.signup()
        bob = self.other('Bob')
        run = self.upload(bob)
        process_one()
        for path in (f"/runs/{run['id']}", f"/runs/{run['id']}/file"):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.delete(f"/runs/{run['id']}").status_code, 404)
        self.assertEqual(self.client.get('/runs').json()['items'], [])
        self.assertNotIn(run['id'], self.client.get('/account/export').content.decode('latin1'))

    def test_three_member_aggregate_and_immediate_revocation(self):
        self.signup()
        cid = self.client.post('/crews', json={'name':'Crew'}).json()['id']
        code = self.client.post(f'/crews/{cid}/invites').json()['code']
        clients = [self.client, self.other('Bob'), self.other('Carol')]
        for c in clients[1:]:
            c.post('/crews/join', json={'code':code})
            target = c.get('/profile').json()['id']
            self.client.patch(f'/crews/{cid}/members/{target}', json={'status':'active'})
        today = datetime.now(timezone.utc).date().isoformat()
        data = SAMPLE.read_bytes().replace(b'2026-01-01', today.encode())
        for c in clients:
            self.upload(c, data)
            self.assertEqual(c.patch(f'/crews/{cid}/consent',json={'share_summary':True}).status_code, 200)
            process_one()
        summary = self.client.get(f'/crews/{cid}/summary').json()
        self.assertFalse(summary['suppressed'])
        self.assertEqual(summary['run_count'],3)
        self.assertGreater(summary['distance_km'],6)
        self.assertEqual(set(summary),{'consenting_members','suppressed','distance_km','run_count'})
        clients[1].patch(f'/crews/{cid}/consent',json={'share_summary':False})
        self.assertTrue(self.client.get(f'/crews/{cid}/summary').json()['suppressed'])

    def test_csrf_unknown_fields_and_auth_failures(self):
        self.signup()
        self.assertEqual(self.client.patch('/profile',headers={'Origin':'https://attacker.invalid'},json={}).status_code,403)
        self.assertEqual(self.client.post('/crews',json={'name':'Crew','owner_id':'forged'}).status_code,422)
        self.assertEqual(self.client.patch('/profile',json={'display_name':'A','goal_distance_km':10,'goal_time_min':None}).status_code,422)
        self.assertEqual(self.client.post('/auth/login',json={'email':'alice@example.com','password':'wrong-password'}).status_code,401)
        self.client.post('/auth/logout')
        self.assertEqual(self.client.get('/runs').status_code,401)

    def test_bad_gpx_and_invalid_ids(self):
        self.signup()
        self.assertEqual(self.client.post('/runs',files={'file':('bad.gpx',b'<gpx/>')}).status_code,422)
        self.assertEqual(self.client.get('/runs/not-a-uuid').status_code,404)
        self.assertEqual(self.client.post('/runs',content=b'x',headers={'Content-Length':'11000000'}).status_code,413)

    def test_lease_recovery_and_no_record_resurrection(self):
        self.signup()
        run = self.upload()
        with session() as db:
            item=db.get(Run,run['id']); item.status='processing'; item.lease_until=time.time()-10; item.attempts=1; db.commit()
        self.assertTrue(process_one())
        self.assertEqual(self.client.get(f"/runs/{run['id']}").json()['status'],'completed')
        self.client.delete(f"/runs/{run['id']}")
        self.assertFalse(process_one())

    def test_transient_storage_retry_limit(self):
        self.signup(); run=self.upload()
        with patch.object(storage,'get',side_effect=OSError('storage unavailable')):
            for _ in range(3):
                self.assertTrue(process_one())
        item=self.client.get(f"/runs/{run['id']}").json()
        self.assertEqual(item['status'],'failed')
        self.assertEqual(item['attempts'],3)
        self.assertFalse(process_one())

    def test_account_deletion_removes_actual_file(self):
        self.signup(); self.upload(); process_one()
        self.assertTrue(any((Path(self.temp.name)/'files').rglob('*.gpx')))
        response=self.client.request('DELETE','/account',json={'confirm':'DELETE'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(any((Path(self.temp.name)/'files').rglob('*.gpx')))

    def test_invalid_signature_rejected_and_production_fails_closed(self):
        self.signup()
        self.client.cookies.clear()
        response=self.client.get('/profile',headers={'Authorization':'Bearer forged'})
        self.assertEqual(response.status_code,401)
        with self.assertRaises(RuntimeError):
            Settings(mode='production',database_url='sqlite://',supabase_url='',allowed_origins='http://localhost:3000').validate_runtime()


if __name__ == '__main__':
    unittest.main()
