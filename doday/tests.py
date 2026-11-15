"""Security baseline (Phase 0): settings, rate limiting, honeypots, password reset."""

import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from doday.ratelimit import client_ip
from events.models import Category, Event

User = get_user_model()
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SettingsTests(TestCase):
    """Load the settings in a fresh interpreter with a controlled environment.

    Skipped where a local .env file exists, because the settings read it and
    it would supply the very values these tests leave out on purpose.
    """

    def _load_settings(self, **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        clean.update(DJANGO_SETTINGS_MODULE="doday.settings", **env)
        code = "from django.conf import settings; print(settings.DEBUG)"
        return subprocess.run(
            [sys.executable, "-c", code], env={**clean, "PYTHONPATH": str(PROJECT_ROOT)},
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )

    def test_production_refuses_to_start_without_a_secret_key(self):
        if (PROJECT_ROOT / ".env").exists() or (PROJECT_ROOT / "api_key.env").exists():
            self.skipTest("a local .env file provides its own values")
        result = self._load_settings()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY is not set", result.stderr)

    def test_debug_is_off_unless_asked_for(self):
        if (PROJECT_ROOT / ".env").exists() or (PROJECT_ROOT / "api_key.env").exists():
            self.skipTest("a local .env file provides its own values")
        result = self._load_settings(DJANGO_SECRET_KEY="x" * 50)
        self.assertEqual(result.stdout.strip(), "False")
        result = self._load_settings(DJANGO_DEBUG="True")
        self.assertEqual(result.stdout.strip(), "True")


class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_forwarded_header_is_ignored_without_trusted_proxies(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR="10.0.0.9")
        self.assertEqual(client_ip(request), "10.0.0.9")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_real_client_is_read_behind_one_proxy(self):
        # The client can prepend anything; our proxy appends the address it saw.
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4", REMOTE_ADDR="10.0.0.9")
        self.assertEqual(client_ip(request), "1.2.3.4")


@override_settings(RATELIMIT_ENABLED=True)
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_login_is_blocked_after_too_many_attempts(self):
        data = {"username": "nobody@doday.co", "password": "wrong"}
        for _ in range(10):
            self.assertEqual(self.client.post(reverse("login"), data).status_code, 200)
        response = self.client.post(reverse("login"), data)
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many attempts", status_code=429)

    def test_limit_is_per_address(self):
        data = {"username": "nobody@doday.co", "password": "wrong"}
        for _ in range(11):
            self.client.post(reverse("login"), data)
        response = self.client.post(reverse("login"), data, REMOTE_ADDR="203.0.113.7")
        self.assertEqual(response.status_code, 200)

    def test_reading_the_page_is_never_limited(self):
        for _ in range(15):
            self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_event_proposals_are_limited(self):
        for _ in range(10):
            self.client.post(reverse("events:event_submit"), {})
        self.assertEqual(self.client.post(reverse("events:event_submit"), {}).status_code, 429)


class HoneypotTests(TestCase):
    def test_bot_proposal_is_not_saved_but_looks_accepted(self):
        category = Category.objects.create(name="Ferias")
        response = self.client.post(reverse("events:event_submit"), {
            "title": "Buy cheap watches", "description": "spam",
            "date_time": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            "location": "x", "category": category.pk, "is_free": "on",
            "submitter_name": "bot", "submitter_email": "bot@example.com",
            "website": "http://spam.example.com",
        })
        self.assertContains(response, "Proposal received")
        self.assertFalse(Event.objects.exists())

    def test_bot_signup_creates_no_account(self):
        response = self.client.post(reverse("signup"), {
            "email": "bot@example.com", "password1": "Str0ng-pass-123", "password2": "Str0ng-pass-123",
            "website": "http://spam.example.com",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.exists())

    def test_forms_include_the_hidden_field(self):
        self.assertContains(self.client.get(reverse("events:event_submit")), 'name="website"')
        self.assertContains(self.client.get(reverse("signup")), 'name="website"')


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@doday.co", "ana@doday.co", "Old-pass-12345")

    def test_login_page_links_to_the_reset_form(self):
        self.assertContains(self.client.get(reverse("login")), reverse("password_reset"))

    def test_full_reset_flow(self):
        response = self.client.post(reverse("password_reset"), {"email": "ana@doday.co"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Reset your Doday password")
        link = re.search(r"http://testserver(/accounts/reset/\S+)", mail.outbox[0].body).group(1)

        response = self.client.get(link, follow=True)
        self.assertContains(response, "Choose a new password")
        response = self.client.post(
            response.redirect_chain[-1][0],
            {"new_password1": "Brand-new-pass-987", "new_password2": "Brand-new-pass-987"},
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.assertTrue(self.client.login(username="ana@doday.co", password="Brand-new-pass-987"))

    def test_unknown_email_gets_the_same_answer_and_no_mail(self):
        response = self.client.post(reverse("password_reset"), {"email": "nobody@doday.co"}, follow=True)
        self.assertContains(response, "If there is an account with that email")
        self.assertEqual(len(mail.outbox), 0)

    def test_used_or_invalid_link_explains_itself(self):
        response = self.client.get(reverse("password_reset_confirm", args=["abc", "bad-token"]))
        self.assertContains(response, "This link is no longer valid")

    def test_pages_use_the_project_layout_not_the_admin_one(self):
        response = self.client.get(reverse("password_reset"))
        self.assertContains(response, "Find events in Medellín")
        self.assertNotContains(response, "Django administration")


class SeedEventsTests(TestCase):
    """The sample data must never open a door into the site."""

    def test_demo_organizers_cannot_log_in_and_are_not_staff(self):
        from django.core.management import call_command

        call_command("seed_events", verbosity=0, stdout=open(os.devnull, "w"))
        self.assertTrue(Event.objects.exists())
        for username in ("maria", "sebas"):
            user = User.objects.get(username=username)
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.is_staff)
            self.assertFalse(self.client.login(username=username, password="123456789"))

    def test_accounts_seeded_with_the_old_default_password_are_repaired(self):
        from django.core.management import call_command

        old = User.objects.create_user("sebas", password="123456789", is_staff=True)
        call_command("seed_events", verbosity=0, stdout=open(os.devnull, "w"))
        old.refresh_from_db()
        self.assertFalse(old.has_usable_password())
        self.assertFalse(old.is_staff)

    def test_an_organizer_who_changed_the_password_is_left_alone(self):
        from django.core.management import call_command

        own = User.objects.create_user("maria", password="Her-own-pass-2468", is_staff=True)
        call_command("seed_events", verbosity=0, stdout=open(os.devnull, "w"))
        own.refresh_from_db()
        self.assertTrue(own.check_password("Her-own-pass-2468"))
        self.assertTrue(own.is_staff)
