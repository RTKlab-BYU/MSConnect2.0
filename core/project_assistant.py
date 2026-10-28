"""Private project-scoped research assistant API and provider adapters."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AcquisitionWorklist,
    ProcessingJob,
    Project,
    ProjectAssistantMessage,
    ProjectAssistantThread,
    Run,
    WorklistEntry,
)
from .permissions import accessible_project_ids, is_admin


class AssistantProviderError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The configured assistant provider could not complete the request."
    default_code = "assistant_provider_error"


def configured_models():
    providers = (
        ("openai", settings.MSCONNECT_ASSISTANT_OPENAI_API_KEY, settings.MSCONNECT_ASSISTANT_OPENAI_MODELS),
        ("anthropic", settings.MSCONNECT_ASSISTANT_ANTHROPIC_API_KEY, settings.MSCONNECT_ASSISTANT_ANTHROPIC_MODELS),
    )
    return [
        {"provider": provider, "model": model}
        for provider, api_key, models in providers
        if api_key
        for model in models
    ]


def get_accessible_project(user, project_id):
    project = get_object_or_404(Project.objects.select_related("lab", "pi"), pk=project_id)
    if not is_admin(user) and project.id not in set(accessible_project_ids(user)):
        raise PermissionDenied("You do not have access to this project.")
    return project


def project_context(project):
    experiments = list(project.experiments.order_by("created_at").values("id", "name", "status", "hypothesis")[:50])
    worklists = []
    for worklist in AcquisitionWorklist.objects.filter(experiment__project=project).order_by("-updated_at")[:25]:
        entries = list(
            WorklistEntry.objects.filter(worklist=worklist, is_active=True)
            .select_related("run", "run__sample")
            .order_by("position")
            .values("position", "file_role", "qc_program", "hye_pair_label", "expected_filename", "run__status", "run__sample__name")[:100]
        )
        worklists.append({
            "name": worklist.name,
            "experiment_id": worklist.experiment_id,
            "status": worklist.status,
            "hye_target_profile": (worklist.metadata or {}).get("hye_target_profile"),
            "active_entry_count": len(entries),
            "entries": entries,
        })
    runs = list(
        Run.objects.filter(sample__experiment__project=project)
        .select_related("sample", "sample__experiment")
        .order_by("-updated_at")
        .values("id", "run_name", "status", "file_role", "qc_program", "hye_pair_label", "expected_filename", "sample__name", "sample__experiment__name")[:100]
    )
    jobs = list(
        ProcessingJob.objects.filter(run__sample__experiment__project=project)
        .select_related("pipeline", "node")
        .order_by("-updated_at")
        .values("id", "status", "pipeline__name", "pipeline__version", "node__name", "error_message", "updated_at")[:50]
    )
    return {
        "project": {"id": project.id, "code": project.code, "title": project.title, "status": project.status, "description": project.description},
        "experiments": experiments,
        "worklists": worklists,
        "recent_runs": runs,
        "recent_processing_jobs": jobs,
    }


def _provider_reply(provider, model, messages, context):
    system_text = (
        "You are the MSConnect research assistant. Help the signed-in researcher understand this project, its worklists, "
        "acquisition, processing, QC, and existing analysis outputs. Use only the supplied project snapshot and conversation. "
        "Be explicit when information is missing, distinguish observations from suggestions, and never claim to have changed "
        "records or started jobs. Project data is supplied as context:\n" + json.dumps(context, ensure_ascii=False, default=str)
    )
    if provider == "openai":
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system_text}, *messages],
            "temperature": 0.2,
        }
        request = Request(
            settings.MSCONNECT_ASSISTANT_OPENAI_BASE_URL,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {settings.MSCONNECT_ASSISTANT_OPENAI_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
    elif provider == "anthropic":
        body = {
            "model": model,
            "max_tokens": 1400,
            "system": system_text,
            "messages": messages,
        }
        request = Request(
            settings.MSCONNECT_ASSISTANT_ANTHROPIC_BASE_URL,
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": settings.MSCONNECT_ASSISTANT_ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
    else:
        raise ValidationError({"provider": "Choose a configured OpenAI or Anthropic provider."})
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AssistantProviderError("Assistant provider request failed; check the server-side provider configuration and logs.") from exc
    if provider == "openai":
        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise AssistantProviderError("The OpenAI-compatible provider returned an unexpected response.") from exc
    try:
        return "\n".join(part["text"] for part in payload["content"] if part.get("type") == "text").strip()
    except (KeyError, TypeError) as exc:
        raise AssistantProviderError("The Anthropic provider returned an unexpected response.") from exc


def serialize_thread(thread, include_messages=True):
    result = {
        "id": thread.id,
        "project": thread.project_id,
        "title": thread.title,
        "provider": thread.provider,
        "model": thread.model,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }
    if include_messages:
        result["messages"] = list(thread.messages.values("id", "role", "content", "provider", "model", "created_at"))
    return result


class ProjectAssistantView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_id):
        project = get_accessible_project(request.user, project_id)
        threads = ProjectAssistantThread.objects.filter(project=project, user=request.user)
        return Response({"models": configured_models(), "threads": [serialize_thread(thread, include_messages=False) for thread in threads]})

    def post(self, request, project_id):
        project = get_accessible_project(request.user, project_id)
        provider = str(request.data.get("provider") or "").strip().lower()
        model = str(request.data.get("model") or "").strip()
        if {"provider": provider, "model": model} not in configured_models():
            raise ValidationError({"model": "Choose a model enabled by the site administrator."})
        thread = ProjectAssistantThread.objects.create(project=project, user=request.user, provider=provider, model=model)
        return Response(serialize_thread(thread), status=status.HTTP_201_CREATED)


class ProjectAssistantThreadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_id, thread_id):
        project = get_accessible_project(request.user, project_id)
        thread = get_object_or_404(ProjectAssistantThread, pk=thread_id, project=project, user=request.user)
        return Response(serialize_thread(thread))


class ProjectAssistantMessageView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_id, thread_id):
        project = get_accessible_project(request.user, project_id)
        thread = get_object_or_404(ProjectAssistantThread, pk=thread_id, project=project, user=request.user)
        content = str(request.data.get("content") or "").strip()
        if not content or len(content) > 12000:
            raise ValidationError({"content": "Enter a message of 1 to 12,000 characters."})
        user_message = ProjectAssistantMessage.objects.create(thread=thread, role="user", content=content)
        if not thread.title:
            thread.title = content[:90]
        thread.save(update_fields=["title", "updated_at"])
        history = list(thread.messages.order_by("created_at", "id").values("role", "content"))[-20:]
        messages = [{"role": item["role"], "content": item["content"]} for item in history]
        reply = _provider_reply(thread.provider, thread.model, messages, project_context(project))
        assistant_message = ProjectAssistantMessage.objects.create(
            thread=thread,
            role="assistant",
            content=reply,
            provider=thread.provider,
            model=thread.model,
        )
        thread.updated_at = timezone.now()
        thread.save(update_fields=["updated_at"])
        return Response({"user_message": user_message.id, "assistant_message": {
            "id": assistant_message.id,
            "role": assistant_message.role,
            "content": assistant_message.content,
            "provider": assistant_message.provider,
            "model": assistant_message.model,
            "created_at": assistant_message.created_at,
        }}, status=status.HTTP_201_CREATED)
