from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="event_list"),
    path("create/", views.event_create, name="event_create"),
    path("accommodation/", views.accommodation_edit, name="accommodation_edit"),
    path("favorites/", views.favorites_list, name="favorites_list"),
    path("<int:pk>/", views.event_detail, name="event_detail"),
    path("<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("<int:pk>/delete/", views.event_delete, name="event_delete"),
    path("<int:pk>/favorite/", views.favorite_toggle, name="favorite_toggle"),
]
