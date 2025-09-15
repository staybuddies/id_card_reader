# app.py
from __future__ import annotations
import base64
import time
from typing import Optional, Tuple, Dict, Any, List, Union

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from PIL import Image
import io
import logging
import re

# Import your OCR analyze function (expects image path/bytes/PIL.Image and returns dict with 'ok' and 'score')
from ocr import analyze

# -------------------------
# App & logging
# -------------------------
app = FastAPI(title="Student Card OCR", version="1.0.0")

# CORS for local dev (tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)


# -------------------------
# Response / Request models
# -------------------------
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
    front_b64: str
    back_b64: Optional[str] = None
    selfie_b64: Optional[str] = None


# -------------------------
# Helpers
# -------------------------
async def await_read_or_none(upload: Optional[UploadFile]) -> Optional[bytes]:
    """Safely await UploadFile.read() or return None if upload is None."""
    if upload is None:
        return None
    # UploadFile.read() is async
    return await upload.read()


def _to_bytes_from_b64(b64: Optional[str]) -> Optional[bytes]:
    if not b64:
        return None
    # Allow data URI style: "data:...;base64,...."
    try:
        payload = b64.split(",", 1)[-1]
        return base64.b64decode(payload)
    except Exception:
        raise ValueError("Invalid base64 image")


def _run_ocr_on_all(front_bytes: Optional[bytes],
                    back_bytes: Optional[bytes],
                    selfie_bytes: Optional[bytes]) -> Dict[str, Any]:
    """
    Run analyze() on available images and return merged result:
    - prefer front result for student_id, but pick the highest score among all image results.
    - return debug results for each image.
    """
    results = {}
    debug: Dict[str, Any] = {}

    def safe_call(img_bytes: Optional[bytes], label: str):
        if not img_bytes:
            return None
        try:
            res = analyze(img_bytes)
            debug[label] = res
            return res
        except Exception as e:
            logger.exception("OCR analyze failed for %s", label)
            debug[label] = {"error": str(e)}
            return None

    front_res = safe_call(front_bytes, "front")
    back_res = safe_call(back_bytes, "back")
    selfie_res = safe_call(selfie_bytes, "selfie")

    # Collect available results
    candidates = []
    for r, label in ((front_res, "front"), (back_res, "back"), (selfie_res, "selfie")):
        if not r:
            continue
        candidates.append({"label": label, "result": r, "score": float(r.get("score", 0.0))})

    # Pick best result by score (if any)
    if candidates:
        best_entry = max(candidates, key=lambda x: x["score"])
        best_res = best_entry["result"]
    else:
        best_res = None

    results["debug"] = debug
    results["best_overall"] = best_res
    return results


# Best-effort extractor helpers to produce student_id, name, university, grad_year
def _extract_fields_from_debug(debug: Dict[str, Any]) -> Dict[str, Any]:
    """
    Heuristics:
     - student_id: choose best 'best_text' (alnum) or highest-confidence all_candidates token that looks like an ID
     - name: look for token sequences with letters and spaces / capitalized words
     - university: look for tokens containing 'univ' / 'university' / 'college' (case-insensitive)
     - grad_year: 4-digit year between 1950 and 2100
    """
    student_id = None
    name = None
    university = None
    grad_year = None

    # Gather tokens from all candidate lists
    tokens: List[Dict[str, Any]] = []
    for label, val in debug.items():
        if not isinstance(val, dict):
            continue
        ac = val.get("all_candidates")
        if isinstance(ac, list):
            for c in ac:
                tokens.append({**c, "source": label})
        bt = val.get("best_text")
        if bt:
            tokens.append({"text": bt, "conf": float(val.get("confidence", val.get("score", 0.0))), "source": label})

    # Normalize token text and sort by confidence
    for t in tokens:
        t["text_norm"] = (t.get("text") or "").strip()

    tokens = [t for t in tokens if t.get("text_norm")]
    tokens.sort(key=lambda x: float(x.get("conf", 0.0)), reverse=True)

    # Student ID heuristic: alphanumeric tokens (with optional hyphen) length 4..20
    id_re = re.compile(r"^[A-Z0-9\-]{4,20}$", flags=re.IGNORECASE)
    for t in tokens:
        txt = t["text_norm"]
        if id_re.match(txt):
            student_id = txt
            break

    # University heuristic: token containing 'univ' or 'college' or 'faculty'
    uni_keywords = re.compile(r"(univ|college|faculty|institute)", flags=re.IGNORECASE)
    for t in tokens:
        if uni_keywords.search(t["text_norm"]):
            university = t["text_norm"]
            break

    # Name heuristic: multi-word or capitalized patterns
    name_candidate = None
    for t in tokens:
        txt = t["text_norm"]
        if sum(1 for ch in txt if ch.isalpha()) < 2:
            continue
        if " " in txt and len(txt) > 4:
            name_candidate = txt
            break
        if re.search(r"[A-Z][a-z]+", txt):
            name_candidate = txt
            break
    if name_candidate:
        name = name_candidate

    # grad_year heuristic: find 4-digit number between 1950..2100
    year_re = re.compile(r"\b(19[5-9]\d|20[0-9]{2}|2100)\b")
    for t in tokens:
        m = year_re.search(t["text_norm"])
        if m:
            try:
                year = int(m.group(0))
                grad_year = year
                break
            except Exception:
                pass

    return {"student_id": student_id, "name": name, "university": university, "grad_year": grad_year}


