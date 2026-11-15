"""Health check for the hosting platform.

Render (and any load balancer) polls GET /healthz every few seconds to know
whether the service is up. The answer comes from a middleware placed first, on
purpose:

* it must not depend on the Host header or on HTTPS, because the probe arrives
  from inside the platform's network, not through the public domain;
* it must not touch the database: a query every few seconds would keep a
  serverless database (Neon) awake around the clock and burn its free quota.

So it only says "the process is running and can answer", which is exactly
what the platform needs to decide whether to route traffic here.
"""

from django.http import HttpResponse

HEALTH_PATH = "/healthz"


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == HEALTH_PATH:
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
