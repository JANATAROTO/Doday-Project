"""Tell, in plain words, which external services this installation can use.

    python manage.py check_integrations

Run it after filling in `.env` (or the server's environment variables) to see
whether each key is in place and actually accepted. It makes one real request
to the Geocoding API and one to the Routes API (two billable calls, far inside
the monthly free allowance); pass --offline to only look at the configuration.

Nothing secret is printed: keys are shown as "set" or "missing".
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from navigation import services

# Parque Lleras -> Plaza Botero, two well-known points inside the service area.
SAMPLE_ADDRESS = "Parque Lleras, Medellín"
SAMPLE_ROUTE = (6.2089, -75.5680, 6.2524, -75.5687)


class Command(BaseCommand):
    help = "Report which external services (database, Google Maps, email...) are configured and working."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline", action="store_true",
            help="Only inspect the configuration; make no request to Google.",
        )

    def handle(self, *args, offline, **options):
        self.problems = 0

        self._database()
        self._cache()
        self._browser_key()
        self._server_key(offline)
        self._optional("Ticketmaster (external event import)", settings.TICKETMASTER_API_KEY,
                       "TICKETMASTER_API_KEY is not set: the import command does nothing. Optional.")
        self._email()
        self._optional("Sentry (error reports)", getattr(settings, "SENTRY_DSN", ""),
                       "SENTRY_DSN is not set: errors only appear in the server log. Optional.")
        self._security()

        self.stdout.write("")
        if self.problems:
            self.stdout.write(self.style.WARNING(f"{self.problems} item(s) need attention (marked with !)."))
        else:
            self.stdout.write(self.style.SUCCESS("Everything that is configured is working."))

    # -- output helpers ------------------------------------------------------

    def _ok(self, label, detail):
        self.stdout.write(self.style.SUCCESS(f"  ok  {label}: {detail}"))

    def _info(self, label, detail):
        self.stdout.write(f"  --  {label}: {detail}")

    def _problem(self, label, detail):
        self.problems += 1
        self.stdout.write(self.style.ERROR(f"  !   {label}: {detail}"))

    def _optional(self, label, value, missing):
        if value:
            self._ok(label, "set")
        else:
            self._info(label, missing)

    # -- checks ----------------------------------------------------------------

    def _database(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as error:  # noqa: BLE001 - report whatever went wrong
            self._problem("Database", f"cannot connect ({error.__class__.__name__}). Check DATABASE_URL.")
            return
        if connection.vendor == "postgresql":
            self._ok("Database", "PostgreSQL")
        else:
            self._info("Database", f"{connection.vendor} (fine for development; production should set DATABASE_URL)")

    def _cache(self):
        backend = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
        if backend == "DatabaseCache":
            table = settings.CACHES["default"]["LOCATION"]
            if table in connection.introspection.table_names():
                self._ok("Cache", "database table (shared by all workers)")
            else:
                self._problem("Cache", f"table `{table}` is missing. Run: python manage.py createcachetable")
        else:
            self._info("Cache", "in memory (fine for development)")

    def _browser_key(self):
        if settings.GOOGLE_MAPS_API_KEY:
            self._ok("Google Maps browser key", "set (it can only be tested by opening /map/ in a browser)")
        else:
            self._problem(
                "Google Maps browser key",
                "GOOGLE_MAPS_API_KEY is not set: the map pages show a notice instead of the map.",
            )

    def _server_key(self, offline):
        if not settings.GOOGLE_MAPS_SERVER_KEY:
            self._problem(
                "Google Maps server key",
                "GOOGLE_MAPS_SERVER_KEY is not set: addresses need manual coordinates and no route is shown.",
            )
            return
        if settings.GOOGLE_MAPS_SERVER_KEY == settings.GOOGLE_MAPS_API_KEY:
            self._problem(
                "Google Maps server key",
                "it is the same key as the browser key. Use two keys: the browser key is public and "
                "restricted by website, which Google rejects for server requests.",
            )
        if offline:
            self._ok("Google Maps server key", "set (not tested: --offline)")
            return

        if services.geocode_address(SAMPLE_ADDRESS):
            self._ok("Geocoding API", "address lookup works")
        else:
            self._problem(
                "Geocoding API",
                "the test lookup failed; the line above this one says why. Usual causes: the Geocoding API "
                "is not enabled in the Google Cloud project, or the key is restricted by website.",
            )
        if services.estimate_transit(*SAMPLE_ROUTE):
            self._ok("Routes API", "route calculation works")
        else:
            self._problem(
                "Routes API",
                "the test route failed; the line above this one says why. Usual cause: the Routes API "
                "is not enabled in the Google Cloud project or not allowed for this key.",
            )

    def _email(self):
        if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
            self._ok("Email", f"SMTP through {settings.EMAIL_HOST}")
        elif settings.DEBUG:
            self._info("Email", "printed to the console (fine for development)")
        else:
            self._problem(
                "Email",
                "EMAIL_HOST is not set: password-reset emails are only written to the server log, "
                "so nobody can recover an account.",
            )

    def _security(self):
        if settings.DEBUG:
            self._info("Mode", "development (DJANGO_DEBUG=True)")
            return
        self._ok("Mode", "production (DEBUG is off)")
        if not getattr(settings, "SECURE_SSL_REDIRECT", False):
            self._problem("HTTPS", "DJANGO_HTTPS is not True: cookies and logins are not forced over HTTPS.")
        else:
            self._ok("HTTPS", "enforced")
        if not settings.ALLOWED_HOSTS:
            self._problem("Domain", "no host is allowed. Set DJANGO_ALLOWED_HOSTS to the site's domain.")
        else:
            self._ok("Domain", ", ".join(settings.ALLOWED_HOSTS))
