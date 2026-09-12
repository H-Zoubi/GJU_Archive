"""
Tests for accounts: the GJU verifier's classification logic and the LoginView
branches that consume it.

Nothing here touches the real MyGJU portal. `_classify` is exercised against
saved page fixtures, and LoginView's branches are exercised by mocking
`gju_verifier.verify` so no browser is launched.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from . import gju_verifier

User = get_user_model()

LOGIN_URL_NAME = "auth-login"

# Real markers captured from a live MyGJU session (see auth-research memo).
WELCOME_URL = "https://mygju.gju.edu.jo/faces/welcome_page.xhtml"
LOGIN_URL = gju_verifier.LOGIN_URL

SUCCESS_BODY = (
    "Hello Hamza Abdelal\nLogout\nHelp\nArabic\nCalendar\nProfile\n"
    "Academic Affairs\nRegistration\nWelcome to your account."
)
# The exact rejection text MyGJU renders on a failed login (captured live).
WRONG_BODY = (
    "Please enter a valid username and/or password\nUsername:\nPassword:\n"
    "Login as Student\nLogin as Employee\n"
    "Please enter your GJU Email credentials to login"
)
BLOCKED_BODY = (
    "block\nWeb Page Blocked!\nThe page cannot be displayed.\n"
    "URL: mygju.gju.edu.jo/faces/index.xhtml\nAttack ID: 20000051"
)
CAPTCHA_BODY = (
    "Validation request\nUser validation required to continue..\n"
    "Validation needed due to the detection of invalid input from this "
    "client IP address, error code : 426"
)


class ClassifyTests(TestCase):
    """`_classify` maps (final_url, body_text) to ok / wrong / unavailable."""

    def test_success_page_is_ok(self):
        self.assertEqual(gju_verifier._classify(WELCOME_URL, SUCCESS_BODY), "ok")

    def test_wrong_credentials_page_is_wrong(self):
        self.assertEqual(gju_verifier._classify(LOGIN_URL, WRONG_BODY), "wrong")

    def test_waf_block_is_unavailable(self):
        self.assertEqual(gju_verifier._classify(LOGIN_URL, BLOCKED_BODY), "unavailable")

    def test_captcha_interstitial_is_unavailable(self):
        self.assertEqual(gju_verifier._classify(LOGIN_URL, CAPTCHA_BODY), "unavailable")

    def test_block_wins_even_if_it_looks_like_an_error_page(self):
        # A block page containing the word "invalid" must still be unavailable,
        # not a false "wrong" that would tell an attacker the creds were bad.
        body = CAPTCHA_BODY + "\ninvalid input"
        self.assertEqual(gju_verifier._classify(LOGIN_URL, body), "unavailable")

    def test_still_on_login_page_without_error_is_unavailable(self):
        # Left on index.xhtml with no recognizable marker: don't guess.
        self.assertEqual(gju_verifier._classify(LOGIN_URL, "MyGJU\nLogin\n"), "unavailable")

    def test_success_markers_without_leaving_login_page_is_not_ok(self):
        # "Logout" text but still on the login URL shouldn't count as success.
        self.assertNotEqual(gju_verifier._classify(LOGIN_URL, SUCCESS_BODY), "ok")


class VerifyBreakerTests(TestCase):
    """verify() honors the enable flag and the circuit breaker."""

    def setUp(self):
        # Reset the module-level breaker between tests.
        gju_verifier._cb_consecutive_unavailable = 0
        gju_verifier._cb_open_until = 0.0

    @override_settings(GJU_VERIFIER_ENABLED=False)
    def test_disabled_verifier_returns_unavailable_without_browser(self):
        with mock.patch.object(gju_verifier, "_run_login") as run:
            self.assertEqual(gju_verifier.verify("a@gju.edu.jo", "pw"), "unavailable")
            run.assert_not_called()

    @override_settings(GJU_VERIFIER_BREAKER_THRESHOLD=2, GJU_VERIFIER_BREAKER_COOLDOWN_S=999)
    def test_breaker_opens_after_repeated_unavailable_and_skips_browser(self):
        # Two browser failures trip the breaker; the third call must not even
        # attempt a login.
        with mock.patch.object(gju_verifier, "_run_login", side_effect=RuntimeError("boom")) as run:
            self.assertEqual(gju_verifier.verify("a@gju.edu.jo", "pw"), "unavailable")
            self.assertEqual(gju_verifier.verify("a@gju.edu.jo", "pw"), "unavailable")
            self.assertEqual(run.call_count, 2)
            # Breaker now open: no further browser attempts.
            self.assertEqual(gju_verifier.verify("a@gju.edu.jo", "pw"), "unavailable")
            self.assertEqual(run.call_count, 2)

    def test_a_definitive_result_resets_the_breaker(self):
        with mock.patch.object(gju_verifier, "_run_login") as run:
            run.side_effect = RuntimeError("boom")
            gju_verifier.verify("a@gju.edu.jo", "pw")  # 1 unavailable
            run.side_effect = None
            run.return_value = (WELCOME_URL, SUCCESS_BODY)
            self.assertEqual(gju_verifier.verify("a@gju.edu.jo", "pw"), "ok")
            self.assertEqual(gju_verifier._cb_consecutive_unavailable, 0)

    def test_username_is_the_email_local_part(self):
        with mock.patch.object(gju_verifier, "_run_login") as run:
            run.return_value = (WELCOME_URL, SUCCESS_BODY)
            gju_verifier.verify("jsmith20@gju.edu.jo", "pw")
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], "jsmith20")


class LoginViewBranchTests(TestCase):
    """The signup path branches on the three verify() outcomes."""

    def setUp(self):
        self.url = reverse(LOGIN_URL_NAME)

    def _post(self, email="new@gju.edu.jo", password="secret-pw"):
        return self.client.post(self.url, {"email": email, "password": password})

    @mock.patch.object(gju_verifier, "verify", return_value="ok")
    def test_ok_creates_a_verified_account(self, _verify):
        resp = self._post()
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(email="new@gju.edu.jo")
        self.assertTrue(user.is_gju_verified)

    @mock.patch.object(gju_verifier, "verify", return_value="wrong")
    def test_wrong_rejects_and_creates_nothing(self, _verify):
        resp = self._post()
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(User.objects.filter(email="new@gju.edu.jo").exists())

    @mock.patch.object(gju_verifier, "verify", return_value="unavailable")
    def test_unavailable_fails_closed_with_503(self, _verify):
        resp = self._post()
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(User.objects.filter(email="new@gju.edu.jo").exists())

    @mock.patch.object(gju_verifier, "verify")
    def test_non_gju_email_is_rejected_before_verifying(self, verify):
        resp = self._post(email="someone@gmail.com")
        self.assertEqual(resp.status_code, 400)
        verify.assert_not_called()

    @mock.patch.object(gju_verifier, "verify")
    def test_existing_account_skips_gju_check_entirely(self, verify):
        # An admin/superadmin with a non-GJU email must be able to sign in
        # against the local password hash without touching the verifier.
        User.objects.create_user(email="admin@example.com", password="adminpass")
        resp = self._post(email="admin@example.com", password="adminpass")
        self.assertEqual(resp.status_code, 200)
        verify.assert_not_called()
