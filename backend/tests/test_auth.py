import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path

from app.auth import AuthService, decode_token, hash_password, verify_password
from app.database import SQLiteRepository


class AuthTests(unittest.TestCase):
    def test_concurrent_refresh_rotates_each_token_at_most_once(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteRepository(Path(directory) / "auth.db")
            auth = AuthService(repository, "test-secret")
            session = auth.register("concurrent@example.test", "strong-password")
            barrier = threading.Barrier(2)
            original = repository.get_refresh_token
            def read_token(token_hash):
                row = original(token_hash)
                barrier.wait(timeout=5)
                return row
            def refresh():
                try:
                    return auth.refresh(session["refresh_token"])
                except ValueError:
                    return None
            with patch.object(repository, "get_refresh_token", side_effect=read_token), ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: refresh(), range(2)))
            self.assertEqual(sum(result is not None for result in results), 1)

    def test_password_is_hashed_and_verifies(self):
        encoded = hash_password("correct horse battery")
        self.assertNotIn("correct horse", encoded)
        self.assertTrue(verify_password("correct horse battery", encoded))
        self.assertFalse(verify_password("wrong password", encoded))

    def test_register_login_and_expiring_token_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthService(SQLiteRepository(Path(directory) / "auth.db"), "test-secret", 60)
            created = auth.register("researcher@example.test", "strong-password", role="ADMIN")
            self.assertEqual(created["token_type"], "bearer")
            self.assertEqual(created["user"]["role"], "USER")
            payload = decode_token(created["access_token"], "test-secret")
            self.assertEqual(payload["email"], "researcher@example.test")
            logged_in = auth.login("researcher@example.test", "strong-password")
            self.assertTrue(logged_in["access_token"])
            with self.assertRaises(ValueError):
                auth.login("researcher@example.test", "bad-password")


if __name__ == "__main__":
    unittest.main()
