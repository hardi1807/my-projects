"""
gallery/ai/duplicate_detector.py

Uses perceptual hashing (pHash) via the `imagehash` library to find
near-duplicate images for a given user.
"""
import logging

logger = logging.getLogger(__name__)

try:
    import imagehash
    from PIL import Image as PILImage
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    logger.warning("imagehash not installed – duplicate detection disabled.")


HASH_THRESHOLD = 10   # Hamming distance; lower = more similar


def compute_phash(image_path: str) -> str | None:
    """Return the perceptual hash string for an image, or None on error."""
    if not IMAGEHASH_AVAILABLE:
        return None
    try:
        return str(imagehash.phash(PILImage.open(image_path)))
    except Exception as exc:
        logger.error("pHash failed for %s: %s", image_path, exc)
        return None


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two hexadecimal hash strings."""
    if not IMAGEHASH_AVAILABLE:
        return 999
    try:
        return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
    except Exception:
        return 999


def find_duplicates_for_user(user) -> list[tuple]:
    """
    Scan all Photos of *user*, compute pHash for each, compare pairwise.
    Returns [(photo_a, photo_b, similarity_score), ...].
    Also creates/updates PhotoSimilarity rows.
    """
    from gallery.models import Photo, PhotoSimilarity

    if not IMAGEHASH_AVAILABLE:
        return []

    photos = list(Photo.objects.filter(user=user))
    hashes = {}
    for photo in photos:
        try:
            hashes[photo.id] = compute_phash(photo.image.path)
        except Exception:
            hashes[photo.id] = None

    duplicates = []
    ids = list(hashes.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            ha = hashes[ids[i]]
            hb = hashes[ids[j]]
            if ha is None or hb is None:
                continue
            dist  = hamming_distance(ha, hb)
            score = max(0.0, 1.0 - dist / 64.0)
            if dist <= HASH_THRESHOLD:
                pa = next(p for p in photos if p.id == ids[i])
                pb = next(p for p in photos if p.id == ids[j])
                PhotoSimilarity.objects.update_or_create(
                    photo_a=pa, photo_b=pb,
                    defaults={'score': score},
                )
                pa.is_duplicate = True
                pa.save(update_fields=['is_duplicate'])
                pb.is_duplicate = True
                pb.save(update_fields=['is_duplicate'])
                duplicates.append((pa, pb, score))
    return duplicates
