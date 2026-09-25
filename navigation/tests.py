import json

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

        markers = json.loads(response.context["markers_json"])
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["title"], "Concierto en el parque")
        self.assertEqual(markers[0]["lat"], 6.244)

    def test_counts_events_without_coordinates(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertEqual(response.context["events_without_coords"], 1)
