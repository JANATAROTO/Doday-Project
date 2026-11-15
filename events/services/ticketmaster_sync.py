"""Import of real events from the Ticketmaster Discovery API.

    from events.services.ticketmaster_sync import sync_ticketmaster_events
    result = sync_ticketmaster_events()

Without TICKETMASTER_API_KEY nothing is requested and nothing changes. The
functions here never raise because of the network or the API: they report
what happened in the SyncResult, so a scheduled job can run unattended.

How the search is built, and why:

* By location, not by city name: events within RADIUS_KM of the centre of the
  service area (ACCOMMODATION_ALLOWED_BOUNDS). A name filter would miss
  "Medellin" without the accent and the neighbouring towns of the valley.
* `locale=*`: the API defaults to English and silently leaves out every event
  that only has a Spanish record, which in Colombia is most of them.
* Only events that have not started yet, soonest first.

Running it again is safe: events are matched by Ticketmaster's own id, so they
are updated in place, never duplicated.
"""
import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

import requests
from django.conf import settings
from django.utils import timezone

from events.models import Category, Event

logger = logging.getLogger(__name__)

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
SOURCE = "ticketmaster"
RADIUS_KM = 40
PAGE_SIZE = 100
# The API refuses to go past the 1000th result of a search.
MAX_RESULTS = 1000
REQUEST_TIMEOUT_SECONDS = 10
# The prices are stored in Colombian pesos; other currencies are left out
# rather than shown with the wrong symbol.
PRICE_CURRENCY = "COP"

_GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


class SyncResult(NamedTuple):
    created: int = 0
    updated: int = 0
    skipped: int = 0  # no start time yet, or cancelled
    available: int = 0  # how many events Ticketmaster has for this search
    problem: str = ""  # why nothing could be imported; empty when all went well


def _api_key():
    return getattr(settings, "TICKETMASTER_API_KEY", "")


def geohash(latitude, longitude, precision=9):
    """Encode a point the way the API's `geoPoint` parameter expects."""
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    bits, value, use_longitude, characters = 0, 0, True, []
    while len(characters) < precision:
        interval, coordinate = (lon_range, longitude) if use_longitude else (lat_range, latitude)
        middle = (interval[0] + interval[1]) / 2
        if coordinate >= middle:
            value = value * 2 + 1
            interval[0] = middle
        else:
            value = value * 2
            interval[1] = middle
        use_longitude = not use_longitude
        bits += 1
        if bits == 5:
            characters.append(_GEOHASH_ALPHABET[value])
            bits, value = 0, 0
    return "".join(characters)


def service_area_centre():
    south, north, west, east = settings.ACCOMMODATION_ALLOWED_BOUNDS
    return (south + north) / 2, (west + east) / 2


def _search_params(city, size, page):
    params = {
        "apikey": _api_key(),
        "locale": "*",
        "startDateTime": timezone.now().astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sort": "date,asc",
        "size": size,
        "page": page,
    }
    if city:
        params["city"] = city
    else:
        params["geoPoint"] = geohash(*service_area_centre())
        params["radius"] = RADIUS_KM
        params["unit"] = "km"
    return params


def _request(city, size, page):
    """One page of the search. Returns (events, total_available, problem)."""
    try:
        response = requests.get(API_URL, params=_search_params(city, size, page), timeout=REQUEST_TIMEOUT_SECONDS)
        data = response.json()
    except (requests.RequestException, ValueError, TypeError):
        logger.warning("Ticketmaster request failed", exc_info=True)
        return [], 0, "Could not reach Ticketmaster (network problem or timeout)."

    if response.status_code != 200:
        fault = (data.get("fault") or {}).get("faultstring") if isinstance(data, dict) else None
        detail = fault or f"HTTP {response.status_code}"
        if response.status_code == 401:
            detail += ". Check that TICKETMASTER_API_KEY is the Consumer Key of your app."
        elif response.status_code == 429:
            detail += ". The daily quota is used up; try again tomorrow."
        logger.warning("Ticketmaster answered %s: %s", response.status_code, detail)
        return [], 0, f"Ticketmaster rejected the request: {detail}"

    events = data.get("_embedded", {}).get("events", [])
    total = data.get("page", {}).get("totalElements", len(events))
    return events, total, ""


