"""Import of real events from Ticketmaster (events/services/ticketmaster_sync.py)."""
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from events.models import Event
from events.services import ticketmaster_sync
from events.services.ticketmaster_sync import geohash, sync_ticketmaster_events


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _raw_event(event_id="Z698xZC2Z17a7AP", **overrides):
    """A record shaped like the Discovery API's, trimmed to what the import reads."""
    event = {
        "id": event_id,
        "name": "Feid en Medellín",
        "url": "https://www.ticketmaster.co/event/feid",
        "info": "Apertura de puertas a las 6:00 p. m.",
        "dates": {"start": {"dateTime": "2026-12-05T01:00:00Z"}, "status": {"code": "onsale"}},
        "classifications": [{"segment": {"name": "Music"}}],
        "priceRanges": [{"currency": "COP", "min": 180000.0, "max": 650000.0}],
        "_embedded": {"venues": [{
            "name": "Estadio Atanasio Girardot",
            "city": {"name": "Medellín"},
            "location": {"latitude": "6.256854", "longitude": "-75.590313"},
        }]},
    }
    event.update(overrides)
    return event


def _page(events, total=None):
    return _Response({"_embedded": {"events": events}, "page": {"totalElements": len(events) if total is None else total}})


class GeohashTests(TestCase):
    def test_known_values(self):
        # Reference values from the geohash specification's own examples.
        self.assertEqual(geohash(57.64911, 10.40744, precision=11), "u4pruydqqvj")
        self.assertEqual(geohash(42.6, -5.6, precision=5), "ezs42")

    def test_medellin_decodes_back_to_medellin(self):
        latitude, longitude = self._decode(geohash(6.25, -75.575))
        self.assertAlmostEqual(latitude, 6.25, places=4)
        self.assertAlmostEqual(longitude, -75.575, places=4)

    @staticmethod
    def _decode(code):
        """Centre of the cell a geohash names (the standard decoding)."""
        lat, lon, use_longitude = [-90.0, 90.0], [-180.0, 180.0], True
        for character in code:
            value = "0123456789bcdefghjkmnpqrstuvwxyz".index(character)
            for shift in range(4, -1, -1):
                interval = lon if use_longitude else lat
                middle = (interval[0] + interval[1]) / 2
                if (value >> shift) & 1:
                    interval[0] = middle
                else:
                    interval[1] = middle
                use_longitude = not use_longitude
        return (lat[0] + lat[1]) / 2, (lon[0] + lon[1]) / 2


