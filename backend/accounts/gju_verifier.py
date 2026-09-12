"""
GJU credential verifier.

At first-time signup the Archive proves a person is a real GJU member by
logging into the **MyGJU portal** (https://mygju.gju.edu.jo) with the
credentials they entered. This is the single source of truth for "is this a
genuine GJU account"; everyday logins afterwards check only our own stored
Argon2 hash and never touch GJU.

Public contract:

    verify(email, password) -> "ok" | "wrong" | "unavailable"

    ok           the portal accepted the credentials
    wrong        the portal rejected the credentials
    unavailable  we could not get a definitive answer (WAF block, portal down,
                 timeout, circuit breaker open) — the caller should fall back,
                 never treat this as either success or failure

Design constraints (see the auth-research memo):
  * MyGJU's WAF blocks browsers carrying an automation fingerprint, so the
    browser is launched with that fingerprint stripped (navigator.webdriver
    etc.). With it stripped the WAF passes even fully headless, so it runs
    headless by default (GJU_VERIFIER_HEADLESS=True) — no window, no virtual
    display needed on a server. Set it False only to watch a run.
  * Exactly ONE login attempt per call — no internal retries. GJU throttles
    attempts aggressively; an ambiguous result is classified "unavailable"
    rather than retried.
  * A process-wide circuit breaker short-circuits to "unavailable" after
    repeated failures so a burst of signups can't hammer a blocked portal.
  * The password is never logged; only the outcome and a generic error class.
"""
from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Iterator, Literal

from django.conf import settings

logger = logging.getLogger(__name__)

VerifyResult = Literal["ok", "wrong", "unavailable"]


class GjuSessionError(Exception):
    """authenticated_session() could not produce a logged-in page."""

LOGIN_URL = "https://mygju.gju.edu.jo/faces/index.xhtml"
USERNAME_SELECTOR = 'input[name="j_idt15:login_username"]'
PASSWORD_SELECTOR = 'input[name="j_idt15:login_password"]'

# Substrings (matched case-insensitively against the post-login page text /
# URL) that classify the outcome. Order of checks matters: a WAF block can
# superficially resemble a "wrong" page, so blocks are checked first.
_BLOCK_MARKERS = ("web page blocked", "attack id", "captcha", "validation needed")
_SUCCESS_MARKERS = ("welcome to your account", "logout")
# MyGJU's actual rejection text is "Please enter a valid username and/or
# password"; the rest are defensive fallbacks for other phrasings.
_WRONG_MARKERS = ("please enter a valid", "invalid", "incorrect", "failed")

