"""REQ-29: English/Spanish names for the categories we know about.

Categories are data, and they arrive in either language: seed_events creates
Spanish ones ("Música") and the Ticketmaster sync English ones ("Music").
Category.save() and the 0004 data migration use this table to fill in both
names, so the interface can show each category in the active language. Any
other category simply keeps its original name in both languages until an
admin fills in the translations.

Plain data on purpose (no model imports): the migration imports it too.
"""

# (English, Spanish)
KNOWN_CATEGORY_NAMES = [
    ("Music", "Música"),
    ("Concerts", "Conciertos"),
    ("Sports", "Deportes"),
    ("Food", "Gastronomía"),
    ("Culture", "Cultura"),
    ("Art", "Arte"),
    ("Arts & Theatre", "Artes y teatro"),
    ("Theatre", "Teatro"),
    ("Film", "Cine"),
    ("Dance", "Danza"),
    ("Comedy", "Comedia"),
    ("Family", "Familia"),
    ("Festivals", "Festivales"),
    ("Fairs", "Ferias"),
    ("Nightlife", "Vida nocturna"),
    ("Workshops", "Talleres"),
    ("Exhibitions", "Exposiciones"),
    ("Education", "Educación"),
    ("Outdoors", "Aire libre"),
    ("Technology", "Tecnología"),
    ("Literature", "Literatura"),
    ("Miscellaneous", "Varios"),
    ("General", "General"),
]

# Other spellings that mean the same category.
_ALIASES = {
    "deporte": "Sports",
    "theater": "Theatre",
    "cinema": "Film",
    "concert": "Concerts",
    "festival": "Festivals",
    "fair": "Fairs",
    "feria": "Fairs",
    "workshop": "Workshops",
    "exhibition": "Exhibitions",
    "food & drink": "Food",
    "comida": "Food",
}

_LOOKUP = {}
for english, spanish in KNOWN_CATEGORY_NAMES:
    _LOOKUP[english.casefold()] = (english, spanish)
    _LOOKUP[spanish.casefold()] = (english, spanish)
for alias, english in _ALIASES.items():
    _LOOKUP[alias] = _LOOKUP[english.casefold()]


def bilingual_names(name):
    """Return (english, spanish) for a known category name, else None."""
    return _LOOKUP.get((name or "").strip().casefold())
