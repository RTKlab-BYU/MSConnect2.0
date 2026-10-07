from __future__ import annotations

import uuid

from django.http import FileResponse, Http404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import generate_metadata_template, generate_worklist_template, generate_worklists, result_path


def _with_download_urls(request, result):
    job_id = result["job_id"]
    for file_info in result["files"]:
        file_info["url"] = f"/api/capabilities/worklist-generator/download/{job_id}/{file_info['url_name']}/"
        file_info.pop("url_name", None)
    return result


class MetadataTemplateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            groups = request.data.get("groups", [])
            if isinstance(groups, str):
                groups = [group.strip() for group in groups.split(",")]
            result = generate_metadata_template(
                str(request.data.get("name", "")),
                str(request.data.get("description", "")),
                groups,
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError({"metadata": str(exc)}) from exc
        return Response(_with_download_urls(request, result), status=status.HTTP_201_CREATED)


class WorklistTemplateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get("metadata")
        if uploaded_file is None:
            raise ValidationError({"metadata": "Attach the completed metadata workbook."})
        try:
            result = generate_worklist_template(uploaded_file)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ValidationError({"metadata": str(exc)}) from exc
        except Exception as exc:
            raise ValidationError({"metadata": f"Unable to generate the worklist template: {exc}"}) from exc
        return Response(_with_download_urls(request, result), status=status.HTTP_201_CREATED)


class WorklistGenerateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get("worklist")
        if uploaded_file is None:
            raise ValidationError({"worklist": "Attach a completed worklist workbook."})
        try:
            result = generate_worklists(uploaded_file)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ValidationError({"worklist": str(exc)}) from exc
        except Exception as exc:
            raise ValidationError({"worklist": f"Unable to generate worklists: {exc}"}) from exc

        return Response(_with_download_urls(request, result), status=status.HTTP_201_CREATED)


class WorklistDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, job_id: uuid.UUID, filename: str):
        path = result_path(job_id, filename)
        if path is None:
            raise Http404("Generated worklist not found.")
        return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