# The automation-fingerprint fixes that get MyGJU's WAF to let us through.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = { runtime: {} };
"""


# --- circuit breaker ------------------------------------------------------
# Per-process state (Django runs several worker processes; each keeps its own
# breaker, which is fine — the goal is to damp a burst, not coordinate globally).
_cb_lock = threading.Lock()
_cb_consecutive_unavailable = 0
_cb_open_until = 0.0


def _breaker_is_open() -> bool:
    with _cb_lock:
        return time.monotonic() < _cb_open_until


def _breaker_record(result: VerifyResult) -> None:
    """A definitive answer resets the breaker; repeated 'unavailable' trips it."""
    global _cb_consecutive_unavailable, _cb_open_until
    threshold = getattr(settings, "GJU_VERIFIER_BREAKER_THRESHOLD", 3)
    cooldown = getattr(settings, "GJU_VERIFIER_BREAKER_COOLDOWN_S", 1800)
    with _cb_lock:
        if result == "unavailable":
            _cb_consecutive_unavailable += 1
            if _cb_consecutive_unavailable >= threshold:
                _cb_open_until = time.monotonic() + cooldown
                logger.warning(
                    "GJU verifier circuit breaker opened for %ss after %s "
                    "consecutive unavailable results.",
                    cooldown,
                    _cb_consecutive_unavailable,
                )
        else:
            _cb_consecutive_unavailable = 0
            _cb_open_until = 0.0


def _classify(final_url: str, body_text: str) -> VerifyResult:
    """
    Pure classification of a post-login page. Kept separate from the browser
    so it can be unit-tested against saved fixture HTML with no network.
    """
    url = (final_url or "").lower()
    text = (body_text or "").lower()

    if any(m in text for m in _BLOCK_MARKERS):
        return "unavailable"
    # Success: we left the login page (index.xhtml) and the authed chrome shows.
    left_login = "index.xhtml" not in url
    if left_login and any(m in text for m in _SUCCESS_MARKERS):
        return "ok"
    if any(m in text for m in _WRONG_MARKERS):
        return "wrong"
    # Anything we can't confidently read is treated as unavailable, never as a
    # silent pass or fail.
    return "unavailable"


def _run_login(username: str, password: str) -> tuple[str, str]:
    """
    Drive one MyGJU login attempt and return (final_url, body_text).

    Playwright is imported lazily so the module (and the test suite, which
    mocks this function) imports fine without the browser installed. Raises on
    any browser/timeout failure; the caller maps that to "unavailable".
    """
    from playwright.sync_api import sync_playwright

    headless = getattr(settings, "GJU_VERIFIER_HEADLESS", False)
    timeout_ms = getattr(settings, "GJU_VERIFIER_TIMEOUT_MS", 15000)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Amman",
            )
            context.add_init_script(_STEALTH_INIT)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            page.goto(LOGIN_URL, wait_until="domcontentloaded")

            # If the WAF blocked the load, there is no form; return what we see
            # so _classify can call it "unavailable".
            if not page.locator(USERNAME_SELECTOR).count():
                return page.url, page.inner_text("body")

            _fill_and_submit_login(page, username, password, timeout_ms)
            return page.url, page.inner_text("body")
        finally:
            browser.close()


def _fill_and_submit_login(page, username: str, password: str, timeout_ms: int) -> None:
    """Shared fill/submit step used by both _run_login and authenticated_session."""
    page.fill(USERNAME_SELECTOR, username)
    page.fill(PASSWORD_SELECTOR, password)

    # The submit button's JSF id is auto-generated and unstable, so we click
    # the first submit-like control rather than target it by id. (This is the
    # submit path proven against the live portal.)
    submit = page.locator('input[type="submit"], button[type="submit"], button').first
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
            submit.click()
    except Exception:
        # JSF may postback via AJAX without a full navigation; fall through
        # and read whatever the page became.
        pass

    page.wait_for_timeout(1000)  # let any AJAX postback settle


@contextlib.contextmanager
def authenticated_session(email: str, password: str) -> Iterator["Page"]:  # noqa: F821
    """
    Log into MyGJU and yield an authenticated Playwright `page` for the
    caller to navigate around and scrape (e.g. the sync worker fetching a
    student's profile/grades). Closes the browser on exit either way.

    Raises GjuSessionError if the login doesn't succeed -- unlike verify(),
    there is no "unavailable" to return to a caller here: the sync worker
    decides for itself how to record/retry a failure per student. Honors the
    same circuit breaker as verify() (same process, same portal) so a WAF
    block or outage backs off both signup and sync attempts together.
    """
    from playwright.sync_api import sync_playwright

    if not getattr(settings, "GJU_VERIFIER_ENABLED", True):
        raise GjuSessionError("GJU verifier is disabled (GJU_VERIFIER_ENABLED=False).")
    if _breaker_is_open():
        raise GjuSessionError("GJU verifier circuit breaker is open.")

    headless = getattr(settings, "GJU_VERIFIER_HEADLESS", False)
    timeout_ms = getattr(settings, "GJU_VERIFIER_TIMEOUT_MS", 15000)
    username = email.split("@", 1)[0]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Amman",
            )
            context.add_init_script(_STEALTH_INIT)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            if not page.locator(USERNAME_SELECTOR).count():
                _breaker_record("unavailable")
                raise GjuSessionError("Could not reach the MyGJU login form (possible WAF block).")

            _fill_and_submit_login(page, username, password, timeout_ms)
            result = _classify(page.url, page.inner_text("body"))
            _breaker_record(result)
            if result != "ok":
                raise GjuSessionError(f"MyGJU login did not succeed (classified {result!r}).")

            yield page
        finally:
            browser.close()


def verify(email: str, password: str) -> VerifyResult:
    """Verify GJU credentials against MyGJU. See module docstring for contract."""
    if not getattr(settings, "GJU_VERIFIER_ENABLED", True):
        return "unavailable"

    if _breaker_is_open():
        logger.info("GJU verifier skipped: circuit breaker open.")
        return "unavailable"

    username = email.split("@", 1)[0]

    try:
        final_url, body_text = _run_login(username, password)
        result = _classify(final_url, body_text)
    except Exception as exc:  # browser launch/timeout/navigation failures
        logger.warning("GJU verifier unavailable (%s).", exc.__class__.__name__)
        result = "unavailable"

    _breaker_record(result)
    return result
