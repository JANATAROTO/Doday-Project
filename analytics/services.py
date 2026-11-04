"""Analytics component — REQ-30.

record() is called by the Events component when a visitor opens an event,
saves it to favorites or follows its ticket link. build_dashboard() turns
those interactions, plus the published catalog, into the indicators shown on
the staff dashboard: what people are interested in (demand) next to what the
catalog offers (supply), so the team can decide which events to promote or
look for.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import ExtractIsoWeekDay, TruncWeek
from django.utils import timezone
from django.utils.dates import WEEKDAYS
from django.utils.formats import number_format
from django.utils.translation import gettext as _

from events.models import Category, Event

from .models import EventInteraction

PERIOD_CHOICES = (7, 30, 90)
DEFAULT_PERIOD = 30

# Weighs how strong each interaction is as a sign of interest: following the
# ticket link is closer to attending than saving, and saving than viewing.
INTEREST_WEIGHTS = {
    EventInteraction.Kind.VIEW: 1,
    EventInteraction.Kind.FAVORITE: 3,
    EventInteraction.Kind.TICKET_CLICK: 5,
}

_VIEWED_SESSION_KEY = "analytics_viewed_event_ids"
_MAX_VIEWED_IN_SESSION = 500


def record(request, event, kind):
    """Store one interaction. Staff browsing is not counted, and a visitor
    opening the same event several times in one session counts as one view,
    so the numbers reflect people rather than page reloads."""
    if request.user.is_authenticated and request.user.is_staff:
        return None
    if kind == EventInteraction.Kind.VIEW:
        viewed = request.session.get(_VIEWED_SESSION_KEY, [])
        if event.pk in viewed:
            return None
        request.session[_VIEWED_SESSION_KEY] = (viewed + [event.pk])[-_MAX_VIEWED_IN_SESSION:]
    return EventInteraction.objects.create(event=event, kind=kind)


def _counts():
    kinds = EventInteraction.Kind
    return {
        "views": Count("pk", filter=Q(kind=kinds.VIEW)),
        "favorites": Count("pk", filter=Q(kind=kinds.FAVORITE)),
        "ticket_clicks": Count("pk", filter=Q(kind=kinds.TICKET_CLICK)),
    }


def _interest(row):
    return (
        row["views"] * INTEREST_WEIGHTS[EventInteraction.Kind.VIEW]
        + row["favorites"] * INTEREST_WEIGHTS[EventInteraction.Kind.FAVORITE]
        + row["ticket_clicks"] * INTEREST_WEIGHTS[EventInteraction.Kind.TICKET_CLICK]
    )


def _with_bars(rows, key):
    """Add an integer bar width (0-100) for the CSS bar charts. Integers on
    purpose: a float would be rendered as "45,5" in Spanish and break the
    inline style."""
    top = max((row[key] for row in rows), default=0)
    for row in rows:
        row["bar"] = round(row[key] * 100 / top) if top else 0
    return rows


def _rate(part, whole):
    return round(part * 100 / whole) if whole else 0


def build_dashboard(period_days=DEFAULT_PERIOD):
    now = timezone.now()
    since = now - timedelta(days=period_days)
    interactions = EventInteraction.objects.filter(
        created_at__gte=since, event__status=Event.Status.APPROVED
    )
    published = Event.objects.published()
    upcoming = published.filter(date_time__gte=now)

    # --- KPIs ---------------------------------------------------------------
    totals = interactions.aggregate(**_counts())
    kpis = {
        **totals,
        "published_events": published.count(),
        "upcoming_events": upcoming.count(),
        "click_through_rate": _rate(totals["ticket_clicks"], totals["views"]),
    }

    # --- Demand: most interesting events ---------------------------------------
    top_events = list(
        interactions.values("event_id", "event__title").annotate(**_counts())
    )
    for row in top_events:
        row["interest"] = _interest(row)
    top_events.sort(key=lambda row: row["interest"], reverse=True)
    top_events = _with_bars(top_events[:5], "interest")

    # --- Demand vs supply by category ------------------------------------------
    categories = {category.pk: category for category in Category.objects.all()}
    supply = dict(
        published.values("category").annotate(total=Count("pk")).values_list("category", "total")
    )
    by_category = []
    for row in interactions.values("event__category").annotate(**_counts()):
        category = categories.get(row["event__category"])
        events_in_category = supply.get(row["event__category"], 0)
        interest = _interest(row)
        by_category.append(
            {
                "name": category.display_name if category else _("General"),
                "interest": interest,
                "events": events_in_category,
                # Interest per published event: high values mean people want
                # more of this category than the catalog currently offers.
                "interest_per_event": round(interest / events_in_category, 1) if events_in_category else interest,
                "ticket_rate": _rate(row["ticket_clicks"], row["views"]),
                **row,
            }
        )
    by_category.sort(key=lambda row: row["interest"], reverse=True)
    _with_bars(by_category, "interest")

    # --- Demand by weekday -----------------------------------------------------
    per_day = dict(
        interactions.annotate(day=ExtractIsoWeekDay("created_at"))
        .values("day")
        .annotate(total=Count("pk"))
        .values_list("day", "total")
    )
    # ISO weekday 1 = Monday; django.utils.dates.WEEKDAYS uses 0 = Monday.
    by_weekday = _with_bars(
        [{"label": WEEKDAYS[day - 1], "total": per_day.get(day, 0)} for day in range(1, 8)],
        "total",
    )

    # --- Supply: upcoming events per week and free vs paid ----------------------
    weeks = (
        upcoming.filter(date_time__lt=now + timedelta(weeks=8))
        .annotate(week=TruncWeek("date_time"))
        .values("week")
        .annotate(total=Count("pk"))
        .order_by("week")
    )
    by_week = _with_bars([{"week": row["week"], "total": row["total"]} for row in weeks], "total")
    free_upcoming = upcoming.filter(is_free=True).count()

    # --- Insights in plain words ------------------------------------------------
    insights = []
    if by_category:
        best = max(by_category, key=lambda row: row["interest_per_event"])
        insights.append(
            _("“%(category)s” gets the most interest per published event (%(value)s). Adding more events of this category is the best bet.")
            % {"category": best["name"], "value": number_format(best["interest_per_event"], decimal_pos=1)}
        )
    if any(row["total"] for row in by_weekday):
        peak = max(by_weekday, key=lambda row: row["total"])
        insights.append(
            _("%(day)s is the day with the most activity. Publish and promote new events before it.")
            % {"day": peak["label"]}
        )
    if top_events:
        insights.append(
            _("“%(title)s” is the event with the most interest in this period.")
            % {"title": top_events[0]["event__title"]}
        )
    if kpis["upcoming_events"]:
        insights.append(
            _("%(free)s of %(total)s upcoming events are free (%(rate)s%%).")
            % {
                "free": free_upcoming,
                "total": kpis["upcoming_events"],
                "rate": _rate(free_upcoming, kpis["upcoming_events"]),
            }
        )

    return {
        "period_days": period_days,
        "since": since,
        "kpis": kpis,
        "top_events": top_events,
        "by_category": by_category,
        "by_weekday": by_weekday,
        "by_week": by_week,
        "free_upcoming": free_upcoming,
        "paid_upcoming": kpis["upcoming_events"] - free_upcoming,
        "free_rate": _rate(free_upcoming, kpis["upcoming_events"]),
        "insights": insights,
        "has_data": bool(totals["views"] or totals["favorites"] or totals["ticket_clicks"]),
    }
