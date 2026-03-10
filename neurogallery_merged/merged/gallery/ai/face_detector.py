"""
gallery/ai/face_detector.py

Face detection using OpenCV Haar cascades (no cmake/dlib needed).
Uses MULTIPLE cascades (frontal, profile) and rotated image variants
for better detection of tilted / side-facing people.

Falls back to PIL-only skin-colour detection if cv2 is unavailable.
"""
import logging
import numpy as np
from io import BytesIO

from PIL import Image as PILImage
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
    logger.info("opencv-python loaded OK: %s", cv2.__version__)
except ImportError:
    CV2_AVAILABLE = False
    logger.error("opencv-python not installed. Falling back to PIL-only detection.")

FACE_SIZE = 64
EMBED_DIM = 128


# ── Public API ────────────────────────────────────────────────────────────────

def detect_and_encode(image_path: str) -> list:
    """
    Detect faces and return a list of dicts::

        [{'encoding': [...128 floats...], 'face_index': 0,
          'location': [top, right, bottom, left], 'confidence': 0.9}, ...]
    """
    if CV2_AVAILABLE:
        try:
            return _opencv_detect(image_path)
        except Exception as exc:
            logger.error("opencv detect failed for %s: %s", image_path, exc)

    # PIL + numpy + scipy fallback
    try:
        return _pil_detect(image_path)
    except Exception as exc:
        logger.error("PIL detect failed for %s: %s", image_path, exc)
    return []


# ── OpenCV engine (primary) ───────────────────────────────────────────────────

def _load_cascades():
    """Load all available Haar cascades for face detection."""
    cascade_files = [
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt.xml",
        "haarcascade_frontalface_alt2.xml",
        "haarcascade_profileface.xml",
    ]
    cascades = []
    for f in cascade_files:
        try:
            c = cv2.CascadeClassifier(cv2.data.haarcascades + f)
            if not c.empty():
                cascades.append(c)
        except Exception:
            pass
    return cascades


