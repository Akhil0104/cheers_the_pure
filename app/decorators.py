from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .account_utils import detect_account_type


def _get_account_type(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.account_type:
        return profile.account_type
    return detect_account_type(user.email)


def b2c_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        if _get_account_type(request.user) != 'b2c':
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)

    return wrapper


def b2b_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        if _get_account_type(request.user) != 'b2b':
            return redirect('access_denied')
        return view_func(request, *args, **kwargs)

    return wrapper
