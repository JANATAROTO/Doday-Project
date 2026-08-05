from django import forms

from .models import Accommodation, Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "date_time",
            "location",
            "category",
            "is_free",
            "price",
        ]
        widgets = {
            "date_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }


class AccommodationForm(forms.ModelForm):
    class Meta:
        model = Accommodation
        fields = ["address", "latitude", "longitude"]