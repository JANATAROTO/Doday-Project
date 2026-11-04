from django.contrib import admin

from .models import EventInteraction


@admin.register(EventInteraction)
class EventInteractionAdmin(admin.ModelAdmin):
    list_display = ("event", "kind", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("event__title",)
    date_hierarchy = "created_at"
