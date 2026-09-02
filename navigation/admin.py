from django.contrib import admin

from .models import Accommodation


@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = ("user", "address", "latitude", "longitude")
    search_fields = ("user__username", "address")
