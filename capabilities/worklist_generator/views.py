from __future__ import annotations

import uuid

from django.http import FileResponse, Http404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import generate_worklists, result_path


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

        job_id = result["job_id"]
        for file_info in result["files"]:
            file_info["url"] = request.build_absolute_uri(
                f"/api/capabilities/worklist-generator/download/{job_id}/{file_info['url_name']}/"
            )
            file_info.pop("url_name", None)
        return Response(result, status=status.HTTP_201_CREATED)


class WorklistDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, job_id: uuid.UUID, filename: str):
        path = result_path(job_id, filename)
        if path is None:
            raise Http404("Generated worklist not found.")
        return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
