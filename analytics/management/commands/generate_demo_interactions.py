"""REQ-30: fill the analytics dashboard with DEMO data for presentations.

The numbers are simulated, not real visitor activity, so use it only on a
demo database:  python manage.py generate_demo_interactions --days 30
`--clear` removes every recorded interaction first.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import EventInteraction
from events.models import Event


class Command(BaseCommand):
    help = "Generate simulated event interactions (DEMO data) for the analytics dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--views", type=int, default=400, help="Approximate number of views.")
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        events = list(Event.objects.published())
        if not events:
            self.stdout.write(self.style.WARNING("No published events: nothing to simulate."))
            return
        if options["clear"]:
            EventInteraction.objects.all().delete()

        # Some events are naturally more popular than others.
        popularity = {event.pk: rng.uniform(0.3, 3.0) for event in events}
        now = timezone.now()
        created = []
        for _ in range(options["views"]):
            event = rng.choices(events, weights=[popularity[e.pk] for e in events])[0]
            moment = now - timedelta(days=rng.uniform(0, options["days"]))
            # More activity on Thursdays to Saturdays, when people plan outings.
            if moment.isoweekday() in (4, 5, 6) or rng.random() < 0.55:
                created.append(EventInteraction(event=event, kind=EventInteraction.Kind.VIEW))
                created[-1]._moment = moment
                if rng.random() < 0.18:
                    created.append(EventInteraction(event=event, kind=EventInteraction.Kind.FAVORITE))
                    created[-1]._moment = moment
                if event.ticket_url and rng.random() < 0.22:
                    created.append(EventInteraction(event=event, kind=EventInteraction.Kind.TICKET_CLICK))
                    created[-1]._moment = moment

        objects = EventInteraction.objects.bulk_create(created)
        # auto_now_add ignores the value on create, so set the dates afterwards.
        for obj, source in zip(objects, created):
            obj.created_at = source._moment
        EventInteraction.objects.bulk_update(objects, ["created_at"])
        self.stdout.write(self.style.SUCCESS(f"Created {len(objects)} DEMO interactions over {options['days']} days."))
