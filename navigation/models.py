from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Accommodation(models.Model):
    """Navigation component — the user's home location (REQ-01), used to
    estimate transit distance/time to events (REQ-03)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accommodation"
    )
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    def clean(self):
        super().clean()
        errors = {}

        if self.latitude is None or self.longitude is None:
            return
        if not -90 <= self.latitude <= 90:
            errors["latitude"] = "Latitude must be between -90 and 90."
        if not -180 <= self.longitude <= 180:
            errors["longitude"] = "Longitude must be between -180 and 180."

        south, north, west, east = settings.ACCOMMODATION_ALLOWED_BOUNDS
        if not south <= self.latitude <= north:
            errors["latitude"] = (
                f"Latitude must be within the allowed area ({south} to {north})."
            )
        if not west <= self.longitude <= east:
            errors["longitude"] = (
                f"Longitude must be within the allowed area ({west} to {east})."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user.username} - {self.address}"
