from datetime import datetime, time

from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .distance import estimate_transit
from .forms import AccommodationForm, EventFilterForm, EventForm, SignupForm
from .models import Event


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("events:event_list")
    else:
        form = SignupForm()

    return render(request, "registration/signup.html", {"form": form})


def event_list(request):
    events = Event.objects.select_related("category").all()

    filter_form = EventFilterForm(request.GET or None)
    if filter_form.is_valid():
        # RF19: keyword search over title and description.
        keyword = filter_form.cleaned_data.get("q")
        if keyword:
            events = events.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))

        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")

        # RF7: date-range filter. Events without an end_date are treated as
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

        # RF11: category filter — matches any of the user-selected categories.
        categories = filter_form.cleaned_data.get("category")
        if categories:
            events = events.filter(category__in=categories)

    return render(
        request, "events/event_list.html", {"events": events, "filter_form": filter_form}
    )


def event_detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("category"), pk=pk)

    # RF21: external ticketing link. Every event points to the same platform
    # for now — no per-organizer ticketing integration yet.
    ticket_url = "https://www.ticketmaster.co/"

    transit_estimate = None
    accommodation = getattr(request.user, "accommodation", None) if request.user.is_authenticated else None
    if accommodation and event.latitude is not None and event.longitude is not None:
        result = estimate_transit(
            accommodation.latitude, accommodation.longitude, event.latitude, event.longitude
        )
        if result:
            distance_km, duration_minutes = result
            transit_estimate = {"distance_km": distance_km, "duration_minutes": duration_minutes}

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "accommodation": accommodation,
            "transit_estimate": transit_estimate,
            "ticket_url": ticket_url,
        },
    )


@login_required
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm()

    return render(request, "events/event_form.html", {"form": form, "event": None})


@login_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.organizer_id != request.user.id:
        raise PermissionDenied("You can only edit events you organize.")

    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm(instance=event)

    return render(request, "events/event_form.html", {"form": form, "event": event})


@login_required
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.organizer_id != request.user.id:
        raise PermissionDenied("You can only delete events you organize.")

    if request.method == "POST":
        event.delete()
        return redirect("events:event_list")

    return render(request, "events/event_confirm_delete.html", {"event": event})


@login_required
def accommodation_edit(request):
    accommodation = getattr(request.user, "accommodation", None)

    if request.method == "POST":
        form = AccommodationForm(request.POST, instance=accommodation)
        if form.is_valid():
            accommodation = form.save(commit=False)
            accommodation.user = request.user
            accommodation.save()
            return redirect("events:event_list")
    else:
        form = AccommodationForm(instance=accommodation)

    return render(request, "events/accommodation_form.html", {"form": form})
