from django.contrib import admin

from .models import Category, Event


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "name_es")
    search_fields = ("name", "name_en", "name_es")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "date_time",
        "end_date",
        "location",
        "organizer",
        "category",
        "is_free",
        "price",
        "status",
    )
    list_filter = ("status", "category", "is_free", "organizer")
    actions = ("approve_events", "reject_events")

    # REQ-25: the same moderation decisions are available from the admin.
    @admin.action(description="Approve selected events (publish)")
    def approve_events(self, request, queryset):
        updated = queryset.update(status=Event.Status.APPROVED)
        self.message_user(request, f"{updated} event(s) approved.")

    @admin.action(description="Reject selected events (keep hidden)")
    def reject_events(self, request, queryset):
        updated = queryset.update(status=Event.Status.REJECTED)
        self.message_user(request, f"{updated} event(s) rejected.")
    search_fields = ("title", "description", "location")
    date_hierarchy = "date_time"
