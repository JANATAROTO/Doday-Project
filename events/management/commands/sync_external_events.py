"""Import real events from external sources (today: Ticketmaster).

    python manage.py sync_external_events
    python manage.py sync_external_events --size 500
    python manage.py sync_external_events --city "Bogotá"

By default it brings the upcoming events around the service area (Medellín
and the valley). Safe to run as often as wanted: events are updated in place,
never duplicated. Needs TICKETMASTER_API_KEY.
"""
from django.core.management.base import BaseCommand, CommandError

from events.services.ticketmaster_sync import RADIUS_KM, sync_ticketmaster_events


class Command(BaseCommand):
    help = "Import upcoming events from Ticketmaster into the catalogue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--city", default=None,
            help="Search by city name instead of around the service area (e.g. \"Bogotá\").",
        )
        parser.add_argument(
            "--size", type=int, default=200,
            help="Most events to bring in one run (default 200, at most 1000).",
        )

    def handle(self, *args, city, size, **options):
        where = f'city "{city}"' if city else f"{RADIUS_KM} km around the service area"
        self.stdout.write(f"Asking Ticketmaster for upcoming events ({where})...")

        result = sync_ticketmaster_events(city=city, size=size)

        if result.problem:
            raise CommandError(result.problem)

        self.stdout.write(f"Ticketmaster has {result.available} upcoming event(s) for this search.")
        self.stdout.write(self.style.SUCCESS(
            f"Imported: {result.created} new, {result.updated} updated, {result.skipped} skipped "
            "(no confirmed date, or cancelled)."
        ))
        if result.available == 0:
            self.stdout.write(self.style.WARNING(
                "Ticketmaster has nothing listed here right now. The key works; there is simply "
                "no event on sale in this area through this API today."
            ))
