import json
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from cases.services import analyze_diagnosis_document


class AnalyzeDiagnosisDocumentMimeTypeTests(SimpleTestCase):
    def setUp(self):
        self.openai_client = Mock()
        self.openai_client.responses.create.return_value.output_text = (
            json.dumps(
                {
                    "extracted_text": "document text",
                    "symptoms": {},
                    "procedure": {
                        "name": "Botox",
                        "area": "Forehead",
                        "date": "2026-08-01",
                    },
                    "ingredients": [],
                    "clinician_note": "",
                }
            )
        )

    def analyze(self, filename, document_bytes):
        document = SimpleUploadedFile(filename, document_bytes)
        with patch(
            "cases.services.OpenAI",
            return_value=self.openai_client,
        ):
            analyze_diagnosis_document(
                document=document,
                target_language="ko",
                symptom_data={},
            )

        return self.openai_client.responses.create.call_args.kwargs[
            "input"
        ][0]["content"][1]

    def test_pdf_signature_sets_pdf_data_url_without_file_extension(self):
        document_input = self.analyze(
            "cloudinary-public-id",
            b"%PDF-1.7\nmock pdf",
        )

        self.assertEqual(document_input["type"], "input_file")
        self.assertEqual(
            document_input["filename"],
            "cloudinary-public-id.pdf",
        )
        self.assertTrue(
            document_input["file_data"].startswith(
                "data:application/pdf;base64,"
            )
        )

    def test_jpeg_signature_sets_image_data_url_without_file_extension(self):
        document_input = self.analyze(
            "cloudinary-public-id",
            b"\xff\xd8\xff\xe0mock jpeg",
        )

        self.assertEqual(document_input["type"], "input_image")
        self.assertTrue(
            document_input["image_url"].startswith(
                "data:image/jpeg;base64,"
            )
        )

    def test_png_signature_overrides_misleading_filename_extension(self):
        document_input = self.analyze(
            "diagnosis.pdf",
            b"\x89PNG\r\n\x1a\nmock png",
        )

        self.assertEqual(document_input["type"], "input_image")
        self.assertTrue(
            document_input["image_url"].startswith(
                "data:image/png;base64,"
            )
        )

    def test_unknown_file_signature_is_rejected_before_openai_call(self):
        with self.assertRaisesMessage(
            ValueError,
            "진단서 파일 형식을 확인할 수 없습니다.",
        ):
            self.analyze("diagnosis.pdf", b"not a supported document")

        self.openai_client.responses.create.assert_not_called()
