"""Security boundaries runnable without database or external account credentials."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import jwt
from fastapi import HTTPException
from starlette.requests import Request

from coach import auth, storage
from coach.config import Settings


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cfg = SimpleNamespace(mode='test', data_dir=Path(self.temp.name),
                                   dev_jwt_secret='test-only-32-character-minimum-secret')
        self.auth_patch = patch.object(auth, 'settings', return_value=self.cfg)
        self.storage_patch = patch.object(storage, 'settings', return_value=self.cfg)
        self.auth_patch.start(); self.storage_patch.start()
        self.user_id = str(uuid4())

    def tearDown(self):
        self.auth_patch.stop(); self.storage_patch.stop(); self.temp.cleanup()

    def rejected(self, token):
        with self.assertRaises(HTTPException) as result:
            auth.decode(token)
        self.assertEqual(result.exception.status_code, 401)

    def test_valid_local_token_and_different_user_identity(self):
        token = auth.issue(self.user_id)
        self.assertEqual(auth.decode(token)['sub'], self.user_id)
        request = Request({'type':'http', 'headers':[(b'authorization',f'Bearer {token}'.encode())]})
        self.assertEqual(auth.current_user(request), self.user_id)

    def test_forged_signature_and_unsigned_token_rejected(self):
        claims = auth.decode(auth.issue(self.user_id))
        self.rejected(jwt.encode(claims, 'attacker-key-with-a-separate-long-secret', algorithm='HS256'))
        self.rejected(jwt.encode(claims, '', algorithm='none'))

    def test_expired_wrong_audience_issuer_or_invalid_subject_rejected(self):
        valid = auth.decode(auth.issue(self.user_id))
        for changes in ({'exp':int(time.time())-10}, {'aud':'wrong-app'},
                        {'iss':'untrusted'}, {'sub':'not-a-uuid'}, {'iat':int(time.time())+1000}):
            with self.subTest(changes=changes):
                self.rejected(jwt.encode({**valid, **changes}, self.cfg.dev_jwt_secret, algorithm='HS256'))

    def test_missing_required_claims_and_session_rejected(self):
        claims = auth.decode(auth.issue(self.user_id))
        for key in ('sub','exp','iat'):
            changed = {k:v for k,v in claims.items() if k!=key}
            self.rejected(jwt.encode(changed,self.cfg.dev_jwt_secret,algorithm='HS256'))
        with self.assertRaises(HTTPException):
            auth.current_user(Request({'type':'http','headers':[]}))

    def test_salted_password_storage_and_invalid_password(self):
        password = 'a long test password'
        first, second = auth.password_hash(password), auth.password_hash(password)
        self.assertNotEqual(first,second)
        self.assertNotIn(password,first)
        self.assertTrue(auth.password_matches(password,first))
        self.assertFalse(auth.password_matches('a different password',first))

    def test_storage_path_traversal_rejected_and_deletion_is_real(self):
        for key in ('../outside','user/../outside','user/..','/absolute','user\\outside/file'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    storage.put(key,b'private')
        key = f'{self.user_id}/{uuid4()}.gpx'
        storage.put(key,b'private-gpx')
        self.assertEqual(storage.get(key),b'private-gpx')
        self.assertTrue(storage.location(key).exists())
        storage.delete(key)
        self.assertFalse(storage.location(key).exists())
        storage.delete(key)  # Retry is safe if external deletion succeeded earlier.

    def test_production_cannot_fall_back_to_development(self):
        for changes in ({'database_url':'sqlite:///dev.db'}, {'supabase_url':''},
                        {'allowed_origins':'http://localhost:3000'}, {'supabase_service_role_key':''}):
            cfg = Settings(**{'mode':'production', 'database_url':'postgresql+psycopg://unused',
                              'supabase_url':'https://project.supabase.co', 'supabase_anon_key':'test-key',
                              'supabase_service_role_key':'test-server-key',
                              'allowed_origins':'https://example.com', **changes})
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError): cfg.validate_runtime()


if __name__ == '__main__':
    unittest.main()
