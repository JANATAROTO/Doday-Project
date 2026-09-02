from django.conf import settings
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

    def __str__(self):
        return f"{self.user.username} - {self.address}"
