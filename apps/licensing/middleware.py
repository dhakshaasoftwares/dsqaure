from django.shortcuts import render

from .service import get_status

# Pages that keep working when the licence has run out, so the owner can log in and fix it.
ALWAYS_ALLOWED = ("/accounts/login/", "/accounts/logout/", "/accounts/language/", "/licence/", "/setup/",
                  "/s/")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class LicenceMiddleware:
    """Attach the licence status to every request; make the app read-only when it has run out."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        status = get_status()
        request.licence = status
        if status.read_only and request.method not in SAFE_METHODS and not request.path.startswith(ALWAYS_ALLOWED):
            return render(request, "licensing/read_only.html", {"status": status}, status=403)
        return self.get_response(request)
