"""
gallery/ai/smart_albums.py

Creates and refreshes smart/auto albums for a user:
  - Recently Uploaded (last 30 days)
  - Selfies
  - Group Photos
  - Scenery
  - Frequently Appearing Faces (people with >= 3 photos)
  - Favourites
"""
from django.utils import timezone
from datetime import timedelta


def build_smart_albums(user):
    """Create / refresh all smart albums for *user*."""
    from gallery.models import Photo, Album, Person

    _smart_album(user, 'Recently Uploaded',
                 Photo.objects.filter(
                     user=user,
                     upload_date__gte=timezone.now() - timedelta(days=30)
                 ))

    _smart_album(user, 'Selfies',
                 Photo.objects.filter(user=user, category='selfie'))

    _smart_album(user, 'Group Photos',
                 Photo.objects.filter(user=user, category='group'))

    _smart_album(user, 'Scenery',
                 Photo.objects.filter(user=user, category='scenery'))

    _smart_album(user, 'Favourites',
                 Photo.objects.filter(user=user, is_favourite=True))

    # People albums
    for person in Person.objects.filter(user=user, photo_count__gte=3):
        photo_ids = (
            person.face_encodings
            .values_list('photo_id', flat=True)
            .distinct()
        )
        _smart_album(
            user,
            f'People – {person.name}',
            Photo.objects.filter(id__in=photo_ids),
            album_type='person',
        )


def _smart_album(user, name, photo_qs, album_type='smart'):
    """Create or update one smart album."""
    from gallery.models import Album

    album, _ = Album.objects.get_or_create(
        user=user,
        name=name,
        defaults={'album_type': album_type},
    )
    album.album_type = album_type
    album.photos.set(photo_qs)
    first = photo_qs.first()
    if first:
        album.cover_photo = first
    album.save()
