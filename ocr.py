import io
import re
import logging
from typing import Union, Optional, Dict, Any, List, Tuple

from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import pytesseract

# Optional OpenCV acceleration
_cv2_available = False
try:
    import numpy as np
    import cv2
    _cv2_available = True
except Exception:
    _cv2_available = False

logger = logging.getLogger("ocr")
logging.basicConfig(level=logging.INFO)

# Exactly 7 digits, starting with 63/65/66/67/68/69
DEFAULT_ID_REGEX = r"(63|65|66|67|68|69)\d{5}"

# ------------ helpers ------------
def _safe_compile_regex(pattern: Optional[str]) -> re.Pattern:
    if not pattern:
        return re.compile(DEFAULT_ID_REGEX)
    try:
        return re.compile(pattern)
    except re.error:
        logger.warning("Invalid id_regex; using default")
        return re.compile(DEFAULT_ID_REGEX)

def _load_image(image: Union[str, bytes, Image.Image]) -> Image.Image:
    if isinstance(image, Image.Image):
        img = image
    elif isinstance(image, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image))
    elif isinstance(image, str):
        img = Image.open(image)
    else:
        raise ValueError("Unsupported image input type")
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img.convert("RGB")

def _resize_max(img: Image.Image, max_dim: int = 1600) -> Image.Image:
    w, h = img.size
    m = max(w, h)
    if m <= max_dim:
        return img
    s = max_dim / m
    return img.resize((int(w * s), int(h * s)), Image.LANCZOS)

def _detect_orientation(img: Image.Image) -> Tuple[Image.Image, int]:
    try:
        osd = pytesseract.image_to_osd(img)
        m = re.search(r"(?:Rotate:|Orientation in degrees:)\s*(\d+)", osd, re.I)
        if m:
            deg = int(m.group(1)) % 360
            if deg:
                logger.info("OSD rotate: %d°", deg)
                return img.rotate(-deg, expand=True), deg
    except Exception as e:
        logger.debug("OSD failed: %s", e)
    return img, 0

def _enhance_pillow(img: Image.Image) -> Image.Image:
    g = img.convert("L")
    g = g.filter(ImageFilter.MedianFilter(3))
    g = ImageEnhance.Contrast(g).enhance(1.45)
    g = ImageEnhance.Sharpness(g).enhance(1.2)
    return g  # keep grayscale for Tesseract

def _pil_to_cv2(img: Image.Image):
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def _cv2_preprocess(img_cv) -> Image.Image:
    # LAB + CLAHE (good on the green area)
    lab = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge([l, a, b])
    bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    return Image.fromarray(th)

def _likely_id_rois(img: Image.Image) -> List[Tuple[int, int, int, int]]:
    """Rectangles (x1,y1,x2,y2) focusing on right/lower area where the ID lives."""
    w, h = img.size
    boxes = [
        (int(0.52 * w), int(0.54 * h), int(0.97 * w), int(0.82 * h)),  # primary zone
        (int(0.48 * w), int(0.50 * h), int(0.98 * w), int(0.86 * h)),  # slightly bigger
        (int(0.55 * w), int(0.44 * h), int(0.98 * w), int(0.74 * h)),  # a bit higher
        (int(0.40 * w), int(0.50 * h), w, h),                          # lower-right half
        (int(0.55 * w), 0, w, h),                                      # right half
    ]
    # clamp
    return [(max(0,x1), max(0,y1), min(w,x2), min(h,y2)) for x1,y1,x2,y2 in boxes]

# OCR configs: fast → detailed
_OCR_CONFIGS = [
    r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789",
    r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789",
]

