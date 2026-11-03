import base64
import io
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
import app as service
from server import app as legacy_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)
        buffer = io.BytesIO()
        Image.new("RGB", (30, 20), "white").save(buffer, format="PNG")
        self.image = buffer.getvalue()
        self.result = dict(ok=True, score=91.0, student_id="6812345", name=None,
                           university=None, grad_year=None, note=None, debug={})

    def post(self, image=None, **kwargs):
        return self.client.post("/analyze", files={"front": ("card.png", self.image if image is None else image, "image/png")}, **kwargs)

    def test_legacy_entry_point_is_identical(self):
        self.assertIs(legacy_app, service.app)

    def test_health(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    @patch("app.analyze")
    def test_student_id_and_score_are_preserved(self, analyze):
        analyze.return_value = self.result
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["student_id"], "6812345")
        self.assertEqual(response.json()["score"], 91.0)

    @patch("app.analyze")
    def test_strict_base64_and_data_uri(self, analyze):
        analyze.return_value = self.result
        value = "data:image/png;base64," + base64.b64encode(self.image).decode()
        response = self.client.post("/analyze_b64", json={"front_b64": value})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["student_id"], "6812345")
        self.assertEqual(self.client.post("/analyze_b64", json={"front_b64": "%%%"}).status_code, 400)

    def test_empty_and_corrupt_images_rejected(self):
        self.assertEqual(self.post(b"").status_code, 400)
        self.assertEqual(self.post(b"not an image").status_code, 400)

    @patch("app.MAX_IMAGE_BYTES", 10)
    def test_size_limit_preserves_413(self):
        self.assertEqual(self.post().status_code, 413)

    @patch("app.MAX_IMAGE_PIXELS", 100)
    def test_pixel_limit(self):
        self.assertEqual(self.post().status_code, 413)

    def test_non_image_format_rejected(self):
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, format="BMP")
        self.assertEqual(self.post(buffer.getvalue()).status_code, 415)

    @patch("app.analyze")
    def test_processing_errors_are_not_success_or_internal_details(self, analyze):
        analyze.side_effect = RuntimeError("secret internal filename")
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.text)

    @patch("app.analyze")
    def test_selfie_is_not_ocr_evidence(self, analyze):
        analyze.return_value = self.result
        response = self.client.post("/analyze", files={
            "front": ("front.png", self.image), "selfie": ("selfie.png", self.image)})
        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once()

    @patch("app.analyze")
    def test_back_card_fallback_keeps_consistent_fields(self, analyze):
        analyze.side_effect = [dict(self.result, ok=False, score=20, student_id=None), self.result]
        response = self.client.post("/analyze", files={
            "front": ("front.png", self.image), "back": ("back.png", self.image)})
        self.assertEqual(response.json()["student_id"], "6812345")
        self.assertEqual(response.json()["score"], 91)

    def test_invalid_threshold_and_regex(self):
        self.assertEqual(self.post(data={"conf_threshold": "101"}).status_code, 422)
        self.assertEqual(self.post(data={"id_regex": "["}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
