from django.core.exceptions import PermissionDenied

from accounts.access import can_access
from accounts.scoping import permits_university_operations


def user_can_access_marketing(user):
    # Campaigns, shared settings and their dispatches are university resources.
    return can_access(user, "view_dashboard", "marketing") and permits_university_operations(user)


def marketing_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not user_can_access_marketing(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper
