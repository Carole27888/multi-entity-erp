"""Current user (a context variable) so TimeStampedModel can fill created_by/updated_by."""

from contextvars import ContextVar

_user = ContextVar("current_user", default=None)


def get_current_user():
    return _user.get()


def set_current_user(user):
    return _user.set(user)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _user.set(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            _user.reset(token)
