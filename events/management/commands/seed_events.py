from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Category, Event

SAMPLE_EVENTS = [
    {
        "title": "Feria de Emprendedores El Poblado",
        "description": "Mercado con productos locales, comida y música en vivo para apoyar a emprendedores de la ciudad.",
        "days_ahead": 3,
        "location": "Parque Lleras, El Poblado, Medellín",
        "category": "Gastronomía",
        "is_free": True,
        "price": None,
        "organizer": "sebas",
    },
    {
        "title": "Concierto Sinfónico de Medianoche",
        "description": "La Orquesta Filarmónica de Medellín presenta un repertorio de clásicos bajo las estrellas.",
        "days_ahead": 7,
        "location": "Teatro Metropolitano, Medellín",
        "category": "Música",
        "is_free": False,
        "price": 45000,
        "organizer": "sebas",
    },
    {
        "title": "Torneo de Fútbol Barrial",
        "description": "Copa amistosa entre barrios del Valle de Aburrá, abierta al público.",
        "days_ahead": 10,
        "location": "Unidad Deportiva Atanasio Girardot, Medellín",
        "category": "Deporte",
        "is_free": True,
        "price": None,
        "organizer": "maria",
    },
    {
        "title": "Noche de Arte y Grafiti en Comuna 13",
        "description": "Recorrido guiado por los murales más icónicos con artistas locales explicando su trabajo.",
        "days_ahead": 5,
        "location": "Comuna 13, Medellín",
        "category": "Cultura",
        "is_free": False,
        "price": 25000,
        "organizer": "maria",
    },
    {
        "title": "Fiesta del Libro y la Cultura",
        "description": "Feria editorial de varios días con lanzamientos, talleres y conversatorios con autores.",
        "days_ahead": 14,
        "days_duration": 6,
        "location": "Jardín Botánico, Medellín",
        "category": "Cultura",
        "is_free": True,
        "price": None,
        "organizer": "sebas",
    },
]

DEMO_ORGANIZERS = {
    "maria": "123456789",
}


class Command(BaseCommand):
    help = "Seed the database with sample events and organizers for RF2/RF5 demo purposes."

    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now().replace(hour=19, minute=0, second=0, microsecond=0)

        for username, password in DEMO_ORGANIZERS.items():
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"organizer created: {username}"))

        for data in SAMPLE_EVENTS:
            category, _ = Category.objects.get_or_create(name=data["category"])
            organizer = User.objects.get(username=data["organizer"])
            start = now + timedelta(days=data["days_ahead"])
            days_duration = data.get("days_duration")
            event, created = Event.objects.update_or_create(
                title=data["title"],
                defaults={
                    "description": data["description"],
                    "date_time": start,
                    "end_date": start + timedelta(days=days_duration) if days_duration else None,
                    "location": data["location"],
                    "category": category,
                    "is_free": data["is_free"],
                    "price": data["price"],
                    "organizer": organizer,
                },
            )
            status = "created" if created else "updated"
            self.stdout.write(self.style.SUCCESS(f"{status}: {event.title} (organizer: {organizer.username})"))
