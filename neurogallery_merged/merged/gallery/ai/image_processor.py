"""
gallery/ai/image_processor.py

Called right after a Photo is saved.
  1. Generates a thumbnail.
  2. Reads image dimensions / file size.
  3. Runs face detection.
  4. Persists FaceEncoding records (JSON).
  5. Marks photo as ai_processed.
"""
import json
import logging
import os
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from django.core.files.base import ContentFile
from django.conf import settings

from .face_detector import detect_and_encode, crop_face_thumbnail, categorise_photo

logger = logging.getLogger(__name__)

THUMB_SIZE = (400, 400)


def make_thumbnail(photo) -> None:
    """Create a 400×400 JPEG thumbnail and update photo.thumbnail."""
    try:
        img = PILImage.open(photo.image.path).convert('RGB')
        img.thumbnail(THUMB_SIZE, PILImage.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=80)
        buf.seek(0)

        thumb_name = f'thumbnails/thumb_{Path(photo.image.name).stem}.jpg'
        thumb_path = os.path.join(str(settings.MEDIA_ROOT), thumb_name)
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, 'wb') as f:
            f.write(buf.read())

        from gallery.models import MediaFile
        photo.thumbnail = MediaFile(thumb_name)
    except Exception as exc:
        logger.error('Thumbnail creation failed for photo %s: %s', photo.id, exc)


def read_image_meta(photo) -> None:
    """Read width, height, file_size and store on the photo instance."""
    try:
        img = PILImage.open(photo.image.path)
        photo.width, photo.height = img.size
        photo.file_size = photo.image.size
    except Exception as exc:
        logger.error('Meta read failed: %s', exc)


def process_photo(photo) -> None:
    """
    Full AI processing pipeline for a single Photo (JSON edition).
    Safe to call multiple times (idempotent via ai_processed flag).
    """
    from gallery.models import FaceEncoding, MediaFile

    if photo.ai_processed:
        return

    image_path = photo.image.path
    if not image_path or not os.path.exists(image_path):
        logger.warning('Image file not found for photo %s: %s', photo.id, image_path)
        return

    # 1. Thumbnail
    make_thumbnail(photo)

    # 2. Image meta
    read_image_meta(photo)

    # 3. Face detection + embeddings
    face_data = detect_and_encode(image_path)
    photo.face_count = len(face_data)
    photo.category   = categorise_photo(len(face_data))

    # 4. Save FaceEncoding records (JSON)
    for fd in face_data:
        fe = FaceEncoding(
            photo_id    = photo.id,
            encoding    = json.dumps(fd['encoding']),
            face_index  = fd['face_index'],
            confidence  = fd['confidence'],
            top         = fd['location'][0],
            right       = fd['location'][1],
            bottom      = fd['location'][2],
            left        = fd['location'][3],
        )
        fe.save()

        # Save the face crop image
        face_img_content = crop_face_thumbnail(image_path, fd['location'])
        if face_img_content:
            face_img_name = f'faces/face_{photo.id}_{fd["face_index"]}.jpg'
            face_img_path = os.path.join(str(settings.MEDIA_ROOT), face_img_name)
            os.makedirs(os.path.dirname(face_img_path), exist_ok=True)
            with open(face_img_path, 'wb') as f:
                for chunk in face_img_content.chunks():
                    f.write(chunk)
            fe.face_image = MediaFile(face_img_name)
            fe.save(update_fields=['face_image'])

    # 5. Mark done
    photo.ai_processed = True
    photo.save(update_fields=[
        'thumbnail', 'width', 'height', 'file_size',
        'face_count', 'category', 'ai_processed',
    ])
    logger.info('AI processing complete for photo %s (%d faces)', photo.id, len(face_data))
