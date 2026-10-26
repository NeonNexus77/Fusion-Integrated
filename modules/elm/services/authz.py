"""Authorization checks for Employee Leave Management operations."""

from core.api.exceptions import PermissionDeniedError


def require(actor, *codes):
    """Raise an authorization error unless the actor holds a required permission."""
    if actor is None:
        raise PermissionDeniedError(
            "Authentication required.",
            code="not_authenticated",
        )

    check = getattr(actor, "has_permission", None)
    if check is None or not any(check(code) for code in codes):
        raise PermissionDeniedError(
            f"This action needs {' or '.join(codes)}.",
            code="permission_denied",
        )
