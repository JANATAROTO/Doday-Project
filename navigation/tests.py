from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from navigation.forms import AccommodationForm
from navigation.models import Accommodation
from navigation.services import estimate_transit, geocode_address, haversine_km

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


def _geocode_response(longitude, latitude):
    """Minimal Pelias GeoJSON payload — coordinates are [lon, lat]."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "features": [{"geometry": {"coordinates": [longitude, latitude]}}]
    }
    return mock_response


class GeocodeAddressTests(TestCase):
    """REQ-01: resolving an address into coordinates."""

    def test_returns_none_without_api_key(self):
        # settings.ORS_API_KEY is empty by default in tests/dev.
        self.assertIsNone(geocode_address("Parque Lleras, Medellín"))

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_returns_latitude_longitude_in_that_order(self, mock_get):
        mock_get.return_value = _geocode_response(-75.568000, 6.208900)

        result = geocode_address("Parque Lleras, Medellín")

        # Pelias answers [lon, lat]; we hand back (lat, lon).
        self.assertEqual(result, (Decimal("6.208900"), Decimal("-75.568000")))

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_query_is_biased_to_colombia_and_medellin(self, mock_get):
        mock_get.return_value = _geocode_response(-75.568000, 6.208900)

        geocode_address("Carrera 43A #7-50")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["boundary.country"], "CO")
        self.assertEqual(kwargs["params"]["focus.point.lat"], "6.2442")
        self.assertEqual(kwargs["params"]["focus.point.lon"], "-75.5812")

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_unresolvable_address_returns_none(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"features": []}
        mock_get.return_value = mock_response

        self.assertIsNone(geocode_address("asdfghjkl"))

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_api_error_returns_none_silently(self, mock_get):
        mock_get.side_effect = Exception("API error or timeout")
        self.assertIsNone(geocode_address("Parque Lleras, Medellín"))

    @override_settings(ORS_API_KEY="test_ors_key")
    @patch("navigation.services.requests.get")
    def test_blank_address_does_not_call_the_api(self, mock_get):
        self.assertIsNone(geocode_address("   "))
        mock_get.assert_not_called()


class AccommodationEntryPointTests(TestCase):
    """REQ-01: a saved accommodation must stay reachable to edit.

    The link on the event detail page only shows while the user has no
    accommodation yet, so without the header link there would be no way back
    to the form once one is saved.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="traveler", password="pw12345")

    def test_header_links_to_the_form_when_logged_in(self):
        self.client.login(username="traveler", password="pw12345")
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, reverse("navigation:accommodation_edit"))

    def test_header_link_still_there_after_saving_an_accommodation(self):
        Accommodation.objects.create(
            user=self.user,
            address="Parque Lleras, Medellín",
            latitude=Decimal("6.208900"),
            longitude=Decimal("-75.568000"),
        )
        self.client.login(username="traveler", password="pw12345")
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, reverse("navigation:accommodation_edit"))

    def test_anonymous_users_do_not_see_the_link(self):
        response = self.client.get(reverse("events:event_list"))
        self.assertNotContains(response, reverse("navigation:accommodation_edit"))


