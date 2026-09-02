from django import forms

from .models import Accommodation


class AccommodationForm(forms.ModelForm):
    class Meta:
        model = Accommodation
        fields = ["address", "latitude", "longitude"]
