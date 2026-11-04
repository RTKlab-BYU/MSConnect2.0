from django.db.models import Q
from rest_framework import permissions

from .models import LabMembership, LabMembershipRole, Project, UserRole


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


def accessible_project_ids(user):
    if not user or not user.is_authenticated:
        return []
    return list(
        Project.objects.filter(Q(owner_id=user.pk) | Q(memberships__user_id=user.pk, memberships__active=True))
        .values_list("id", flat=True)
        .distinct()
    )


class RoleScopedWritePermission(permissions.BasePermission):
    message = "You do not have permission for this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(view, "allow_watcher_agent", False) and getattr(request.user, "agent_role", None) == "watcher":
            return True

        if request.method in permissions.SAFE_METHODS:
            return True

        if getattr(view, "write_requires_admin", False):
            return is_admin(request.user)

        if getattr(view, "write_requires_facility_manager", False):
            if is_admin(request.user):
                return True
            if request.method == "POST":
                facility_id = request.data.get("facility")
                return _manages_facility(request.user, facility_id)
            return True

        return user_role(request.user) != UserRole.COLLABORATOR

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS or not getattr(view, "write_requires_facility_manager", False):
            return True
        if is_admin(request.user):
            return True
        old_facility_id = getattr(obj, "facility_id", None)
        target_facility_id = request.data.get("facility", old_facility_id)
        return _manages_facility(request.user, old_facility_id) and _manages_facility(request.user, target_facility_id)


def _manages_facility(user, facility_id) -> bool:
    if not facility_id:
        return False
    return LabMembership.objects.filter(
        user=user,
        active=True,
        role__in=(LabMembershipRole.FACILITY_MANAGER, LabMembershipRole.ADMIN),
        lab__active=True,
        lab__facility_id=facility_id,
    ).exists()


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
