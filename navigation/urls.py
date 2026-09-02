from django.urls import path

from . import views

app_name = "navigation"

urlpatterns = [
    path("accommodation/", views.accommodation_edit, name="accommodation_edit"),
]
