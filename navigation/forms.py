from django import forms

from .models import Accommodation
from .services import geocode_address


class AccommodationForm(forms.ModelForm):
    """REQ-01: capture the user's accommodation location.

    The user only types an address — the coordinates are resolved through the
    Navigation component's geocoder and never shown. They are only revealed,
    as a manual fallback, when the lookup fails: no ORS_API_KEY configured, an
    address that cannot be resolved, or the API being down. Without that
    fallback the form would be unusable whenever the geocoder is unavailable.
    """

    COORDINATE_FIELDS = ("latitude", "longitude")

    LOOKUP_FAILED = (
        "We could not find the coordinates for that address. "
        "Check the address, or enter the latitude and longitude manually."
    )

    class Meta:
        model = Accommodation
        fields = ["address", "latitude", "longitude"]
        help_texts = {
            "address": "Street address or place name — we look up the coordinates for you.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendered only after a failed lookup; the template checks this.
        self.show_coordinate_fields = False
        self._visible_widgets = {}

        for name in self.COORDINATE_FIELDS:
            field = self.fields[name]
            # The model requires both, but the form does not: clean() fills
            # them in from the address.
            field.required = False
            self._visible_widgets[name] = field.widget
            field.widget = forms.HiddenInput()

    def _reveal_coordinate_fields(self):
        self.show_coordinate_fields = True
        for name in self.COORDINATE_FIELDS:
            self.fields[name].widget = self._visible_widgets[name]

    def _address_changed_alone(self):
        """The address changed but the coordinates were left untouched.

        They still point at the previous place, so they have to be resolved
        again instead of being saved against the new address.
        """
        return "address" in self.changed_data and not (
            set(self.COORDINATE_FIELDS) & set(self.changed_data)
        )

    def clean(self):
        cleaned_data = super().clean()
        address = cleaned_data.get("address")
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if not address:
            return cleaned_data

        coordinates_are_missing = latitude is None or longitude is None
        if not (coordinates_are_missing or self._address_changed_alone()):
            return cleaned_data

        coordinates = geocode_address(address)
        if coordinates:
            cleaned_data["latitude"], cleaned_data["longitude"] = coordinates
            return cleaned_data

        self._reveal_coordinate_fields()
        raise forms.ValidationError(self.LOOKUP_FAILED)