# -------------------------
# Routes
# -------------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_multipart(
    request: Request,
    front: UploadFile = File(..., description="Front side image file"),
    back: UploadFile = File(None),
    selfie: UploadFile = File(None),
):
    """
    Upload files as multipart/form-data.
    curl -F front=@IMG_1160.jpeg http://localhost:8000/analyze
    """
    t0 = time.time()
    front_bytes = None
    back_bytes = None
    selfie_bytes = None
    try:
        # Safely await only when UploadFile exists
        front_bytes = await await_read_or_none(front)
        back_bytes = await await_read_or_none(back)
        selfie_bytes = await await_read_or_none(selfie)

        merged = _run_ocr_on_all(front_bytes, back_bytes, selfie_bytes)
        debug = merged.get("debug", {})

        best_overall = merged.get("best_overall")
        if isinstance(best_overall, dict) and best_overall.get("score") is not None:
            ok = bool(best_overall.get("ok", False))
            score = float(best_overall.get("score", 0.0))
        else:
            front_dbg = debug.get("front") if debug else None
            if front_dbg and isinstance(front_dbg, dict):
                score = float(front_dbg.get("score", 0.0))
                ok = bool(front_dbg.get("ok", False))
            else:
                ok = False
                score = 0.0

        fields = _extract_fields_from_debug(debug)

        resp = {
            "ok": bool(ok),
            "score": float(score),
            "student_id": fields.get("student_id"),
            "name": fields.get("name"),
            "university": fields.get("university"),
            "grad_year": fields.get("grad_year"),
            "note": None,
            "debug": debug,
        }
        return resp
    except Exception as e:
        logger.exception("analyze endpoint failed")
        # Return 400 so client knows this was a request-level problem
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        dt = (time.time() - t0) * 1000
        try:
            print(f"[ML] /analyze done in {dt:.0f} ms; front={len(front_bytes) if front_bytes else 0} bytes")
        except Exception:
            pass


@app.post("/analyze_b64", response_model=AnalyzeResponse)
def analyze_base64(req: AnalyzeBase64Request):
    """Alternative: send base64 images in JSON."""
    t0 = time.time()
    try:
        front_bytes = _to_bytes_from_b64(req.front_b64)
        back_bytes = _to_bytes_from_b64(req.back_b64) if req.back_b64 else None
        selfie_bytes = _to_bytes_from_b64(req.selfie_b64) if req.selfie_b64 else None

        merged = _run_ocr_on_all(front_bytes, back_bytes, selfie_bytes)
        debug = merged.get("debug", {})

        best_overall = merged.get("best_overall")
        if isinstance(best_overall, dict) and best_overall.get("score") is not None:
            ok = bool(best_overall.get("ok", False))
            score = float(best_overall.get("score", 0.0))
        else:
            front_dbg = debug.get("front") if debug else None
            if front_dbg and isinstance(front_dbg, dict):
                score = float(front_dbg.get("score", 0.0))
                ok = bool(front_dbg.get("ok", False))
            else:
                ok = False
                score = 0.0

        fields = _extract_fields_from_debug(debug)
        resp = {
            "ok": bool(ok),
            "score": float(score),
            "student_id": fields.get("student_id"),
            "name": fields.get("name"),
            "university": fields.get("university"),
            "grad_year": fields.get("grad_year"),
            "note": None,
            "debug": debug,
        }
        return resp
    except ValueError as e:
        logger.exception("Invalid input")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("analyze_b64 failed")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        dt = (time.time() - t0) * 1000
        try:
            print(f"[ML] /analyze_b64 done in {dt:.0f} ms")
        except Exception:
            pass


# -------------------------
# CLI dev runner
# -------------------------
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
