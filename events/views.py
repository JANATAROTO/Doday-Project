from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from .distance import estimate_transit
from .forms import AccommodationForm, EventForm, SignupForm
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
    return render(request, "events/event_list.html", {"events": events})


def event_detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("category"), pk=pk)

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
        {"event": event, "accommodation": accommodation, "transit_estimate": transit_estimate},
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