def _collect_candidates(img: Image.Image, id_pattern: re.Pattern, cfg: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=cfg)
    except Exception as e:
        logger.debug("image_to_data failed: %s", e)
        return out

    n = len(data.get("text", []))
    # token-level
    for i in range(n):
        t = (data["text"][i] or "").strip()
        if not t:
            continue
        digits = re.sub(r"\D", "", t)
        if not digits:
            continue
        try:
            conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", None, "") else 0.0
        except Exception:
            conf = 0.0
        if id_pattern.fullmatch(digits):
            out.append({"text": digits, "conf": conf})

    # line-level aggregation (handles token splits)
    try:
        keys = list(zip(data.get("block_num", []), data.get("par_num", []), data.get("line_num", [])))
        buf, confs, last = [], [], None
        for i in range(n):
            key = keys[i] if i < len(keys) else None
            if last is None:
                last = key
            if key != last:
                if buf:
                    line_digits = re.sub(r"\D", "", " ".join(buf))
                    for m in re.finditer(r"\d{7}", line_digits):
                        token = m.group(0)
                        if id_pattern.fullmatch(token):
                            avg = sum(confs) / max(1, len(confs))
                            out.append({"text": token, "conf": avg})
                buf, confs = [], []
                last = key
            token = (data["text"][i] or "").strip()
            if token:
                buf.append(token)
                try:
                    c = float(data["conf"][i]) if data["conf"][i] not in ("-1", None, "") else 0.0
                except Exception:
                    c = 0.0
                confs.append(c)
        if buf:
            line_digits = re.sub(r"\D", "", " ".join(buf))
            for m in re.finditer(r"\d{7}", line_digits):
                token = m.group(0)
                if id_pattern.fullmatch(token):
                    avg = sum(confs) / max(1, len(confs))
                    out.append({"text": token, "conf": avg})
    except Exception:
        pass

    return out

# ------------ public ------------
def analyze(
    image: Union[str, bytes, Image.Image],
    id_regex: Optional[str] = None,
    conf_threshold: float = 35.0,
    try_rotations: bool = True,
    try_mirror: bool = False,          # webcam: mirrors rarely help, save time
    prefer_cv2: bool = True,
) -> Dict[str, Any]:

    id_pattern = _safe_compile_regex(id_regex)
    pil = _load_image(image)
    pil = _resize_max(pil)
    pil, osd_rot = _detect_orientation(pil)

    angles = [0]
    if try_rotations:
        angles += [90, 270]  # 180 seldom helps on this card

    early_exit_conf = max(conf_threshold, 60.0)  # return as soon as we’re clearly confident
    attempts, all_cands = [], []

    for angle in angles:
        base = pil.rotate(-angle, expand=True) if angle else pil

        # build preprocess variants once per angle
        variants: List[Tuple[Image.Image, str]] = []
        if prefer_cv2 and _cv2_available:
            try:
                variants.append((_cv2_preprocess(_pil_to_cv2(base)), "cv2"))
            except Exception as e:
                logger.debug("cv2 preprocess failed: %s", e)
        # Pillow fallback/extra
        variants.append((_enhance_pillow(base), "pillow"))

        # Scan focused ROIs first (faster, cleaner); then whole frame
        rois = _likely_id_rois(base) + [(0, 0, base.size[0], base.size[1])]

        for (img_pre, tag) in variants:
            for (x1, y1, x2, y2) in rois:
                crop = img_pre.crop((x1, y1, x2, y2))
                for cfg in _OCR_CONFIGS:
                    cands = _collect_candidates(crop, id_pattern, cfg)
                    all_cands.extend(cands)
                    attempts.append({"angle": angle, "pre": tag, "cfg": cfg, "roi": (x1,y1,x2,y2), "found": len(cands)})
                    if cands:
                        best = max(cands, key=lambda c: c.get("conf", 0.0))
                        if best.get("conf", 0.0) >= early_exit_conf:
                            return {
                                "ok": True,
                                "score": float(best["conf"]),
                                "student_id": best["text"],
                                "name": None, "university": None, "grad_year": None,
                                "note": None,
                                "debug": {"attempts": attempts, "osd_rotation": osd_rot}
                            }

    if all_cands:
        best = max(all_cands, key=lambda c: c.get("conf", 0.0))
        ok = best.get("conf", 0.0) >= conf_threshold
        return {
            "ok": ok,
            "score": float(best.get("conf", 0.0)),
            "student_id": best["text"],
            "name": None, "university": None, "grad_year": None,
            "note": None if ok else "low_confidence",
            "debug": {"attempts": attempts, "osd_rotation": osd_rot}
        }

    return {
        "ok": False,
        "score": 0.0,
        "student_id": None,
        "name": None, "university": None, "grad_year": None,
        "note": "no_candidates",
        "debug": {"attempts": attempts, "osd_rotation": osd_rot}
    }

if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python ocr.py path/to/image [id_regex]")
        sys.exit(1)
    path = sys.argv[1]
    regex = sys.argv[2] if len(sys.argv) >= 3 else None
    print(json.dumps(analyze(path, id_regex=regex), indent=2))
