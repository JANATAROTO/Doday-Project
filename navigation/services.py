"""Navigation component.

REQ-01: resolve a free-text accommodation address into coordinates.
REQ-03: estimate transit distance/time between the user's accommodation and an
event.

Both talk to OpenRouteService (ORS) and share the same ORS_API_KEY.
"""
import os
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

import requests
from django.conf import settings

EARTH_RADIUS_KM = 6371.0

# Pelias ranks results near this point higher, so a street address typed
# without a city still resolves inside Medellín instead of somewhere else.
MEDELLIN_FOCUS = (6.244200, -75.581200)

# Matches the decimal_places=6 of Accommodation/Event coordinate fields.
_COORD_PRECISION = Decimal("0.000001")


def _format_coord(coord):
    return str(coord).replace(",", ".")


def _get_ors_api_key():
    return getattr(settings, "ORS_API_KEY", "") or os.environ.get("ORS_API_KEY", "")


def _to_coordinate(value):
    return Decimal(str(value)).quantize(_COORD_PRECISION)


def haversine_km(origin_lat, origin_lon, dest_lat, dest_lon):
    """Great-circle distance in kilometres between two points.

    Deliberately local arithmetic, not an API call: the radius filter (REQ-08)
    and proximity sorting (REQ-14) need a distance for *every* event in a
    listing, and routing that through estimate_transit() would mean one
    external request per event on every page load. Use estimate_transit() when
    an actual travel time for a single event is what matters.

    Accepts Decimal or float; returns a float.
    """
    origin_lat, origin_lon, dest_lat, dest_lon = (
        radians(float(value)) for value in (origin_lat, origin_lon, dest_lat, dest_lon)
    )
    delta_lat = dest_lat - origin_lat
    delta_lon = dest_lon - origin_lon
    a = sin(delta_lat / 2) ** 2 + cos(origin_lat) * cos(dest_lat) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def geocode_address(address, country="CO", focus=MEDELLIN_FOCUS):
    """REQ-01: return (latitude, longitude) for a free-text address, or None.

    Uses the Pelias geocoder hosted by openrouteservice, covered by the same
    ORS_API_KEY as estimate_transit(). Returns None when no key is configured,
    when the address cannot be resolved, or when the call fails/times out —
    same defensive contract as estimate_transit(), so callers never need to
    guard against exceptions.
    """
    ors_api_key = _get_ors_api_key()
    if not ors_api_key:
        return None

    if not address or not address.strip():
        return None

    params = {
        "api_key": ors_api_key,
        "text": address,
        "size": 1,
    }
    if country:
        params["boundary.country"] = country
    if focus:
        params["focus.point.lat"] = _format_coord(focus[0])
        params["focus.point.lon"] = _format_coord(focus[1])

    try:
        response = requests.get(
            "https://api.openrouteservice.org/geocode/search",
            params=params,
            headers={"Authorization": ors_api_key},
            timeout=5,
        )
        if response.status_code != 200:
            return None

        features = response.json().get("features") or []
        if not features:
            return None

        # GeoJSON stores coordinates as [longitude, latitude] — the same
        # inverted order ORS uses everywhere else.
        coordinates = features[0].get("geometry", {}).get("coordinates") or []
        if len(coordinates) < 2:
            return None

        longitude, latitude = coordinates[0], coordinates[1]
        return _to_coordinate(latitude), _to_coordinate(longitude)
    except Exception:
        return None


def estimate_transit(origin_lat, origin_lon, dest_lat, dest_lon):
    """Return (distance_km, duration_minutes) using OpenRouteService (ORS) API.

    Returns None if no ORS API key is configured or if the API call fails/timeouts.
    """
    ors_api_key = _get_ors_api_key()
    if not ors_api_key:
        return None

    # ORS critical rule: coordinates strictly in order [longitude, latitude]
    start = f"{_format_coord(origin_lon)},{_format_coord(origin_lat)}"
    end = f"{_format_coord(dest_lon)},{_format_coord(dest_lat)}"

    try:
        response = requests.get(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            params={
                "api_key": ors_api_key,
                "start": start,
                "end": end,
            },
            headers={
                "Authorization": ors_api_key,
            },
            timeout=5,
        )
        if response.status_code != 200:
            return None

        data = response.json()

        summary = None
        if "features" in data and len(data["features"]) > 0:
            summary = data["features"][0].get("properties", {}).get("summary", {})
        elif "routes" in data and len(data["routes"]) > 0:
            summary = data["routes"][0].get("summary", {})

        if not summary:
            return None

        distance_m = summary.get("distance")
        duration_s = summary.get("duration")

        if distance_m is None or duration_s is None:
            return None

        distance_km = round(distance_m / 1000.0, 1)
        duration_minutes = round(duration_s / 60.0)

        return distance_km, duration_minutes
    except Exception:
        return None
