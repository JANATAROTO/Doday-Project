import math
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from events.models import Category, Event
from navigation.forms import AccommodationForm
from navigation.models import Accommodation
from navigation.services import (
    bounding_box,
    decode_polyline,
    distance_km_expression,
    estimate_transit,
    geocode_address,
    get_transit_route,
    haversine_km,
)

User = get_user_model()


class AccommodationModelTests(TestCase):
    def test_str_representation(self):
        user = User.objects.create_user(username="traveler", password="pw12345")
        accommodation = Accommodation.objects.create(
            user=user, address="Hotel Central", latitude=6.244, longitude=-75.581
        )
        self.assertEqual(str(accommodation), "traveler - Hotel Central")


class _Response:
    """Stand-in for requests' response."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


# Google's documented sample: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453).
SAMPLE_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


class PolylineTests(TestCase):
    def test_decodes_googles_documented_example(self):
        self.assertEqual(
            decode_polyline(SAMPLE_POLYLINE),
            [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]],
        )

    def test_empty_and_truncated_input_do_not_fail(self):
        self.assertEqual(decode_polyline(""), [])
        self.assertEqual(decode_polyline(SAMPLE_POLYLINE[:-1])[:2], [[38.5, -120.2], [40.7, -120.95]])


class RouteTests(TestCase):
    """REQ-03: route from the accommodation to an event (Google Routes API)."""

    def test_returns_none_without_a_server_key(self):
        # GOOGLE_MAPS_SERVER_KEY is empty by default in tests and development.
        self.assertIsNone(estimate_transit(6.244, -75.581, 6.25, -75.56))

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key", GOOGLE_MAPS_API_KEY="browser-key")
    @patch("navigation.services.requests.post")
    def test_distance_duration_and_path(self, mock_post):
        mock_post.return_value = _Response({
            "routes": [{
                "distanceMeters": 5324,
                "duration": "720s",
                "polyline": {"encodedPolyline": SAMPLE_POLYLINE},
            }]
        })

        route = get_transit_route(Decimal("6.244000"), Decimal("-75.581000"), 6.25, -75.56)

        self.assertEqual(route["distance_km"], 5.3)
        self.assertEqual(route["duration_minutes"], 12)
        self.assertEqual(route["coordinates"][0], [38.5, -120.2])

        _, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["json"]["origin"]["location"]["latLng"], {"latitude": 6.244, "longitude": -75.581}
        )
        self.assertEqual(
            kwargs["json"]["destination"]["location"]["latLng"], {"latitude": 6.25, "longitude": -75.56}
        )
        # The server key authenticates the call; the browser key must not be used.
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "server-key")
        # Cheapest billing tier: no traffic, only the fields the page shows.
        self.assertEqual(kwargs["json"]["routingPreference"], "TRAFFIC_UNAWARE")
        self.assertEqual(
            kwargs["headers"]["X-Goog-FieldMask"],
            "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline",
        )

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.post")
    def test_estimate_is_distance_and_minutes(self, mock_post):
        mock_post.return_value = _Response({"routes": [{"distanceMeters": 5324, "duration": "720s"}]})
        self.assertEqual(estimate_transit(6.244, -75.581, 6.25, -75.56), (5.3, 12))

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.post")
    def test_no_route_found_returns_none(self, mock_post):
        mock_post.return_value = _Response({})
        with self.assertNoLogs("navigation.services", level="WARNING"):
            self.assertIsNone(get_transit_route(6.244, -75.581, 6.25, -75.56))

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.post")
    def test_rejected_key_returns_none_and_logs_the_reason_without_the_key(self, mock_post):
        mock_post.return_value = _Response(
            {"error": {"code": 403, "message": "Routes API has not been used in project 1 before or it is disabled."}},
            status_code=403,
        )
        with self.assertLogs("navigation.services", level="WARNING") as logs:
            self.assertIsNone(get_transit_route(6.244, -75.581, 6.25, -75.56))
        self.assertIn("Routes API has not been used", logs.output[0])
        self.assertNotIn("server-key", logs.output[0])

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.post")
    def test_network_error_returns_none(self, mock_post):
        mock_post.side_effect = Exception("timeout")
        with self.assertLogs("navigation.services", level="WARNING"):
            self.assertIsNone(estimate_transit(6.244, -75.581, 6.25, -75.56))


def _geocode_response(latitude, longitude):
    return _Response({
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": latitude, "lng": longitude}}}],
    })


class GeocodeAddressTests(TestCase):
    """REQ-01: resolving an address into coordinates (Google Geocoding API)."""

    def test_returns_none_without_a_server_key(self):
        self.assertIsNone(geocode_address("Parque Lleras, Medellín"))

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.get")
    def test_returns_latitude_then_longitude(self, mock_get):
        mock_get.return_value = _geocode_response(6.2089, -75.568)
        self.assertEqual(
            geocode_address("Parque Lleras, Medellín"), (Decimal("6.208900"), Decimal("-75.568000"))
        )

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key", ACCOMMODATION_ALLOWED_BOUNDS=(6.10, 6.40, -75.70, -75.45))
    @patch("navigation.services.requests.get")
    def test_query_is_biased_to_colombia_and_the_service_area(self, mock_get):
        mock_get.return_value = _geocode_response(6.2089, -75.568)

        geocode_address("Carrera 43A #7-50")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["components"], "country:CO")
        # Google expects south,west|north,east.
        self.assertEqual(kwargs["params"]["bounds"], "6.1,-75.7|6.4,-75.45")
        self.assertEqual(kwargs["params"]["key"], "server-key")

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.get")
    def test_unresolvable_address_returns_none(self, mock_get):
        mock_get.return_value = _Response({"status": "ZERO_RESULTS", "results": []})
        with self.assertNoLogs("navigation.services", level="WARNING"):
            self.assertIsNone(geocode_address("asdfghjkl"))

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.get")
    def test_denied_request_logs_googles_explanation(self, mock_get):
        mock_get.return_value = _Response(
            {"status": "REQUEST_DENIED", "error_message": "API keys with referer restrictions cannot be used with this API."}
        )
        with self.assertLogs("navigation.services", level="WARNING") as logs:
            self.assertIsNone(geocode_address("Parque Lleras"))
        self.assertIn("referer restrictions", logs.output[0])

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.get")
    def test_network_error_returns_none(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        with self.assertLogs("navigation.services", level="WARNING"):
            self.assertIsNone(geocode_address("Parque Lleras, Medellín"))

    @override_settings(GOOGLE_MAPS_SERVER_KEY="server-key")
    @patch("navigation.services.requests.get")
    def test_blank_address_does_not_call_the_api(self, mock_get):
        self.assertIsNone(geocode_address("   "))
        mock_get.assert_not_called()


class DistanceInTheDatabaseTests(TestCase):
    """The SQL distance must agree with the Python formula it replaces."""

    ORIGIN = (Decimal("6.208500"), Decimal("-75.567000"))

    def _event(self, title, latitude, longitude):
        return Event.objects.create(
            title=title, description="d", date_time=timezone.now(), location="x",
            latitude=latitude, longitude=longitude,
        )

    def _annotated(self):
        exact, rounded = distance_km_expression(*self.ORIGIN)
        return {e.title: e for e in Event.objects.annotate(exact=exact, shown=rounded)}

    def test_matches_haversine_km(self):
        self._event("near", Decimal("6.244200"), Decimal("-75.581200"))
        self._event("far", Decimal("4.711000"), Decimal("-74.072100"))  # Bogotá
        events = self._annotated()
        for title, (lat, lon) in {"near": (6.2442, -75.5812), "far": (4.711, -74.0721)}.items():
            expected = haversine_km(*self.ORIGIN, lat, lon)
            self.assertAlmostEqual(events[title].exact, expected, places=6)
            self.assertAlmostEqual(events[title].shown, round(expected, 1), places=6)

    def test_same_point_is_zero(self):
        self._event("here", *self.ORIGIN)
        self.assertAlmostEqual(self._annotated()["here"].exact, 0.0, places=6)

    def test_events_without_coordinates_get_no_distance(self):
        # On PostgreSQL a careless formula turns NULL into ~20,000 km here.
        self._event("nowhere", None, None)
        event = self._annotated()["nowhere"]
        self.assertIsNone(event.exact)
        self.assertIsNone(event.shown)

    def test_bounding_box_never_excludes_a_point_inside_the_radius(self):
        # Walk the edge of the circle: every point the exact formula accepts
        # must also pass the cheap rectangle filter that runs first.
        for origin in [self.ORIGIN, (Decimal("60.0"), Decimal("10.0")), (Decimal("-33.45"), Decimal("-70.66"))]:
            for radius in (1, 5, 50):
                south, north, west, east = bounding_box(*origin, radius)
                lat0, lon0 = math.radians(float(origin[0])), math.radians(float(origin[1]))
                angular = radius / 6371.0
                for bearing in range(0, 360, 5):
                    b = math.radians(bearing)
                    lat = math.asin(
                        math.sin(lat0) * math.cos(angular) + math.cos(lat0) * math.sin(angular) * math.cos(b)
                    )
                    lon = lon0 + math.atan2(
                        math.sin(b) * math.sin(angular) * math.cos(lat0),
                        math.cos(angular) - math.sin(lat0) * math.sin(lat),
                    )
                    point = (round(math.degrees(lat), 6), round(math.degrees(lon), 6))
                    self.assertTrue(
                        south <= Decimal(str(point[0])) <= north and west <= Decimal(str(point[1])) <= east,
                        f"{point} is {radius} km from {origin} but outside the box",
                    )

    def test_bounding_box_is_tight(self):
        south, north, west, east = bounding_box(*self.ORIGIN, 5)
        self.assertLess(haversine_km(*self.ORIGIN, north, self.ORIGIN[1]), 5.02)
        self.assertLess(haversine_km(*self.ORIGIN, self.ORIGIN[0], east), 5.02)


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
                # REQ-26: manual coordinates still have to fall inside
                # ACCOMMODATION_ALLOWED_BOUNDS, so these sit well within Medellin.
                "latitude": "6.200000",
                "longitude": "-75.600000",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["latitude"], Decimal("6.200000"))
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

    @override_settings(GOOGLE_MAPS_API_KEY="")
    def test_shows_setup_message_without_api_key(self):
        response = self.client.get(reverse("navigation:event_map"))
        self.assertContains(response, 'id="map-unavailable"')
        self.assertContains(response, "The interactive map is not available right now.")
        self.assertNotContains(response, 'id="map"')

    @override_settings(GOOGLE_MAPS_API_KEY="fake-js-key")
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

    @override_settings(GOOGLE_MAPS_API_KEY="fake-js-key")
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


class EventMapDistanceTests(TestCase):
    """REQ-08/REQ-14: the map honors the radius and proximity order measured
    from the logged-in user's accommodation, like the event list does."""

    def setUp(self):
        self.user = User.objects.create_user(username="traveler", password="pass12345")
        Accommodation.objects.create(
            user=self.user, address="El Poblado", latitude=6.2087, longitude=-75.5678
        )
        self.near = Event.objects.create(
            title="Cerca",
            description="desc",
            date_time="2026-10-20T20:00:00Z",
            location="Poblado",
            latitude=6.21,
            longitude=-75.57,
            is_free=True,
        )
        self.far = Event.objects.create(
            title="Lejos",
            description="desc",
            date_time="2026-10-10T20:00:00Z",
            location="Norte",
            latitude=6.35,
            longitude=-75.50,
            is_free=True,
        )
        self.no_coords = Event.objects.create(
            title="Sin coordenadas",
            description="desc",
            date_time="2026-10-12T20:00:00Z",
            location="Por definir",
            is_free=True,
        )

    def _titles(self, response):
        return [m["title"] for m in response.context["markers"]]

    def test_radius_filters_markers_for_user_with_accommodation(self):
        self.client.login(username="traveler", password="pass12345")
        response = self.client.get(reverse("navigation:event_map"), {"radius_km": "5"})
        self.assertEqual(self._titles(response), ["Cerca"])

    def test_distance_sort_orders_markers_nearest_first(self):
        self.client.login(username="traveler", password="pass12345")
        response = self.client.get(reverse("navigation:event_map"), {"sort": "distance"})
        self.assertEqual(self._titles(response), ["Cerca", "Lejos"])
        self.assertEqual(response.context["events_without_coords"], 1)

    def test_radius_is_ignored_without_accommodation(self):
        response = self.client.get(reverse("navigation:event_map"), {"radius_km": "5"})
        self.assertEqual(sorted(self._titles(response)), ["Cerca", "Lejos"])
        self.assertContains(response, "Log in")