@override_settings(TICKETMASTER_API_KEY="tm-key", ACCOMMODATION_ALLOWED_BOUNDS=(6.10, 6.40, -75.70, -75.45))
class TicketmasterSyncTests(TestCase):
    @patch("events.services.ticketmaster_sync.requests.get")
    def test_imports_an_event_with_everything_the_site_shows(self, mock_get):
        mock_get.return_value = _page([_raw_event()])

        result = sync_ticketmaster_events()

        self.assertEqual((result.created, result.updated, result.skipped, result.problem), (1, 0, 0, ""))
        event = Event.objects.get(external_source="ticketmaster", external_id="Z698xZC2Z17a7AP")
        self.assertEqual(event.title, "Feid en Medellín")
        self.assertEqual(event.location, "Estadio Atanasio Girardot, Medellín")
        self.assertEqual(event.date_time, datetime(2026, 12, 5, 1, 0, tzinfo=dt_timezone.utc))
        self.assertEqual((event.latitude, event.longitude), (Decimal("6.256854"), Decimal("-75.590313")))
        self.assertEqual(event.price, Decimal("180000"))
        self.assertFalse(event.is_free)
        self.assertEqual(event.ticket_url, "https://www.ticketmaster.co/event/feid")
        self.assertEqual(event.category.name_es, "Música")
        # Imported events are real listings: published without moderation.
        self.assertIn(event, Event.objects.published())

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_search_is_by_location_in_every_language_and_only_upcoming(self, mock_get):
        mock_get.return_value = _page([])

        sync_ticketmaster_events()

        params = mock_get.call_args.kwargs["params"]
        # The API's default locale (English) hides Spanish-only records.
        self.assertEqual(params["locale"], "*")
        self.assertEqual(params["geoPoint"], geohash(6.25, -75.575))
        self.assertEqual((params["radius"], params["unit"]), (40, "km"))
        self.assertEqual(params["sort"], "date,asc")
        self.assertRegex(params["startDateTime"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertNotIn("city", params)

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_city_name_search_when_asked(self, mock_get):
        mock_get.return_value = _page([])
        sync_ticketmaster_events(city="Bogotá")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["city"], "Bogotá")
        self.assertNotIn("geoPoint", params)

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_running_twice_updates_instead_of_duplicating(self, mock_get):
        mock_get.return_value = _page([_raw_event()])
        sync_ticketmaster_events()
        mock_get.return_value = _page([_raw_event(name="Feid en Medellín (nueva fecha)")])

        result = sync_ticketmaster_events()

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().title, "Feid en Medellín (nueva fecha)")

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_skips_events_without_a_date_and_cancelled_ones(self, mock_get):
        mock_get.return_value = _page([
            _raw_event("a", dates={"start": {"localDate": "2026-12-05", "dateTBD": True}}),
            _raw_event("b", dates={"start": {"dateTime": "2026-12-05T01:00:00Z"}, "status": {"code": "cancelled"}}),
            _raw_event("c"),
        ])
        result = sync_ticketmaster_events()
        self.assertEqual((result.created, result.skipped), (1, 2))
        self.assertEqual(list(Event.objects.values_list("external_id", flat=True)), ["c"])

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_sparse_record_still_imports(self, mock_get):
        mock_get.return_value = _page([{
            "id": "bare", "name": "Evento sin detalles",
            "dates": {"start": {"dateTime": "2026-12-05T01:00:00Z"}},
        }])
        sync_ticketmaster_events()
        event = Event.objects.get(external_id="bare")
        self.assertEqual(event.location, "Medellín")
        self.assertIsNone(event.latitude)
        self.assertIsNone(event.price)
        self.assertFalse(event.is_free)  # unknown price is not "free"
        self.assertEqual(event.category.name, "General")

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_price_in_another_currency_is_not_shown_as_pesos(self, mock_get):
        mock_get.return_value = _page([_raw_event(priceRanges=[{"currency": "USD", "min": 45.0}])])
        sync_ticketmaster_events()
        self.assertIsNone(Event.objects.get().price)

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_follows_pages_up_to_the_requested_size(self, mock_get):
        first = [_raw_event(f"p0-{i}") for i in range(100)]
        second = [_raw_event(f"p1-{i}") for i in range(100)]
        mock_get.side_effect = [_page(first, total=250), _page(second, total=250)]

        result = sync_ticketmaster_events(size=150)

        self.assertEqual(result.created, 150)
        self.assertEqual(result.available, 250)
        self.assertEqual([call.kwargs["params"]["page"] for call in mock_get.call_args_list], [0, 1])

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_rejected_key_is_explained_and_nothing_changes(self, mock_get):
        mock_get.return_value = _Response({"fault": {"faultstring": "Invalid ApiKey"}}, status_code=401)
        with self.assertLogs("events.services.ticketmaster_sync", level="WARNING") as logs:
            result = sync_ticketmaster_events()
        self.assertIn("Invalid ApiKey", result.problem)
        self.assertIn("Consumer Key", result.problem)
        self.assertNotIn("tm-key", result.problem + logs.output[0])
        self.assertEqual(Event.objects.count(), 0)

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_network_failure_is_reported_not_raised(self, mock_get):
        import requests
        mock_get.side_effect = requests.ConnectionError("down")
        with self.assertLogs("events.services.ticketmaster_sync", level="WARNING"):
            result = sync_ticketmaster_events()
        self.assertIn("Could not reach Ticketmaster", result.problem)

    @override_settings(TICKETMASTER_API_KEY="")
    @patch("events.services.ticketmaster_sync.requests.get")
    def test_without_a_key_nothing_is_requested(self, mock_get):
        result = sync_ticketmaster_events()
        self.assertIn("TICKETMASTER_API_KEY is not set", result.problem)
        mock_get.assert_not_called()


@override_settings(TICKETMASTER_API_KEY="tm-key")
class SyncCommandTests(TestCase):
    def _run(self, name="sync_external_events", *args):
        out = StringIO()
        call_command(name, *args, stdout=out, no_color=True)
        return out.getvalue()

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_reports_what_was_imported(self, mock_get):
        mock_get.return_value = _page([_raw_event()], total=37)
        output = self._run()
        self.assertIn("Ticketmaster has 37 upcoming event(s)", output)
        self.assertIn("Imported: 1 new, 0 updated, 0 skipped", output)

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_says_so_when_ticketmaster_has_nothing_here(self, mock_get):
        mock_get.return_value = _page([])
        self.assertIn("nothing listed here right now", self._run())

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_a_problem_fails_the_command_so_a_scheduled_run_shows_red(self, mock_get):
        mock_get.return_value = _Response({"fault": {"faultstring": "Invalid ApiKey"}}, status_code=401)
        with self.assertLogs("events.services.ticketmaster_sync", level="WARNING"):
            with self.assertRaisesMessage(CommandError, "Invalid ApiKey"):
                self._run()

    @patch("events.services.ticketmaster_sync.requests.get")
    def test_old_command_name_still_works(self, mock_get):
        mock_get.return_value = _page([_raw_event()])
        self.assertIn("Imported: 1 new", self._run("sync_ticketmaster"))


class ProbeTests(TestCase):
    @override_settings(TICKETMASTER_API_KEY="tm-key")
    @patch("events.services.ticketmaster_sync.requests.get")
    def test_reports_how_many_events_there_are(self, mock_get):
        mock_get.return_value = _page([_raw_event()], total=37)
        works, message = ticketmaster_sync.probe()
        self.assertTrue(works)
        self.assertIn("37 upcoming event(s)", message)
        self.assertEqual(mock_get.call_args.kwargs["params"]["size"], 1)

    @override_settings(TICKETMASTER_API_KEY="")
    def test_no_key(self):
        self.assertEqual(ticketmaster_sync.probe(), (False, "TICKETMASTER_API_KEY is not set."))
