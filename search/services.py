"""Search component — REQ-07, REQ-11, REQ-19, REQ-20, REQ-22.

Pure filtering logic kept separate from the Events views so the Search
component can be reasoned about (and tested) independently, even though it
has no database table of its own — it only queries the Event model owned by
the Events component.
"""
from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone


def filter_events(events, filter_form):
    """Apply the current filter selection to an Event queryset.

    `filter_form` must already be bound; if it isn't valid the original
    queryset is returned unfiltered.
    """
    if not filter_form.is_valid():
        return events

    # REQ-19: keyword search over title and description.
    keyword = filter_form.cleaned_data.get("q")
    if keyword:
        events = events.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))

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

    return events
