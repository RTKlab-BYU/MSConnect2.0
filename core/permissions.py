from rest_framework import permissions

from .models import UserRole


def is_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.global_role == UserRole.ADMIN)


def user_role(user) -> str:
    if is_admin(user):
        return UserRole.ADMIN

    profile = getattr(user, "profile", None)
    if profile:
        return profile.global_role
    return UserRole.RESEARCHER


def active_lab_ids(user):
    if not user or not user.is_authenticated:
        return []

    memberships = user.lab_memberships.filter(active=True).values_list("lab_id", flat=True)
    return list(memberships)


class RoleScopedWritePermission(permissions.BasePermission):
    message = "You do not have permission for this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        if getattr(view, "write_requires_admin", False):
            return is_admin(request.user)

        return user_role(request.user) != UserRole.COLLABORATOR


class AgentRolePermission(permissions.BasePermission):
    message = "You do not have permission for this agent action."

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False

        agent_role = getattr(user, "agent_role", None)
        if not agent_role:
            return False

        allowed_roles = getattr(view, "agent_roles", ())
        return agent_role in allowed_roles
