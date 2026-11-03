"""Student-card OCR API. Run with uvicorn app:app --host 127.0.0.1."""
from __future__ import annotations

import base64
import binascii
import io
import logging
import os
import re
import warnings
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
import uvicorn

from ocr import analyze

logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_BASE64_CHARS = ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 128

app = FastAPI(title="Student Card OCR", version="1.1.0")
origins = [origin.strip() for origin in os.getenv("OCR_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_credentials=False, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])


class AnalyzeResponse(BaseModel):
    ok: bool
    score: float
    student_id: Optional[str] = None
    name: Optional[str] = None
    university: Optional[str] = None
    grad_year: Optional[int] = None
    note: Optional[str] = None
    debug: Optional[dict] = None


class AnalyzeBase64Request(BaseModel):
    front_b64: str = Field(min_length=1, max_length=MAX_BASE64_CHARS)
    back_b64: Optional[str] = Field(default=None, max_length=MAX_BASE64_CHARS)
    selfie_b64: Optional[str] = Field(default=None, max_length=MAX_BASE64_CHARS)


def validate_image(data: bytes) -> bytes:
    if not data:
        raise HTTPException(400, "Image must not be empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds the 8 MiB limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(415, "Use a JPEG, PNG, or WebP image")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise HTTPException(413, "Image exceeds the 12 megapixel limit")
                image.verify()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, "Image dimensions are too large") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(400, "Invalid or corrupted image") from None
    return data


def read_upload(upload: Optional[UploadFile]) -> Optional[bytes]:
    if upload is None:
        return None
    # Read a bounded amount even when the Content-Length header is absent.
    return validate_image(upload.file.read(MAX_IMAGE_BYTES + 1))


def decode_image(value: Optional[str]) -> Optional[bytes]:
    if value is None:
        return None
    payload = value
    if value.startswith("data:"):
        header, separator, payload = value.partition(",")
        if not separator or not header.endswith(";base64"):
            raise HTTPException(400, "Invalid base64 image")
    if len(payload) > MAX_BASE64_CHARS:
        raise HTTPException(413, "Image exceeds the 8 MiB limit")
    try:
        return validate_image(base64.b64decode(payload, validate=True))
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid base64 image") from None


def analyze_images(front: bytes, back: Optional[bytes], **options) -> dict:
    try:
        front_result = analyze(front, **options)
        results = [front_result]
        if back:
            results.append(analyze(back, **options))
        # Keep the fields, confidence and success flag from the SAME result.
        # A selfie is never evidence of a student ID or a face match.
        result = next((item for item in results if item.get("ok") and item.get("student_id")), None)
        if result is None:
            result = max(results, key=lambda item: item.get("score", 0))
        return {key: result.get(key) for key in AnalyzeResponse.model_fields}
    except HTTPException:
        raise
    except Exception:
        logger.exception("OCR inference failed")
        raise HTTPException(500, "OCR processing failed") from None


@app.get("/health")
def health():
    return {"ok": True, "status": "ok"}


# Sync handlers run CPU/subprocess OCR work in FastAPI's worker pool.
@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_multipart(
    front: UploadFile = File(...),
    back: Optional[UploadFile] = File(None),
    selfie: Optional[UploadFile] = File(None),
    id_regex: Optional[str] = Form(None, max_length=128),
    conf_threshold: float = Form(50.0, ge=0, le=100),
    score_threshold: Optional[float] = Form(None, ge=0, le=100),
    try_rotations: bool = Form(True),
    try_mirror: bool = Form(False),
    prefer_cv2: bool = Form(True),
):
    if id_regex:
        try:
            re.compile(id_regex)
        except re.error:
            raise HTTPException(400, "Invalid student ID pattern") from None
    front_bytes = read_upload(front)
    back_bytes = read_upload(back)
    read_upload(selfie)  # Accepted for compatibility; face verification is not implemented.
    return analyze_images(front_bytes, back_bytes, id_regex=id_regex,
                          conf_threshold=score_threshold if score_threshold is not None else conf_threshold,
                          try_rotations=try_rotations, try_mirror=try_mirror, prefer_cv2=prefer_cv2)


@app.post("/analyze_b64", response_model=AnalyzeResponse)
def analyze_base64(request: AnalyzeBase64Request):
    front = decode_image(request.front_b64)
    back = decode_image(request.back_b64)
    decode_image(request.selfie_b64)
    return analyze_images(front, back, conf_threshold=50.0)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000)
