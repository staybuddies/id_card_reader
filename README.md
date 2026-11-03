# StayBuddies student-card OCR

FastAPI service called by the Spring Boot backend. It extracts student IDs from
card images with Tesseract. Email ownership and student verification decisions
belong to the backend. This service does not verify faces or authenticate users.

## Run locally

Use Python 3.10–3.12 and install Tesseract (`brew install tesseract` on macOS).

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

`python app.py` and the legacy `python server.py` run the same application.
The service binds to loopback by default. Keep it private behind the backend;
it has no API authentication or rate limiting. Apply request-body and concurrency
limits at the reverse proxy before exposing it to a network.

## API

- `GET /health`: process liveness.
- `POST /analyze`: multipart `front` required; `back` and `selfie` optional.
- `POST /analyze_b64`: JSON `front_b64` required; `back_b64` and `selfie_b64` optional.
- `GET /docs`: interactive API schema.

```sh
curl -F front=@student-card.jpg http://127.0.0.1:8000/analyze
```

JPEG, PNG, and WebP are supported, with an 8 MiB / 12 megapixel limit per image.
Base64 data URIs are accepted. Invalid images return 400, unsupported image formats
415, excessive size 413, invalid form options 422, and processing failures 500.
The response includes `ok`, confidence `score` (0–100), `student_id`, optional
metadata, `note`, and diagnostic `debug`. Selfies are accepted for compatibility
but never used as evidence of a student ID. The front card is preferred; a valid
back-card result is used when the front has no valid ID.

The multipart endpoint supports `conf_threshold` (default 50), its legacy alias
`score_threshold`, `id_regex`, `try_rotations`, `try_mirror`, and `prefer_cv2`.
The default ID pattern is specific to the original institution; configure it
before using another institution. Do not treat an OCR confidence score as proof
of identity.

Browser CORS is disabled by default. Set `OCR_ALLOWED_ORIGINS` to an explicit
comma-separated list if needed. Uvicorn does not load `.env` automatically;
export variables in the shell or use `uvicorn --env-file .env app:app`.

## Verify

```sh
python -m unittest discover -s tests -v
pip-audit -r requirements.txt
```

Tests use generated images and stub Tesseract for API regressions. They cover
result propagation, invalid uploads, strict base64, limits, and safe errors.
Real image accuracy still needs an institution-approved, consented test set.
