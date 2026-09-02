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


class EstimateTransitTests(TestCase):
    def test_returns_none_without_api_key(self):
        # settings.GOOGLE_MAPS_API_KEY is empty by default in tests/dev.
        result = estimate_transit(6.244, -75.581, 6.25, -75.56)
        self.assertIsNone(result)