class GeocodedAtTests(TestCase):
    """Google's coordinates may be kept 30 days: the form records when they arrived."""

    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@example.com", "S3gura!pass")

    def _save(self, data, instance=None):
        form = AccommodationForm(data, instance=instance)
        self.assertTrue(form.is_valid(), form.errors)
        accommodation = form.save(commit=False)
        accommodation.user = self.user
        accommodation.save()
        return accommodation

    @patch("navigation.forms.geocode_address")
    def test_set_when_the_geocoder_answers(self, mock_geocode):
        mock_geocode.return_value = (Decimal("6.208900"), Decimal("-75.568000"))
        accommodation = self._save({"address": "Parque Lleras"})
        self.assertIsNotNone(accommodation.geocoded_at)

    @patch("navigation.forms.geocode_address")
    def test_empty_for_coordinates_typed_by_hand(self, mock_geocode):
        accommodation = self._save({"address": "Mi casa", "latitude": "6.2100", "longitude": "-75.5700"})
        self.assertIsNone(accommodation.geocoded_at)
        mock_geocode.assert_not_called()

    @patch("navigation.forms.geocode_address")
    def test_cleared_when_the_user_replaces_googles_coordinates(self, mock_geocode):
        mock_geocode.return_value = (Decimal("6.208900"), Decimal("-75.568000"))
        accommodation = self._save({"address": "Parque Lleras"})
        accommodation = self._save(
            {"address": "Parque Lleras", "latitude": "6.2100", "longitude": "-75.5700"}, instance=accommodation
        )
        self.assertIsNone(accommodation.geocoded_at)