def _detect_in_gray(cascades, img_gray):
    """Run all cascades on a grayscale image and deduplicate bounding boxes."""
    all_faces = []
    seen = []
    for cascade in cascades:
        faces = cascade.detectMultiScale(
            img_gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(20, 20),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        if len(faces) == 0:
            continue
        for (x, y, w, h) in faces:
            cx, cy = x + w // 2, y + h // 2
            duplicate = any(
                abs(cx - px) < w * 0.4 and abs(cy - py) < h * 0.4
                for (px, py) in seen
            )
            if not duplicate:
                all_faces.append((x, y, w, h))
                seen.append((cx, cy))
    return all_faces


def _opencv_detect(image_path: str) -> list:
    """Multi-cascade, multi-rotation face detection using OpenCV."""
    cascades = _load_cascades()
    if not cascades:
        logger.warning("No Haar cascade XML files found in opencv data directory.")
        return []

    # Load image
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        pil = PILImage.open(image_path).convert("RGB")
        img_bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    h0, w0 = img_bgr.shape[:2]

    # Downscale very large images to prevent memory errors during rotation
    MAX_DIM = 1280
    if max(h0, w0) > MAX_DIM:
        scale = MAX_DIM / max(h0, w0)
        img_bgr = cv2.resize(img_bgr, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
        h0, w0 = img_bgr.shape[:2]

    # Upscale tiny images
    if max(h0, w0) < 200:
        img_bgr = cv2.resize(img_bgr, (w0 * 3, h0 * 3))

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    img_gray = cv2.equalizeHist(img_gray)

    found_faces = []

    # Original orientation
    for (x, y, w, h) in _detect_in_gray(cascades, img_gray):
        found_faces.append({"box": (x, y, w, h)})

    # Try rotated variants to catch tilted / profile faces
    img_h, img_w = img_gray.shape
    center = (img_w // 2, img_h // 2)

    for angle in [90, 180, 270, -30, 30, -45, 45, -60, 60]:
        M     = cv2.getRotationMatrix2D(center, angle, 1.0)
        M_inv = cv2.getRotationMatrix2D(center, -angle, 1.0)
        rotated = cv2.warpAffine(img_gray, M, (img_w, img_h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)
        rot_faces = _detect_in_gray(cascades, rotated)
        for (x, y, w, h) in rot_faces:
            bc = np.array([x + w / 2, y + h / 2, 1.0])
            oc = M_inv @ bc
            ox = max(0, min(img_w - w, int(oc[0] - w / 2)))
            oy = max(0, min(img_h - h, int(oc[1] - h / 2)))
            cx, cy = ox + w // 2, oy + h // 2
            dup = any(
                abs(cx - (f["box"][0] + f["box"][2] // 2)) < w * 0.4 and
                abs(cy - (f["box"][1] + f["box"][3] // 2)) < h * 0.4
                for f in found_faces
            )
            if not dup:
                found_faces.append({"box": (ox, oy, w, h)})

    if not found_faces:
        logger.info("No faces detected in %s (tried all rotations).", image_path)
        return []

    results = []
    for idx, face in enumerate(found_faces):
        x, y, w, h = face["box"]
        top, right, bottom, left = y, x + w, y + h, x
        face_crop = img_gray[max(0, y): min(img_h, y + h),
                              max(0, x): min(img_w, x + w)]
        face_resized = cv2.resize(face_crop, (FACE_SIZE, FACE_SIZE))
        hist = cv2.calcHist([face_resized], [0], None, [EMBED_DIM], [0, 256]).flatten()
        norm = np.linalg.norm(hist)
        embedding = (hist / norm).tolist() if norm > 0 else hist.tolist()
        results.append({
            "encoding":   embedding,
            "face_index": idx,
            "location":   [top, right, bottom, left],
            "confidence": 0.9,
        })

    logger.info("Detected %d face(s) in %s", len(results), image_path)
    return results


# ── PIL-only fallback engine ──────────────────────────────────────────────────

def _pil_detect(image_path: str) -> list:
    """
    Skin-colour blob detection using only PIL + numpy + scipy.
    Requires no OpenCV. Less accurate but works on any platform.
    """
    try:
        from scipy import ndimage
    except ImportError:
        logger.warning("scipy not available – PIL fallback detection disabled.")
        return []

    img = PILImage.open(image_path).convert("RGB")
    w, h = img.size
    scale = min(1.0, 600 / max(w, h))
    img_s = img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)
    arr   = np.array(img_s, dtype=np.float32)

    R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)

    # Chai & Ngan skin-colour rule (RGB space)
    skin = (
        (R > 95) & (G > 40) & (B > 20) &
        ((mx - mn) > 15) & (R > G) & (R > B) &
        (np.abs(R.astype(np.int32) - G.astype(np.int32)) > 15)
    ).astype(np.uint8)

    labeled, n = ndimage.label(skin)
    if n == 0:
        return []

    sw, sh = img_s.size
    results, idx = [], 0
    min_px = sw * sh * 0.003
    max_px = sw * sh * 0.40

    for label in range(1, n + 1):
        size_ = int((labeled == label).sum())
        if not (min_px < size_ < max_px):
            continue
        rows, cols = np.where(labeled == label)
        y1, y2 = int(rows.min()), int(rows.max())
        x1, x2 = int(cols.min()), int(cols.max())
        bh, bw  = y2 - y1, x2 - x1
        if bw < 15 or bh < 15:
            continue
        if not (0.6 < bh / bw < 2.5):
            continue
        # Scale back to original coords
        oy1, oy2 = int(y1 / scale), int(y2 / scale)
        ox1, ox2 = int(x1 / scale), int(x2 / scale)
        face_crop = img.crop((ox1, oy1, ox2, oy2)).convert("L").resize((FACE_SIZE, FACE_SIZE))
        face_arr  = np.array(face_crop, dtype=np.float32)
        hist, _   = np.histogram(face_arr, bins=EMBED_DIM, range=(0, 256))
        hist_f    = hist.astype(np.float32)
        norm      = np.linalg.norm(hist_f)
        embedding = (hist_f / norm).tolist() if norm > 0 else hist_f.tolist()
        results.append({
            "encoding":   embedding,
            "face_index": idx,
            "location":   [oy1, ox2, oy2, ox1],
            "confidence": 0.7,
        })
        idx += 1

    logger.info("PIL detect: %d face(s) in %s", len(results), image_path)
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def crop_face_thumbnail(image_path: str, location: list, padding: int = 20):
    """Crop face region and return a Django ContentFile (JPEG)."""
    try:
        top, right, bottom, left = location
        img  = PILImage.open(image_path).convert("RGB")
        w, h = img.size
        face_img = img.crop((
            max(0, left   - padding),
            max(0, top    - padding),
            min(w, right  + padding),
            min(h, bottom + padding),
        )).resize((120, 120))
        buf = BytesIO()
        face_img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return ContentFile(buf.read(), name="face.jpg")
    except Exception as exc:
        logger.error("crop_face_thumbnail failed: %s", exc)
        return None


def categorise_photo(face_count: int) -> str:
    if face_count == 0:
        return "scenery"
    if face_count == 1:
        return "selfie"
    return "group"
