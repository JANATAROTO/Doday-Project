# REQ-29: Colombian number format for the Spanish interface ("$85.000").
# Django's generic Spanish locale groups thousands with a non-breaking space;
# everything not overridden here falls back to Django's "es" formats.
DECIMAL_SEPARATOR = ","
THOUSAND_SEPARATOR = "."
NUMBER_GROUPING = 3
