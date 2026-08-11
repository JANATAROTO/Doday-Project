from django.contrib import admin

from .models import Accommodation, Category, Event


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


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
    )
    list_filter = ("category", "is_free", "organizer")
    search_fields = ("title", "description", "location")
    date_hierarchy = "date_time"


@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = ("user", "address", "latitude", "longitude")
    search_fields = ("user__username", "address")
