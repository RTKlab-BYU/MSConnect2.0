from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient


class WorklistGeneratorApiTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.client = APIClient()
        self.client.force_authenticate(user=get_user_model().objects.create_user(username="operator"))

    @override_settings(MEDIA_ROOT="/tmp/msconnect-worklist-generator-test")
    @patch("capabilities.worklist_generator.services.run_worklist")
    def test_generate_returns_isolated_downloads(self, run_worklist):
        def fake_run(_input_path, output_dir):
            output_dir = Path(output_dir)
            ms_path = output_dir / "EN123_MS.csv"
            lc_path = output_dir / "EN123_LC.csv"
            ms_path.write_text("MS\n", encoding="utf-8")
            lc_path.write_text("LC\n", encoding="utf-8")
            return ms_path, lc_path

        run_worklist.side_effect = fake_run
        with override_settings(MEDIA_ROOT=self.media_directory.name):
            response = self.client.post(
                "/api/capabilities/worklist-generator/generate/",
                {"worklist": SimpleUploadedFile("worklist.xlsx", b"placeholder")},
                format="multipart",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual({item["kind"] for item in response.data["files"]}, {"ms", "lc"})
        self.assertTrue(all(item["url"].startswith("/api/") for item in response.data["files"]))

        with override_settings(MEDIA_ROOT=self.media_directory.name):
            download = self.client.get(response.data["files"][0]["url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"MS\n")

    def test_generate_rejects_non_excel_uploads(self):
        with override_settings(MEDIA_ROOT=self.media_directory.name):
            response = self.client.post(
                "/api/capabilities/worklist-generator/generate/",
                {"worklist": SimpleUploadedFile("worklist.txt", b"not excel")},
                format="multipart",
            )
        self.assertEqual(response.status_code, 400)

    @override_settings(MEDIA_ROOT="/tmp/msconnect-worklist-generator-stages")
    def test_metadata_and_template_stages_create_downloadable_workbooks(self):
        media_root = Path("/tmp/msconnect-worklist-generator-stages")
        response = self.client.post(
            "/api/capabilities/worklist-generator/metadata/",
            {"name": "Demo experiment", "description": "Demo", "groups": ["Healthy", "Diseased"]},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        metadata_file = media_root / "worklist_generator_results" / response.data["job_id"] / response.data["files"][0]["name"]
        self.assertTrue(metadata_file.is_file())

        response = self.client.post(
            "/api/capabilities/worklist-generator/worklist-template/",
            {"metadata": SimpleUploadedFile(metadata_file.name, metadata_file.read_bytes())},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        worklist_file = media_root / "worklist_generator_results" / response.data["job_id"] / response.data["files"][0]["name"]
        self.assertTrue(worklist_file.is_file())

    def test_download_rejects_path_traversal(self):
        with override_settings(MEDIA_ROOT=self.media_directory.name):
            response = self.client.get(
                "/api/capabilities/worklist-generator/download/00000000-0000-0000-0000-000000000000/..%2Fsettings.py/"
            )
        self.assertEqual(response.status_code, 404)
