import io
import json
import sys
import types
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    class _CookieJar:
        def set(self, *args, **kwargs):
            pass

    class Session:
        def __init__(self):
            self.cookies = _CookieJar()
            self.headers = {}

        def request(self, *args, **kwargs):
            raise AssertionError("unexpected real HTTP request")

    requests.RequestException = RequestException
    requests.Timeout = Timeout
    requests.Session = Session
    sys.modules["requests"] = requests

try:
    import colorama  # noqa: F401
except ModuleNotFoundError:
    colorama = types.ModuleType("colorama")
    colorama.init = lambda **kwargs: None
    colorama.Fore = SimpleNamespace(
        LIGHTRED_EX="", LIGHTGREEN_EX="", LIGHTYELLOW_EX="",
        LIGHTBLUE_EX="", LIGHTMAGENTA_EX="", LIGHTCYAN_EX="",
        LIGHTWHITE_EX="", LIGHTBLACK_EX="",
    )
    colorama.Style = SimpleNamespace(RESET_ALL="", BRIGHT="")
    sys.modules["colorama"] = colorama

import InstagramSession as app


_NO_JSON = object()


class FakeResponse:
    def __init__(self, status=200, data=_NO_JSON, text=None,
                 url="https://www.instagram.com/", headers=None):
        self.status_code = status
        self._data = data
        self.text = (json.dumps(data) if text is None and data is not _NO_JSON
                     else (text or ""))
        self.url = url
        self.headers = headers or {}

    def json(self):
        if self._data is _NO_JSON:
            raise ValueError("not json")
        return self._data


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


class FakeStore:
    def __init__(self):
        self.saved = 0
        self.added = []
        self.accounts = []

    def save(self):
        self.saved += 1

    def enabled(self):
        return [account for account in self.accounts
                if account.get("enabled", True)]

    def add(self, cookie, username="", xsmm_id=""):
        account = {
            "ds_user_id": "123", "cookie": cookie,
            "username": username, "xsmm_id": xsmm_id, "enabled": True,
        }
        self.added.append(account)
        return account


