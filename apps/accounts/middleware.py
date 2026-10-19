from django.utils import translation


class UserLanguageMiddleware:
    """Show the interface in the language each user picked."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            translation.activate(user.preferred_language)
            request.LANGUAGE_CODE = user.preferred_language
        return self.get_response(request)
