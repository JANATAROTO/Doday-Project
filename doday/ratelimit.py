"""Small rate limiter for public forms (login, sign-up, proposals, password reset).

Counts requests per client IP in fixed time windows using Django's cache, so
it needs no extra dependency. In production the cache is the database (see
CACHES in settings.py), so the count is shared by every worker process; the
in-memory cache of local development counts per process.
"""

import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render


def client_ip(request):
    """The visitor's IP address.

    Behind a hosting platform the connection comes from the platform's proxy,
    so the visitor's address has to be read from a header, and headers can be
    forged. Two settings say which one to believe:

    * CLIENT_IP_HEADER: a header the platform's edge always overwrites with
      the real address (Render and anything behind Cloudflare:
      "CF-Connecting-IP"). Preferred when the platform has one.
    * TRUSTED_PROXY_COUNT: how many of our own proxies append to
      X-Forwarded-For; the real client is that many entries from the right,
      whatever the client put in front.

    With neither set (local development, or a server exposed directly) only
    the address of the connection itself is trusted.
    """
    header = getattr(settings, "CLIENT_IP_HEADER", "")
    if header:
        value = request.META.get("HTTP_" + header.upper().replace("-", "_"), "").strip()
        if value:
            return value
    proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies > 0 and forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(parts) >= proxies:
            return parts[-proxies]
    return request.META.get("REMOTE_ADDR", "unknown")


def is_limited(request, scope, limit, window):
    """Count this request; True when the IP is over `limit` in `window` seconds.

    Fixed windows: the clock is cut into slices of `window` seconds and each
    slice has its own counter (the slice number is part of the key). Reading
    and writing the counter are two steps on purpose: the database cache has
    no real increment, and its imitation silently shortens the life of the
    counter to the cache's default timeout, which cut a one-hour limit down
    to five minutes. Two requests arriving at the very same instant may count
    as one; for slowing down guessing that is an acceptable trade.
    """
    if not getattr(settings, "RATELIMIT_ENABLED", True):
        return False
    key = f"ratelimit:{scope}:{client_ip(request)}:{int(time.time() // window)}"
    count = (cache.get(key) or 0) + 1
    cache.set(key, count, timeout=window)
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