class InstagramDiagnosticTests(unittest.TestCase):
    COOKIE = "sessionid=session-secret; ds_user_id=123; csrftoken=csrf-secret"

    def make_api(self):
        return app.InstagramAPI(self.COOKIE)

    def diagnose(self, response=None, error=None):
        api = self.make_api()
        if error is not None:
            api.get = lambda *args, **kwargs: (_ for _ in ()).throw(error)
        else:
            api.get = lambda *args, **kwargs: response
        alive = api.is_alive()
        return api, alive

    def test_live_requires_valid_user_json_not_only_content_type(self):
        response = FakeResponse(
            data={"user": {"pk": "123", "username": "alice"}},
            headers={"content-type": "text/plain"},
        )
        api, alive = self.diagnose(response)
        self.assertTrue(alive)
        self.assertEqual("LIVE", api.last_session_diagnostic["status"])

    def test_auth_error_uses_explicit_json_evidence(self):
        response = FakeResponse(
            status=401,
            data={"status": "fail", "message": "invalid_session"},
            headers={"content-type": "application/json"},
        )
        api, alive = self.diagnose(response)
        self.assertFalse(alive)
        self.assertEqual("AUTH_INVALID", api.last_session_diagnostic["status"])

    def test_login_redirect(self):
        response = FakeResponse(
            status=200,
            text="<html></html>",
            url=("https://user:password@www.instagram.com/accounts/login/"
                 "?next=%2Fsecret#token"),
        )
        api, alive = self.diagnose(response)
        self.assertFalse(alive)
        self.assertEqual("LOGIN_REQUIRED", api.last_session_diagnostic["status"])
        self.assertEqual(
            "https://www.instagram.com/accounts/login/",
            api.last_session_diagnostic["final_url"],
        )

    def test_checkpoint_json_marker(self):
        response = FakeResponse(
            status=400,
            data={"message": "challenge_required",
                  "challenge": {"url": "/challenge/abc"}},
        )
        api, alive = self.diagnose(response)
        self.assertFalse(alive)
        self.assertEqual("CHECKPOINT", api.last_session_diagnostic["status"])

    def test_rate_limit(self):
        api, alive = self.diagnose(FakeResponse(status=429, text=""))
        self.assertFalse(alive)
        self.assertEqual("RATE_LIMITED", api.last_session_diagnostic["status"])
        self.assertFalse(api.diagnostic_requires_disable(api.last_session_diagnostic))

    def test_timeout(self):
        api, alive = self.diagnose(error=requests.Timeout("timed out"))
        self.assertFalse(alive)
        self.assertEqual("NETWORK_ERROR", api.last_session_diagnostic["status"])
        self.assertNotIn("timed out", str(api.last_session_diagnostic))

    def test_http_500(self):
        api, alive = self.diagnose(FakeResponse(status=500, text="server error"))
        self.assertFalse(alive)
        self.assertEqual("HTTP_ERROR", api.last_session_diagnostic["status"])
        self.assertEqual(500, api.last_session_diagnostic["http_status"])

    def test_http_200_html_is_non_json_not_auth_invalid(self):
        api, alive = self.diagnose(
            FakeResponse(status=200, text="<html>temporary page</html>"),
        )
        self.assertFalse(alive)
        self.assertEqual("NON_JSON_RESPONSE",
                         api.last_session_diagnostic["status"])

    def test_http_200_malformed_json_structure(self):
        api, alive = self.diagnose(FakeResponse(data={"status": "ok"}))
        self.assertFalse(alive)
        self.assertEqual("MALFORMED_RESPONSE",
                         api.last_session_diagnostic["status"])

    def test_mismatched_user_id_is_not_live(self):
        api, alive = self.diagnose(
            FakeResponse(data={"user": {"pk": "999", "username": "other"}}),
        )
        self.assertFalse(alive)
        self.assertEqual("MALFORMED_RESPONSE",
                         api.last_session_diagnostic["status"])
        self.assertEqual("USER_ID_MISMATCH",
                         api.last_session_diagnostic["reason"])

    def test_load_diagnostics_network_redirect_rate_limit_and_http_error(self):
        cases = [
            (FakeSession(error=requests.Timeout("secret detail")), "NETWORK_ERROR"),
            (FakeSession(FakeResponse(
                url="https://www.instagram.com/accounts/login/?next=/",
                text="<html></html>",
            )), "LOGIN_REQUIRED"),
            (FakeSession(FakeResponse(status=429)), "RATE_LIMITED"),
            (FakeSession(FakeResponse(status=503)), "HTTP_ERROR"),
        ]
        for session, expected in cases:
            with self.subTest(expected=expected):
                api = self.make_api()
                api.session = session
                self.assertFalse(api.load())
                self.assertEqual(expected,
                                 api.last_session_diagnostic["status"])

    def test_load_success_keeps_boolean_contract(self):
        api = self.make_api()
        api.session = FakeSession(FakeResponse(status=200, text="<html></html>"))
        self.assertTrue(api.load())
        self.assertEqual("LOAD_OK", api.last_session_diagnostic["status"])

    def test_suspended_flow_still_uses_explicit_url_evidence(self):
        api = self.make_api()
        api.session = FakeSession(FakeResponse(
            url="https://www.instagram.com/accounts/suspended/",
        ))
        self.assertTrue(api.is_suspended())


