"""Search component — REQ-07, REQ-08, REQ-11, REQ-14, REQ-19, REQ-20, REQ-22.

Pure filtering logic kept separate from the Events views so the Search
component can be reasoned about (and tested) independently, even though it
has no database table of its own — it only queries the Event model owned by
the Events component.

The distance itself belongs to the Navigation component; Search only decides
what to do with it.
"""
from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone

from navigation.services import haversine_km

from .forms import SORT_DATE, SORT_DISTANCE


def filter_events(events, filter_form, origin=None):
    """Apply the current filter selection to an Event queryset.

    When `filter_form` is unbound or invalid no filter is applied, but the
    distances below are still attached: the event list renders with an unbound
    form on a plain page load, and the distance is information about the
    events, not a filter the user asked for.

    `origin` is the (latitude, longitude) of the user's accommodation, or None
    when they have not saved one. With an origin, every event comes back
    carrying a `distance_km` attribute and the result is a list instead of a
    queryset, because the distance is computed in Python. Without one, the
    queryset is returned untouched and both the radius (REQ-08) and proximity
    sorting (REQ-14) are ignored — there is nothing to measure from.
    """
    radius_km = None
    sort = SORT_DATE

    if filter_form.is_valid():
        # REQ-19: keyword search over title and description.
        keyword = filter_form.cleaned_data.get("q")
        if keyword:
            events = events.filter(
                Q(title__icontains=keyword) | Q(description__icontains=keyword)
            )

        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")

        # REQ-07: date-range filter. Events without an end_date are treated as
        # single-day — they only need to start on/after date_from — while
        # multi-day events (fairs, festivals) match if their stay overlaps
        # the requested [date_from, date_to] range at all.
        if date_from:
            check_in = timezone.make_aware(datetime.combine(date_from, time.min))
            events = events.filter(
                Q(end_date__gte=check_in) | Q(end_date__isnull=True, date_time__gte=check_in)
            )
        if date_to:
            check_out = timezone.make_aware(datetime.combine(date_to, time.max))
            events = events.filter(date_time__lte=check_out)

        # REQ-11: category filter — matches any of the user-selected categories.
        categories = filter_form.cleaned_data.get("category")
        if categories:
            events = events.filter(category__in=categories)

        # REQ-22: free-admission-only filter.
        if filter_form.cleaned_data.get("free_only"):
            events = events.filter(is_free=True)

        # REQ-08: radius around the accommodation.
        radius_km = filter_form.cleaned_data.get("radius_km")

        # REQ-14: the field is not required, so an empty value means the
        # default order by start date.
        sort = filter_form.cleaned_data.get("sort") or SORT_DATE

    if origin is None:
        # Nothing to measure from, so neither the radius nor proximity sorting
        # can apply. The queryset keeps Event.Meta.ordering — by start date,
        # which is the other half of what REQ-14 asks for.
        return events

    events = _with_distances(events, origin, radius_km)

    if sort == SORT_DISTANCE:
        events = _by_proximity(events)

    return events


def _by_proximity(events):
    """REQ-14: nearest first, events with no location last.

    Events without coordinates cannot be placed on a distance scale, so they
    go to the end as a group rather than being dropped — the same treatment
    they get everywhere else in the project. (With a radius they are already
    gone; see _with_distances.)

    The sort key never compares None against a float: the boolean first
    element partitions located from unlocated events before any number is
    looked at.

    `sorted` is stable and `events` arrives in Event.Meta.ordering, so events
    at the same distance keep their start-date order for free.
    """
    return sorted(
        events,
        key=lambda event: (
            event.distance_km is None,
            event.distance_km if event.distance_km is not None else 0.0,
        ),
    )


def _with_distances(events, origin, radius_km):
    """Attach `distance_km` to every event, dropping those outside the radius.

    Returns a list: the distance is plain Python arithmetic (see
    navigation.services.haversine_km), not something the database can filter
    on, and one external routing call per event is not an option.

    Events with no coordinates are a legitimate part of the catalogue — some
    have no physical venue at all. They get `distance_km = None` and are kept
    while no radius is requested, but a radius necessarily excludes them:
    something with no location cannot be "within X km".
    """
    origin_latitude, origin_longitude = origin
    limit = float(radius_km) if radius_km is not None else None
    within_radius = []

    for event in events:
        if event.latitude is None or event.longitude is None:
            event.distance_km = None
            if limit is None:
                within_radius.append(event)
            continue

        distance = haversine_km(
            origin_latitude, origin_longitude, event.latitude, event.longitude
        )
        event.distance_km = round(distance, 1)
        if limit is None or distance <= limit:
            within_radius.append(event)

    return within_radius
