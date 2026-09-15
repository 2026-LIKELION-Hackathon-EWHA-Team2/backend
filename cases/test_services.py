import json
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from cases.services import (
    analyze_diagnosis_document,
    translate_diagnosis_analysis,
)


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
            "cases.services.ai.OpenAI",
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

    def test_document_analysis_uses_bounded_openai_client(self):
        document = SimpleUploadedFile(
            "diagnosis.pdf",
            b"%PDF-1.7\nmock pdf",
        )

        with patch("cases.services.ai.OpenAI") as openai:
            openai.return_value.responses.create.return_value.output_text = (
                self.openai_client.responses.create.return_value.output_text
            )
            analyze_diagnosis_document(
                document=document,
                target_language="ko",
                symptom_data={},
            )

        openai.assert_called_once_with(
            timeout=settings.OPENAI_DOCUMENT_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )


class TranslateDiagnosisAnalysisTests(SimpleTestCase):
    @patch("cases.services.ai.OpenAI")
    def test_reuses_structured_result_and_preserves_numeric_fields(
        self,
        openai,
    ):
        document_result = {
            "extracted_text": "sensitive raw document text",
            "symptoms": {
                "description": "Swelling",
                "start_date": "2026-08-10",
                "onset_timing": "After treatment",
                "pain_level": 3,
                "areas": ["Forehead"],
                "types": ["Pain"],
            },
            "procedure": {
                "name": "Botox",
                "area": "Forehead",
                "date": "2026-08-09",
            },
            "ingredients": ["Botulinum Toxin Type A"],
            "clinician_note": "Observe symptoms.",
        }
        translated_result = {
            **document_result,
            "symptoms": {
                **document_result["symptoms"],
                "description": "부기",
                "start_date": "2099-01-01",
                "pain_level": 99,
            },
            "procedure": {
                **document_result["procedure"],
                "name": "보톡스",
                "area": "이마",
                "date": "2099-01-01",
            },
            "clinician_note": "증상을 관찰하세요.",
        }
        openai.return_value.responses.create.return_value.output_text = (
            json.dumps(translated_result)
        )

        result = translate_diagnosis_analysis(document_result, "ko")

        self.assertEqual(result["symptoms"]["start_date"], "2026-08-10")
        self.assertEqual(result["symptoms"]["pain_level"], 3)
        self.assertEqual(result["procedure"]["date"], "2026-08-09")
        self.assertEqual(result["procedure"]["name"], "보톡스")
        request_input = openai.return_value.responses.create.call_args.kwargs[
            "input"
        ]
        self.assertNotIn("extracted_text", json.loads(request_input))
        openai.assert_called_once_with(
            timeout=settings.OPENAI_TRANSLATION_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