class CallerPolicyTests(unittest.TestCase):
    COOKIE = InstagramDiagnosticTests.COOKIE

    @staticmethod
    def controlled_api(status, load_ok=True, alive=False):
        api = app.InstagramAPI(CallerPolicyTests.COOKIE)
        api.load = lambda: load_ok

        def is_alive():
            api._set_session_diagnostic(status, "ALIVE_CHECK", reason="TEST")
            return alive

        api.is_alive = is_alive
        api.is_suspended = lambda: False
        api.me = lambda: {"username": "alice", "pk": "123"}
        if not load_ok:
            api._set_session_diagnostic(status, "LOAD_HOME", reason="TEST")
        return api

    def test_get_ig_disables_only_durable_diagnostics(self):
        expectations = {
            "AUTH_INVALID": True,
            "LOGIN_REQUIRED": True,
            "CHECKPOINT": True,
            "SUSPENDED": True,
            "NETWORK_ERROR": False,
            "RATE_LIMITED": False,
            "HTTP_ERROR": False,
            "NON_JSON_RESPONSE": False,
            "MALFORMED_RESPONSE": False,
            "UNKNOWN_RESPONSE": False,
        }
        for status, should_disable in expectations.items():
            with self.subTest(status=status):
                store = FakeStore()
                worker = app.IGTaskWorker(None, store)
                account = {
                    "ds_user_id": "123", "cookie": self.COOKIE,
                    "username": "alice", "enabled": True,
                }
                fake_api = self.controlled_api(status)
                with patch.object(app, "InstagramAPI", return_value=fake_api), \
                        redirect_stdout(io.StringIO()):
                    result = worker._get_ig(account)
                self.assertIsNone(result)
                self.assertEqual(not should_disable, account["enabled"])
                self.assertEqual(1 if should_disable else 0, store.saved)

    def test_get_ig_keeps_transient_load_failure_enabled(self):
        store = FakeStore()
        worker = app.IGTaskWorker(None, store)
        account = {
            "ds_user_id": "123", "cookie": self.COOKIE,
            "username": "alice", "enabled": True,
        }
        fake_api = self.controlled_api("NETWORK_ERROR", load_ok=False)
        with patch.object(app, "InstagramAPI", return_value=fake_api), \
                redirect_stdout(io.StringIO()):
            result = worker._get_ig(account)
        self.assertIsNone(result)
        self.assertTrue(account["enabled"])
        self.assertEqual(0, store.saved)

    def test_check_live_accounts_uses_same_disable_policy(self):
        expectations = {
            "AUTH_INVALID": True,
            "LOGIN_REQUIRED": True,
            "CHECKPOINT": True,
            "SUSPENDED": True,
            "NETWORK_ERROR": False,
            "RATE_LIMITED": False,
            "HTTP_ERROR": False,
            "NON_JSON_RESPONSE": False,
            "MALFORMED_RESPONSE": False,
            "UNKNOWN_RESPONSE": False,
        }
        for status, should_disable in expectations.items():
            with self.subTest(status=status):
                store = FakeStore()
                account = {
                    "ds_user_id": "123", "cookie": self.COOKIE,
                    "username": "alice", "enabled": True,
                }
                store.accounts = [account]
                worker = app.IGTaskWorker(None, store)
                worker.ig_cache["123"] = self.controlled_api(status)
                with redirect_stdout(io.StringIO()):
                    worker._check_live_accounts()
                self.assertEqual(not should_disable, account["enabled"])
                self.assertEqual(1 if should_disable else 0, store.saved)

    def test_add_account_network_error_does_not_claim_dead_session(self):
        store = FakeStore()
        fake_api = self.controlled_api("NETWORK_ERROR")
        config = SimpleNamespace(xsmm_token="", debug=False)
        output = io.StringIO()
        with patch.object(app, "InstagramAPI", return_value=fake_api), \
                patch("builtins.input", return_value=self.COOKIE), \
                redirect_stdout(output):
            app.add_account(store, config)
        rendered = output.getvalue()
        self.assertIn("lỗi mạng", rendered)
        self.assertNotIn("Session chết", rendered)
        self.assertEqual([], store.added)

    def test_add_account_auth_invalid_is_rejected_with_evidence_message(self):
        store = FakeStore()
        fake_api = self.controlled_api("AUTH_INVALID")
        config = SimpleNamespace(xsmm_token="", debug=False)
        output = io.StringIO()
        with patch.object(app, "InstagramAPI", return_value=fake_api), \
                patch("builtins.input", return_value=self.COOKIE), \
                redirect_stdout(output):
            app.add_account(store, config)
        self.assertIn("không còn hợp lệ", output.getvalue())
        self.assertEqual([], store.added)

    def test_add_account_live_flow_is_unchanged(self):
        store = FakeStore()
        fake_api = self.controlled_api("LIVE", alive=True)
        config = SimpleNamespace(xsmm_token="", debug=False)
        with patch.object(app, "InstagramAPI", return_value=fake_api), \
                patch("builtins.input", return_value=self.COOKIE), \
                redirect_stdout(io.StringIO()):
            app.add_account(store, config)
        self.assertEqual(1, len(store.added))
        self.assertEqual("alice", store.added[0]["username"])


if __name__ == "__main__":
    unittest.main()