class RefreshGeocodesTests(TestCase):
    def _accommodation(self, username, geocoded_days_ago):
        user = User.objects.create_user(username, f"{username}@example.com", "S3gura!pass")
        geocoded_at = None if geocoded_days_ago is None else timezone.now() - timedelta(days=geocoded_days_ago)
        return Accommodation.objects.create(
            user=user, address="Parque Lleras", latitude=Decimal("6.2"), longitude=Decimal("-75.5"),
            geocoded_at=geocoded_at,
        )

    def _run(self):
        out, err = StringIO(), StringIO()
        call_command("refresh_geocodes", stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    @patch("navigation.management.commands.refresh_geocodes.geocode_address")
    def test_refreshes_only_googles_old_coordinates(self, mock_geocode):
        mock_geocode.return_value = (Decimal("6.208900"), Decimal("-75.568000"))
        old = self._accommodation("old", 29.5)
        recent = self._accommodation("recent", 3)
        manual = self._accommodation("manual", None)

        out, _ = self._run()

        self.assertIn("Refreshed 1 accommodation(s)", out)
        mock_geocode.assert_called_once_with("Parque Lleras")
        old.refresh_from_db()
        self.assertEqual(old.latitude, Decimal("6.208900"))
        self.assertLess(timezone.now() - old.geocoded_at, timedelta(minutes=1))
        recent.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(recent.latitude, Decimal("6.200000"))
        self.assertEqual(manual.latitude, Decimal("6.200000"))
        self.assertIsNone(manual.geocoded_at)

    @patch("navigation.management.commands.refresh_geocodes.geocode_address")
    def test_a_failed_lookup_keeps_the_row_for_the_next_run(self, mock_geocode):
        mock_geocode.return_value = None
        old = self._accommodation("old", 40)
        before = old.geocoded_at

        out, err = self._run()

        self.assertIn("1 could not be refreshed", out)
        self.assertIn("check_integrations", err)
        old.refresh_from_db()
        self.assertEqual(old.latitude, Decimal("6.200000"))
        self.assertEqual(old.geocoded_at, before)
