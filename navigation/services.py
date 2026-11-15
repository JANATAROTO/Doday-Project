"""Navigation component.

REQ-01: resolve a free-text accommodation address into coordinates.
REQ-03: distance, travel time and route between the user's accommodation and
an event.
REQ-08/REQ-14: straight-line distance from the accommodation to every event.

Geocoding and routing use Google Maps Platform (Geocoding API and Routes API)
with a server-side key, GOOGLE_MAPS_SERVER_KEY. It is a different key from
GOOGLE_MAPS_API_KEY, which is sent to the browser to draw the maps: a browser
key is restricted by website and Google rejects it for server calls.

Google's terms shape two things here: their results may only be shown on a
Google map (so the route is drawn with the Maps JavaScript API), and
coordinates they return may be kept for 30 days at most (see
Accommodation.geocoded_at and the refresh_geocodes command).
"""
import logging
from decimal import Decimal
from math import asin, cos, degrees, radians, sin, sqrt

import requests
from django.conf import settings
from django.db.models import Case, ExpressionWrapper, F, FloatField, Value, When
from django.db.models.functions import ASin, Cast, Cos, Least, Power, Radians, Round, Sin, Sqrt

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
# Only what the page needs: Google bills by the fields requested, and these
# keep the call in the cheapest ("Essentials") tier.
ROUTES_FIELD_MASK = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
REQUEST_TIMEOUT_SECONDS = 5

# Matches the decimal_places=6 of Accommodation/Event coordinate fields.
_COORD_PRECISION = Decimal("0.000001")


def _server_key():
    return getattr(settings, "GOOGLE_MAPS_SERVER_KEY", "")


def _to_coordinate(value):
    return Decimal(str(value)).quantize(_COORD_PRECISION)


# --- Straight-line distance --------------------------------------------------


def haversine_km(origin_lat, origin_lon, dest_lat, dest_lon):
    """Great-circle distance in kilometres between two points.

    Local arithmetic, not an API call. Accepts Decimal or float; returns a
    float. distance_km_expression() is the same formula for the database.
    """
    origin_lat, origin_lon, dest_lat, dest_lon = (
        radians(float(value)) for value in (origin_lat, origin_lon, dest_lat, dest_lon)
    )
    delta_lat = dest_lat - origin_lat
    delta_lon = dest_lon - origin_lon
    a = sin(delta_lat / 2) ** 2 + cos(origin_lat) * cos(dest_lat) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def distance_km_expression(origin_lat, origin_lon, lat_field="latitude", lon_field="longitude"):
    """The haversine distance from a fixed origin as database expressions.

    Returns (exact, rounded): `exact` to filter and sort with, `rounded` to one
    decimal to show. Rows without coordinates get NULL in both. Works on
    PostgreSQL and SQLite alike, with no geographic extension.
    """

    def number(value):
        return Value(float(value), output_field=FloatField())

    origin_lat_rad = radians(float(origin_lat))
    origin_lon_rad = radians(float(origin_lon))
    lat = Radians(Cast(F(lat_field), FloatField()))
    lon = Radians(Cast(F(lon_field), FloatField()))

    a = Power(Sin((lat - number(origin_lat_rad)) / number(2)), number(2)) + number(
        cos(origin_lat_rad)
    ) * Cos(lat) * Power(Sin((lon - number(origin_lon_rad)) / number(2)), number(2))
    # Least() guards asin against a value a hair above 1 from rounding.
    distance = number(2 * EARTH_RADIUS_KM) * ASin(Sqrt(Least(number(1), a)))

    def located(expression):
        # Explicit NULL for unlocated rows: PostgreSQL's LEAST ignores NULLs,
        # so without this they would come out as half the Earth's circumference.
        return Case(
            When(**{f"{lat_field}__isnull": False, f"{lon_field}__isnull": False}, then=expression),
            default=Value(None, output_field=FloatField()),
            output_field=FloatField(),
        )

    exact = located(ExpressionWrapper(distance, output_field=FloatField()))
    rounded = located(ExpressionWrapper(Round(distance * number(10)) / number(10), output_field=FloatField()))
    return exact, rounded


def bounding_box(origin_lat, origin_lon, radius_km):
    """(south, north, west, east) of the rectangle that contains the circle.

    A cheap pre-filter the indexes can answer before the exact distance is
    computed. It uses the same sphere as haversine_km, plus a small margin, so
    it can never leave out a point the exact formula would accept.
    """
    origin_lat, origin_lon = float(origin_lat), float(origin_lon)
    angular = (radius_km / EARTH_RADIUS_KM) * 1.001
    delta_lat = degrees(angular)
    # A degree of longitude shrinks towards the poles; never divide by ~0.
    ratio = sin(angular) / max(cos(radians(origin_lat)), 0.01)
    delta_lon = degrees(asin(ratio)) if ratio < 1 else 180.0
    margin = 0.000002  # the coordinates are rounded to 6 decimals
    return (
        _to_coordinate(max(origin_lat - delta_lat - margin, -90)),
        _to_coordinate(min(origin_lat + delta_lat + margin, 90)),
        _to_coordinate(max(origin_lon - delta_lon - margin, -180)),
        _to_coordinate(min(origin_lon + delta_lon + margin, 180)),
    )


