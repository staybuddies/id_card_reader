from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

import uvicorn
import ocr  # your ocr.py (the analyze(...) function)

app = FastAPI(title="Student ID OCR")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze(
    # files (front required)
    front: UploadFile = File(...),
    back: Optional[UploadFile] = File(None),
    selfie: Optional[UploadFile] = File(None),

    # optional knobs — all defaulted so we never do float(None)
    id_regex: Optional[str] = Form(None),
    conf_threshold: float = Form(50.0),

    # accept both names to be future-proof (some clients use score_threshold)
    score_threshold: Optional[float] = Form(None),

    try_rotations: bool = Form(True),
    try_mirror: bool = Form(True),
    prefer_cv2: bool = Form(True),
):
    try:
        # prefer explicitly provided score_threshold over conf_threshold if present
        if score_threshold is not None:
            conf_threshold = float(score_threshold)

        # read the required front image bytes
        front_bytes = await front.read()

        # We only need 'front' for the current implementation.
        # (You can stitch logic later to use 'back'/'selfie' if needed.)
        result = ocr.analyze(
            image=front_bytes,
            id_regex=id_regex,
            conf_threshold=conf_threshold,
            try_rotations=try_rotations,
            try_mirror=try_mirror,
            prefer_cv2=prefer_cv2,
        )

        # result already shaped like:
        # { "ok": bool, "score": float, "student_id": str|None, "name":..., "university":..., "grad_year":..., "note":..., "debug": ... }
        # Your Java DTO ignores unknown fields due to @JsonIgnoreProperties, so debug is fine.
        return JSONResponse(result)

    except Exception as e:
        # Log in real code; return safe message
        raise HTTPException(status_code=500, detail="internal inference error")

if __name__ == "__main__":
    # On the SAME machine as Spring, binding to 127.0.0.1 is perfect.
    # If you need to hit it from other devices on the LAN, use host="0.0.0.0".
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
