"""Management command: sync_ticketmaster

REQ-13 — pulls events from the Ticketmaster Discovery API and upserts them
into the local Event table.  Safe to run periodically (cron / celery beat)
because update_or_create is keyed on (external_source, external_id).

Usage:
    python manage.py sync_ticketmaster
    python manage.py sync_ticketmaster --city "Bogotá" --size 100
"""
from django.core.management.base import BaseCommand

from events.services.ticketmaster_sync import sync_ticketmaster_events


class Command(BaseCommand):
    help = "REQ-13: Sync events from the Ticketmaster Discovery API into the local DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--city",
            default="Medellín",
            help="City to query (default: Medellín).",
        )
        parser.add_argument(
            "--size",
            type=int,
            default=50,
            help="Maximum number of events to fetch per run (default: 50).",
        )

    def handle(self, *args, **options):
        city = options["city"]
        size = options["size"]

        self.stdout.write(f"Syncing Ticketmaster events for '{city}' (size={size})…")

        created, updated = sync_ticketmaster_events(city=city, size=size)

        if created == 0 and updated == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No events returned — check TICKETMASTER_API_KEY or city name."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done: {created} created, {updated} updated."
                )
            )
