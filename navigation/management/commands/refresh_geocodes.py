"""Refresh accommodation coordinates that came from Google more than a month ago.

Google lets an application keep the latitude/longitude returned by the
Geocoding API for 30 days at most; after that they must be requested again
(or deleted). Run this once a day from a scheduler:

    python manage.py refresh_geocodes

Coordinates the user typed by hand (geocoded_at is empty) are theirs, not
Google's, and are never touched.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from navigation.models import Accommodation
from navigation.services import geocode_address

# One day of slack, so a run that is skipped once still stays inside 30 days.
MAX_AGE_DAYS = 29


class Command(BaseCommand):
    help = "Re-geocode accommodations whose Google coordinates are about to turn 30 days old."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=MAX_AGE_DAYS,
            help=f"Refresh coordinates older than this many days (default {MAX_AGE_DAYS}).",
        )
        parser.add_argument(
            "--limit", type=int, default=500,
            help="Most addresses to refresh in one run; each one is a billable request (default 500).",
        )

    def handle(self, *args, days, limit, **options):
        cutoff = timezone.now() - timedelta(days=days)
        stale = Accommodation.objects.filter(geocoded_at__lt=cutoff).order_by("geocoded_at")[:limit]

        refreshed = failed = 0
        for accommodation in stale:
            coordinates = geocode_address(accommodation.address)
            if not coordinates:
                # Keep the row and try again on the next run: the usual reason
                # is a missing key or a network problem, not a bad address.
                failed += 1
                continue
            accommodation.latitude, accommodation.longitude = coordinates
            accommodation.geocoded_at = timezone.now()
            accommodation.save(update_fields=["latitude", "longitude", "geocoded_at"])
            refreshed += 1

        self.stdout.write(f"Refreshed {refreshed} accommodation(s); {failed} could not be refreshed.")
        if failed:
            self.stderr.write(
                "Some addresses could not be refreshed. Run `python manage.py check_integrations` "
                "to see whether the Google server key is working."
            )
