from django.conf import settings
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
        help_text="Only the organizer who created the event can edit it (RF5).",
    )
    title = models.CharField(max_length=150)
    description = models.TextField()
    date_time = models.DateTimeField()
    location = models.CharField(
        max_length=255,
        help_text="Address or place name (exact map coordinates come with RF1).",
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name="events"
    )
    is_free = models.BooleanField(default=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave empty if the event is free.",
    )

    class Meta:
        ordering = ["date_time"]

    def __str__(self):
        return self.title
