"""Small rate limiter for public forms (login, sign-up, proposals, password reset).

Counts requests per client IP in fixed time windows using Django's cache, so
it needs no extra dependency. With the default in-memory cache the count is
per server process; point CACHES at Redis or the database when the site runs
several workers.
"""

from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render


def client_ip(request):
    """The visitor's IP address.

    X-Forwarded-For can be forged by the client, so it is only trusted when
    TRUSTED_PROXY_COUNT says how many of our own proxies appended to it: the
    real client is that many entries from the right.
    """
    proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies > 0 and forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(parts) >= proxies:
            return parts[-proxies]
    return request.META.get("REMOTE_ADDR", "unknown")


def is_limited(request, scope, limit, window):
    """Count this request; True when the IP is over `limit` in `window` seconds."""
    if not getattr(settings, "RATELIMIT_ENABLED", True):
        return False
    key = f"ratelimit:{scope}:{client_ip(request)}"
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:  # the key expired between add() and incr()
        cache.set(key, 1, timeout=window)
        count = 1
    return count > limit


def rate_limit(scope, limit, window, methods=("POST",)):
    """Decorator: answer 429 once an IP exceeds `limit` requests per `window` seconds."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods and is_limited(request, scope, limit, window):
                return render(request, "429.html", status=429)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
