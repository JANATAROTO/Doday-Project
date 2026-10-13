from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from events.models import Category, Event
from navigation.models import Accommodation
from navigation.services import estimate_transit

User = get_user_model()


class AccommodationModelTests(TestCase):
    def test_str_representation(self):
        user = User.objects.create_user(username="traveler", password="pw12345")
        accommodation = Accommodation.objects.create(
            user=user, address="Hotel Central", latitude=6.244, longitude=-75.581
        )
        self.assertEqual(str(accommodation), "traveler - Hotel Central")


from unittest.mock import MagicMock, patch
from django.test import override_settings

class EstimateTransitTests(TestCase):
    def test_returns_none_without_api_key(self):
        # settings.ORS_API_KEY is empty by default in tests/dev.
        result = estimate_transit(6.244, -75.581, 6.25, -75.56)
        self.assertIsNone(result)

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_openrouteservice_success_calculates_distance_and_duration(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "summary": {
                            "distance": 5324.4,  # 5.3 km
                            "duration": 720.0,   # 12 min
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        result = estimate_transit(6.244, -75.581, 6.25, -75.56)
        self.assertEqual(result, (5.3, 12))

        # Verify ORS coordinate order rule: strictly [longitude, latitude]
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["start"], "-75.581,6.244")
        self.assertEqual(kwargs["params"]["end"], "-75.56,6.25")

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_openrouteservice_error_returns_none_silently(self, mock_get):
        mock_get.side_effect = Exception("API error or timeout")
        result = estimate_transit(6.244, -75.581, 6.25, -75.56)
        self.assertIsNone(result)


from django.test import override_settings as _override_settings  # noqa: E402


class EventMapViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Music")
        self.event_with_coords = Event.objects.create(
            title="Concierto en el parque",
            description="desc",
            date_time="2026-10-01T20:00:00Z",
            location="Parque Lleras",
            latitude=6.244,
            longitude=-75.581,
            category=self.category,
            is_free=True,
        )
        self.event_without_coords = Event.objects.create(
            title="Feria sin coordenadas",
            description="desc",
            date_time="2026-10-02T10:00:00Z",
            location="Por definir",
            category=self.category,
            is_free=False,
            price=20000,
        )

    def test_map_page_loads(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertEqual(response.status_code, 200)

    @_override_settings(GOOGLE_MAPS_API_KEY="")
    def test_shows_setup_message_without_api_key(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertContains(response, "GOOGLE_MAPS_API_KEY")
        self.assertNotContains(response, 'id="map"')

    @_override_settings(GOOGLE_MAPS_API_KEY="fake-js-key")
    def test_renders_map_and_markers_with_api_key(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertContains(response, 'id="map"')
        self.assertContains(response, "fake-js-key")

        markers = response.context["markers"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["title"], "Concierto en el parque")
        self.assertEqual(markers[0]["lat"], 6.244)

    def test_counts_events_without_coordinates(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertEqual(response.context["events_without_coords"], 1)

    def test_counts_event_missing_only_one_coordinate(self):
        # Latitude without longitude can't be plotted either.
        Event.objects.create(
            title="Solo latitud",
            description="desc",
            date_time="2026-10-03T10:00:00Z",
            location="Parcial",
            latitude=6.25,
            category=self.category,
        )
        response = self.client.get(reverse("navigation:event_map"))
        self.assertEqual(response.context["events_without_coords"], 2)

    @_override_settings(GOOGLE_MAPS_API_KEY="fake-js-key")
    def test_marker_data_is_script_safe(self):
        Event.objects.create(
            title="</script><script>alert(1)</script>",
            description="desc",
            date_time="2026-10-04T10:00:00Z",
            location="XSS",
            latitude=6.3,
            longitude=-75.6,
            category=self.category,
        )
        response = self.client.get(reverse("navigation:event_map"))
        html = response.content.decode()
        # The raw closing tag must never appear inside the page's JSON blob.
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertIn("\\u003C/script\\u003E", html)


class EventMapFilterTests(TestCase):
    """REQ-09: the map must plot only the events matching the search filters."""

    def setUp(self):
        self.music = Category.objects.create(name="Music")
        self.food = Category.objects.create(name="Food")
        self.concert = Event.objects.create(
            title="Concierto en el parque",
            description="rock",
            date_time="2026-10-01T20:00:00Z",
            location="Parque Lleras",
            latitude=6.244,
            longitude=-75.581,
            category=self.music,
            is_free=True,
        )
        self.fair = Event.objects.create(
            title="Feria gastronomica",
            description="comida",
            date_time="2026-10-20T10:00:00Z",
            location="Plaza Mayor",
            latitude=6.25,
            longitude=-75.57,
            category=self.food,
            is_free=False,
            price=15000,
        )
        self.no_coords = Event.objects.create(
            title="Concierto sin coordenadas",
            description="rock",
            date_time="2026-10-02T10:00:00Z",
            location="Por definir",
            category=self.music,
            is_free=True,
        )

    def _titles(self, response):
        return sorted(m["title"] for m in response.context["markers"])

    def test_no_filters_shows_all_events_with_coordinates(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertEqual(len(response.context["markers"]), 2)

    def test_keyword_filter(self):
        response = self.client.get(reverse("navigation:event_map"), {"q": "gastronomica"})
        self.assertEqual(self._titles(response), ["Feria gastronomica"])

    def test_category_filter(self):
        response = self.client.get(reverse("navigation:event_map"), {"category": [self.music.pk]})
        self.assertEqual(self._titles(response), ["Concierto en el parque"])

    def test_free_only_filter(self):
        response = self.client.get(reverse("navigation:event_map"), {"free_only": "on"})
        self.assertEqual(self._titles(response), ["Concierto en el parque"])

    def test_date_range_filter(self):
        response = self.client.get(
            reverse("navigation:event_map"),
            {"date_from": "2026-10-15", "date_to": "2026-10-31"},
        )
        self.assertEqual(self._titles(response), ["Feria gastronomica"])

    def test_without_coords_count_respects_filters(self):
        response = self.client.get(reverse("navigation:event_map"), {"q": "sin coordenadas"})
        self.assertEqual(response.context["events_without_coords"], 1)
        self.assertEqual(response.context["markers"], [])
        # Filter that excludes the coordinate-less event -> nothing to warn about.
        response = self.client.get(reverse("navigation:event_map"), {"q": "gastronomica"})
        self.assertEqual(response.context["events_without_coords"], 0)

    def test_invalid_form_does_not_crash(self):
        response = self.client.get(
            reverse("navigation:event_map"),
            {"date_from": "2026-10-31", "date_to": "2026-10-01"},
        )
        self.assertEqual(response.status_code, 200)


class EventMapTimezoneTests(TestCase):
    def test_marker_date_uses_local_timezone(self):
        # 11:00 UTC is 06:00 in America/Bogota (UTC-5), the project's TIME_ZONE.
        Event.objects.create(
            title="EDC",
            description="desc",
            date_time="2026-10-13T11:00:00Z",
            location="Atanasio Girardot",
            latitude=6.2565,
            longitude=-75.5905,
        )
        response = self.client.get(reverse("navigation:event_map"))
        self.assertIn("13 Oct 2026 — 06:00", response.context["markers"][0]["date"])