class AccommodationFormTests(TestCase):
    """REQ-01: the form fills coordinates in from the address."""

    @patch("navigation.forms.geocode_address")
    def test_coordinates_are_geocoded_from_the_address(self, mock_geocode):
        mock_geocode.return_value = (Decimal("6.208900"), Decimal("-75.568000"))

        form = AccommodationForm(data={"address": "Parque Lleras, Medellín"})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["latitude"], Decimal("6.208900"))
        self.assertEqual(form.cleaned_data["longitude"], Decimal("-75.568000"))

    @patch("navigation.forms.geocode_address")
    def test_manual_coordinates_are_kept_and_skip_the_lookup(self, mock_geocode):
        form = AccommodationForm(
            data={
                "address": "Somewhere with no street number",
                "latitude": "6.100000",
                "longitude": "-75.400000",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["latitude"], Decimal("6.100000"))
        mock_geocode.assert_not_called()

    @patch("navigation.forms.geocode_address")
    def test_failed_lookup_asks_for_manual_coordinates(self, mock_geocode):
        mock_geocode.return_value = None

        form = AccommodationForm(data={"address": "asdfghjkl"})

        self.assertFalse(form.is_valid())
        self.assertIn("manually", str(form.errors))

    def test_coordinate_fields_are_hidden_by_default(self):
        form = AccommodationForm()

        self.assertFalse(form.show_coordinate_fields)
        for name in ("latitude", "longitude"):
            self.assertTrue(form.fields[name].widget.is_hidden)
        # No visible label for them on a fresh form.
        self.assertNotIn("Latitude:", form.as_p())

    @patch("navigation.forms.geocode_address")
    def test_coordinate_fields_appear_after_a_failed_lookup(self, mock_geocode):
        mock_geocode.return_value = None

        form = AccommodationForm(data={"address": "asdfghjkl"})
        self.assertFalse(form.is_valid())

        self.assertTrue(form.show_coordinate_fields)
        for name in ("latitude", "longitude"):
            self.assertFalse(form.fields[name].widget.is_hidden)
        self.assertIn("Latitude:", form.as_p())

    @patch("navigation.forms.geocode_address")
    def test_changed_address_that_cannot_be_resolved_is_rejected(self, mock_geocode):
        """The old coordinates belong to the old address — never save them silently."""
        mock_geocode.return_value = None
        user = User.objects.create_user(username="nomad", password="pw12345")
        accommodation = Accommodation.objects.create(
            user=user,
            address="Parque Lleras, Medellín",
            latitude=Decimal("6.208900"),
            longitude=Decimal("-75.568000"),
        )

        form = AccommodationForm(
            data={
                "address": "Somewhere unresolvable",
                "latitude": "6.208900",
                "longitude": "-75.568000",
            },
            instance=accommodation,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.show_coordinate_fields)

    @patch("navigation.forms.geocode_address")
    def test_changing_the_address_refreshes_stale_coordinates(self, mock_geocode):
        mock_geocode.return_value = (Decimal("6.270548"), Decimal("-75.563529"))
        user = User.objects.create_user(username="traveler", password="pw12345")
        accommodation = Accommodation.objects.create(
            user=user,
            address="Parque Lleras, Medellín",
            latitude=Decimal("6.208900"),
            longitude=Decimal("-75.568000"),
        )

        form = AccommodationForm(
            data={
                "address": "Jardín Botánico, Medellín",
                "latitude": "6.208900",
                "longitude": "-75.568000",
            },
            instance=accommodation,
        )

        self.assertTrue(form.is_valid(), form.errors)
        # The old coordinates belonged to the previous address.
        self.assertEqual(form.cleaned_data["latitude"], Decimal("6.270548"))


class HaversineTests(TestCase):
    """Distance helper behind REQ-08 (radius) and REQ-14 (proximity sorting).

    Checked against known straight-line distances so a sign error or a wrong
    Earth radius cannot hide: both would still order events plausibly, which
    is all the REQ-08/REQ-14 tests would notice.
    """

    # Parque Lleras — the origin the catalogue tests measure from.
    LLERAS = (Decimal("6.208900"), Decimal("-75.568000"))
    TEATRO_METROPOLITANO = (Decimal("6.243177"), Decimal("-75.577508"))
    JARDIN_BOTANICO = (Decimal("6.270548"), Decimal("-75.563529"))

    def test_distance_to_itself_is_zero(self):
        self.assertEqual(haversine_km(*self.LLERAS, *self.LLERAS), 0.0)

    def test_known_distance_within_medellin(self):
        """Lleras → Teatro Metropolitano is ~3.9 km in a straight line."""
        distance = haversine_km(*self.LLERAS, *self.TEATRO_METROPOLITANO)
        self.assertAlmostEqual(distance, 3.9, delta=0.2)

    def test_second_known_distance_within_medellin(self):
        """Lleras → Jardín Botánico is ~6.9 km in a straight line."""
        distance = haversine_km(*self.LLERAS, *self.JARDIN_BOTANICO)
        self.assertAlmostEqual(distance, 6.9, delta=0.2)

    def test_distance_is_symmetric(self):
        there = haversine_km(*self.LLERAS, *self.JARDIN_BOTANICO)
        back = haversine_km(*self.JARDIN_BOTANICO, *self.LLERAS)
        self.assertAlmostEqual(there, back, places=9)

    def test_accepts_floats_as_well_as_decimals(self):
        """Event/Accommodation store Decimal, but callers may pass floats."""
        as_decimal = haversine_km(*self.LLERAS, *self.TEATRO_METROPOLITANO)
        as_float = haversine_km(6.208900, -75.568000, 6.243177, -75.577508)
        self.assertAlmostEqual(as_decimal, as_float, places=9)

    def test_one_degree_of_latitude_is_about_111_km(self):
        """Guards the Earth radius: a wrong constant scales every distance."""
        self.assertAlmostEqual(haversine_km(0, 0, 1, 0), 111.19, delta=0.1)

    def test_longitude_spacing_shrinks_away_from_the_equator(self):
        """Guards the cos(latitude) term, which a flat approximation drops."""
        at_equator = haversine_km(0, 0, 0, 1)
        at_medellin = haversine_km(6.24, 0, 6.24, 1)
        self.assertLess(at_medellin, at_equator)
        self.assertAlmostEqual(at_medellin, at_equator * 0.9941, delta=0.1)

    def test_distance_grows_with_separation(self):
        near = haversine_km(*self.LLERAS, *self.TEATRO_METROPOLITANO)
        far = haversine_km(*self.LLERAS, *self.JARDIN_BOTANICO)
        self.assertLess(near, far)