def fetch_ticketmaster_events(city=None, size=200):
    """Up to `size` upcoming events. Returns (events, total_available, problem)."""
    if not _api_key():
        return [], 0, "TICKETMASTER_API_KEY is not set."

    size = max(1, min(size, MAX_RESULTS))
    page_size = min(size, PAGE_SIZE)
    events, total, page = [], 0, 0
    while len(events) < size and (page + 1) * page_size <= MAX_RESULTS:
        batch, total, problem = _request(city, page_size, page)
        if problem:
            # Keep what earlier pages returned; report only a total failure.
            return (events, total, "") if events else ([], 0, problem)
        events.extend(batch)
        if len(batch) < page_size or len(events) >= total:
            break
        page += 1
    return events[:size], total, ""


def probe():
    """For check_integrations: (works, message) from a single one-event request."""
    if not _api_key():
        return False, "TICKETMASTER_API_KEY is not set."
    _, total, problem = _request(city=None, size=1, page=0)
    if problem:
        return False, problem
    return True, f"key accepted; {total} upcoming event(s) within {RADIUS_KM} km of the service area"


# -- turning one Ticketmaster record into an Event -------------------------------


def _start(raw):
    start = raw.get("dates", {}).get("start", {})
    value = start.get("dateTime")
    if not value or start.get("dateTBD"):
        return None  # announced without a confirmed date: nothing to put on a calendar
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None


def _is_cancelled(raw):
    return raw.get("dates", {}).get("status", {}).get("code") in ("cancelled", "canceled")


def _category(raw):
    classifications = raw.get("classifications") or [{}]
    name = (classifications[0].get("segment") or {}).get("name") or ""
    if not name or name.lower() == "undefined":
        name = "General"
    category, _ = Category.objects.get_or_create(name=name)
    return category


def _coordinate(value):
    try:
        return round(Decimal(str(value)), 6)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _location(venue):
    """"Venue, City" — and never empty, because the listing shows it."""
    parts = [venue.get("name"), (venue.get("city") or {}).get("name")]
    return ", ".join(part for part in parts if part) or "Medellín"


def _price(raw):
    """Lowest ticket price in pesos, or None when Ticketmaster does not publish it."""
    for price_range in raw.get("priceRanges") or []:
        if price_range.get("currency") == PRICE_CURRENCY and price_range.get("min") is not None:
            try:
                return Decimal(str(price_range["min"])).quantize(Decimal("1"))
            except (InvalidOperation, TypeError, ValueError):
                continue
    return None


def _event_fields(raw, start):
    venue = (raw.get("_embedded", {}).get("venues") or [{}])[0]
    position = venue.get("location") or {}
    price = _price(raw)
    return {
        "title": (raw.get("name") or "").strip()[:150],
        "description": raw.get("info") or raw.get("description") or raw.get("pleaseNote") or "",
        "date_time": start,
        "location": _location(venue)[:255],
        "latitude": _coordinate(position.get("latitude")),
        "longitude": _coordinate(position.get("longitude")),
        "category": _category(raw),
        "is_free": price == 0,
        "price": price,
        "ticket_url": raw.get("url", ""),
    }


def sync_ticketmaster_events(city=None, size=200):
    """Bring upcoming Ticketmaster events into the catalogue. Returns a SyncResult.

    `city` searches by city name instead of around the service area (to try
    another city). Events without a confirmed start time and cancelled events
    are skipped.
    """
    raw_events, available, problem = fetch_ticketmaster_events(city=city, size=size)
    if problem:
        return SyncResult(problem=problem)

    created = updated = skipped = 0
    for raw in raw_events:
        start = _start(raw)
        if not raw.get("id") or start is None or _is_cancelled(raw):
            skipped += 1
            continue
        _, was_created = Event.objects.update_or_create(
            external_source=SOURCE, external_id=raw["id"], defaults=_event_fields(raw, start),
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return SyncResult(created=created, updated=updated, skipped=skipped, available=available)