# --- Geocoding (REQ-01) --------------------------------------------------------


def geocode_address(address, country="CO"):
    """REQ-01: return (latitude, longitude) for a free-text address, or None.

    Returns None when no server key is configured, when the address cannot be
    resolved, or when the call fails or times out, so callers never need to
    guard against exceptions. Results are biased towards the service area
    (ACCOMMODATION_ALLOWED_BOUNDS), so a street typed without a city still
    resolves inside it.
    """
    key = _server_key()
    if not key or not address or not address.strip():
        return None

    params = {"address": address, "key": key}
    if country:
        params["components"] = f"country:{country}"
    bounds = getattr(settings, "ACCOMMODATION_ALLOWED_BOUNDS", None)
    if bounds:
        south, north, west, east = bounds
        params["bounds"] = f"{south},{west}|{north},{east}"

    try:
        response = requests.get(GEOCODING_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        data = response.json()
        if response.status_code != 200 or data.get("status") != "OK":
            # An address Google cannot place is an everyday answer, not a fault.
            if data.get("status") != "ZERO_RESULTS":
                _log_google_problem("Geocoding", response.status_code, data)
            return None
        location = data["results"][0]["geometry"]["location"]
        return _to_coordinate(location["lat"]), _to_coordinate(location["lng"])
    except Exception:
        logger.warning("Geocoding request failed", exc_info=True)
        return None


# --- Routes (REQ-03) -----------------------------------------------------------


def estimate_transit(origin_lat, origin_lon, dest_lat, dest_lon):
    """Return (distance_km, duration_minutes), or None when there is no route."""
    route = get_transit_route(origin_lat, origin_lon, dest_lat, dest_lon)
    if route is None:
        return None
    return route["distance_km"], route["duration_minutes"]


def get_transit_route(origin_lat, origin_lon, dest_lat, dest_lon):
    """Route summary plus the path as [lat, lng] pairs, or None.

    Returns None when no server key is configured or the call fails. The
    result is not stored: Google's terms do not allow caching routes.
    """
    key = _server_key()
    if not key:
        return None

    def waypoint(latitude, longitude):
        return {"location": {"latLng": {"latitude": float(latitude), "longitude": float(longitude)}}}

    body = {
        "origin": waypoint(origin_lat, origin_lon),
        "destination": waypoint(dest_lat, dest_lon),
        "travelMode": "DRIVE",
        # Traffic-aware routing is billed in a higher tier and is not needed
        # for an "about X minutes" estimate.
        "routingPreference": "TRAFFIC_UNAWARE",
        "units": "METRIC",
    }
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": ROUTES_FIELD_MASK}

    try:
        response = requests.post(ROUTES_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        data = response.json()
        routes = data.get("routes") or []
        if response.status_code != 200:
            _log_google_problem("Routes", response.status_code, data)
            return None
        if not routes:
            return None  # no road between the two points: nothing to report

        route = routes[0]
        distance_m = route.get("distanceMeters")
        duration_s = _seconds(route.get("duration"))
        if distance_m is None or duration_s is None:
            return None

        return {
            "distance_km": round(distance_m / 1000.0, 1),
            "duration_minutes": round(duration_s / 60.0),
            "coordinates": decode_polyline(route.get("polyline", {}).get("encodedPolyline", "")),
        }
    except Exception:
        logger.warning("Routes request failed", exc_info=True)
        return None


def _seconds(duration):
    """Google sends durations as text, e.g. "754s"."""
    if not duration:
        return None
    try:
        return float(str(duration).rstrip("s"))
    except ValueError:
        return None


def decode_polyline(encoded):
    """Decode Google's encoded polyline format into [lat, lng] pairs."""
    coordinates = []
    index = latitude = longitude = 0
    length = len(encoded)

    while index < length:
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                if index >= length:
                    return coordinates  # truncated input: keep what decoded cleanly
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        coordinates.append([latitude / 1e5, longitude / 1e5])

    return coordinates


def _log_google_problem(service, status_code, data):
    """Record why Google said no (key not enabled, quota, bad request...)
    without ever writing the key itself to the logs."""
    error = data.get("error") if isinstance(data, dict) else None
    detail = (
        (error or {}).get("message")
        or (data.get("error_message") if isinstance(data, dict) else None)
        or (data.get("status") if isinstance(data, dict) else None)
        or "no detail"
    )
    logger.warning("%s API answered %s: %s", service, status_code, detail)
