"""REQ-13: management command to run the external API sync.

Meant to be run periodically (cron, django-crontab, etc.) — see README for
the chosen scheduling mechanism — but can also be run manually the same way
seed_events is:

    python manage.py sync_external_events
    python manage.py sync_external_events --city "Bogotá"
"""
from django.core.management.base import BaseCommand

from events.services.ticketmaster_sync import sync_ticketmaster_events


class Command(BaseCommand):
    help = "REQ-13: sync events from external APIs (Ticketmaster) into the local DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--city",
            default="Medellín",
            help="City to query the external API for (default: Medellín).",
        )

    def handle(self, *args, **options):
        city = options["city"]
        self.stdout.write(f"Syncing Ticketmaster events for city={city}...")

        created, updated = sync_ticketmaster_events(city=city)

        self.stdout.write(
            self.style.SUCCESS(
                f"Ticketmaster sync complete: {created} created, {updated} updated."
            )
        )
