def is_superuser(request):
    return request.user.is_authenticated and request.user.is_superuser


def can_access_material(request):
    return request.user.is_authenticated and request.user.is_staff
