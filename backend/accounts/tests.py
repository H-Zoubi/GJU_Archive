"""
Tests for accounts: the GJU verifier's classification logic and the LoginView
branches that consume it.

Nothing here touches the real MyGJU portal. `_classify` is exercised against
saved page fixtures, and LoginView's branches are exercised by mocking
`gju_verifier.verify` so no browser is launched.
"""
import base64
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from . import gju_verifier, services, vault_transit
from .models import GjuCredential
from .serializers import UserSerializer

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

    @mock.patch("accounts.services.vault_transit.encrypt", return_value="vault:v1:ct")
    @mock.patch.object(gju_verifier, "verify", return_value="ok")
    def test_ok_signup_also_stores_the_gju_credential(self, _verify, encrypt):
        # Signup is the one moment this app ever sees the real GJU password,
        # so it must be captured then -- not left to a separate step nobody
        # is ever prompted to take. See gju-vault-password-storage-decision.
        resp = self._post(password="real-gju-pw")
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(email="new@gju.edu.jo")
        encrypt.assert_called_once_with("real-gju-pw")
        credential = GjuCredential.objects.get(user=user)
        self.assertEqual(credential.ciphertext, b"vault:v1:ct")

    @mock.patch.object(services, "opt_in_gju_sync", side_effect=RuntimeError("vault is down"))
    @mock.patch.object(gju_verifier, "verify", return_value="ok")
    def test_signup_still_succeeds_if_credential_storage_fails(self, _verify, _opt_in):
        # A verified signup must not be blocked by Vault being unreachable --
        # sync is a bonus feature, account creation is the critical path.
        resp = self._post()
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(User.objects.filter(email="new@gju.edu.jo").exists())

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


class VaultTransitTests(TestCase):
    """encrypt()/decrypt() call the right transit path with the right token."""

    @override_settings(
        VAULT_ADDR="http://vault.test:8200",
        VAULT_TRANSIT_KEY_NAME="gju-credentials",
        VAULT_ENCRYPT_TOKEN="enc-tok",
    )
    def test_encrypt_uses_the_encrypt_token(self):
        with mock.patch.object(vault_transit, "hvac") as hvac_mod:
            client = hvac_mod.Client.return_value
            client.secrets.transit.encrypt_data.return_value = {
                "data": {"ciphertext": "vault:v1:xyz"}
            }
            result = vault_transit.encrypt("hunter2")
            hvac_mod.Client.assert_called_once_with(url="http://vault.test:8200", token="enc-tok")
            client.secrets.transit.encrypt_data.assert_called_once_with(
                name="gju-credentials", plaintext=base64.b64encode(b"hunter2").decode()
            )
            self.assertEqual(result, "vault:v1:xyz")

    @override_settings(VAULT_ENCRYPT_TOKEN="")
    def test_encrypt_without_a_configured_token_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            vault_transit.encrypt("hunter2")

    @override_settings(VAULT_DECRYPT_TOKEN="dec-tok")
    def test_decrypt_uses_the_decrypt_token(self):
        with mock.patch.object(vault_transit, "hvac") as hvac_mod:
            client = hvac_mod.Client.return_value
            client.secrets.transit.decrypt_data.return_value = {
                "data": {"plaintext": base64.b64encode(b"hunter2").decode()}
            }
            result = vault_transit.decrypt("vault:v1:xyz")
            self.assertEqual(hvac_mod.Client.call_args.kwargs["token"], "dec-tok")
            self.assertEqual(result, "hunter2")

    @override_settings(VAULT_DECRYPT_TOKEN="")
    def test_decrypt_without_a_configured_token_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            vault_transit.decrypt("vault:v1:xyz")


class GjuSyncViewTests(TestCase):
    """The opt-in/revoke endpoint never touches the plaintext password itself."""

    def setUp(self):
        self.user = User.objects.create_user(email="student@gju.edu.jo", password="pw12345")
        self.client.force_login(self.user)
        self.url = reverse("auth-gju-sync")

    @mock.patch("accounts.services.vault_transit.encrypt", return_value="vault:v1:ct")
    def test_opt_in_stores_ciphertext_not_plaintext(self, encrypt):
        resp = self.client.post(self.url, {"password": "real-gju-pw"})
        self.assertEqual(resp.status_code, 204)
        encrypt.assert_called_once_with("real-gju-pw")
        credential = GjuCredential.objects.get(user=self.user)
        self.assertEqual(credential.ciphertext, b"vault:v1:ct")

    def test_revoke_deletes_the_credential(self):
        GjuCredential.objects.create(user=self.user, ciphertext=b"vault:v1:ct")
        resp = self.client.delete(self.url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(GjuCredential.objects.filter(user=self.user).exists())

    def test_requires_authentication(self):
        self.client.logout()
        resp = self.client.post(self.url, {"password": "x"})
        self.assertIn(resp.status_code, (401, 403))


class GjuCredentialExposureTests(TestCase):
    """GjuCredential must never surface through the admin or the API."""

    def test_not_registered_in_admin(self):
        self.assertNotIn(GjuCredential, admin.site._registry)

    def test_user_serializer_never_mentions_the_credential(self):
        user = User.objects.create_user(email="s@gju.edu.jo", password="pw12345")
        GjuCredential.objects.create(user=user, ciphertext=b"vault:v1:ct")
        rendered = str(UserSerializer(user).data)
        self.assertNotIn("ciphertext", rendered)
        self.assertNotIn("vault:v1:ct", rendered)
