from django.contrib.auth import get_user_model
from django.test import TestCase

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
