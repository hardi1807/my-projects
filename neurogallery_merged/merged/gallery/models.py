"""
gallery/models.py
=================
JSON-backed model classes for NeuroGallery.

Django's built-in User / Session / Auth models still use SQLite
(required for Django's auth machinery to work).

All app-specific data — Photo, Album, Person, Tag,
FaceEncoding, UserProfile, PhotoSimilarity — is stored in
plain JSON files via gallery.json_db.
"""

import os
import json
from datetime import datetime, date

from django.conf import settings
from django.utils import timezone

from . import json_db as db


# ─── Media file proxy ─────────────────────────────────────────────────────────

class MediaFile:
    """
    Lightweight proxy that mimics Django's ImageField/FileField interface.
    Stores just the relative path; computes absolute path/url on demand.
    """

    def __init__(self, name: str = ''):
        self.name = name or ''

    # ── Path helpers ──────────────────────────────────────────────────────────

    @property
    def path(self) -> str:
        if not self.name:
            return ''
        return os.path.join(str(settings.MEDIA_ROOT), self.name)

    @property
    def url(self) -> str:
        if not self.name:
            return ''
        return settings.MEDIA_URL + self.name

    @property
    def size(self) -> int:
        p = self.path
        if p and os.path.exists(p):
            return os.path.getsize(p)
        return 0

    # ── Django ImageField API ─────────────────────────────────────────────────

    def delete(self, save: bool = True) -> None:
        """Delete the physical file."""
        if self.name and os.path.exists(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        self.name = ''

    def save(self, name: str, content, save: bool = True) -> None:
        """Save content to media storage and update self.name."""
        from django.core.files.storage import default_storage
        self.name = default_storage.save(name, content)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def __bool__(self):
        return bool(self.name)

    def __str__(self):
        return self.name


# ─── QuerySet-like helper ─────────────────────────────────────────────────────

class JsonQuerySet:
    """
    Lazy, chainable wrapper around a list of raw JSON dicts.
    Mimics the parts of Django's QuerySet used in views.py.
    """

    def __init__(self, records: list, model_cls):
        self._records = records
        self._model_cls = model_cls

    # ── Filtering ─────────────────────────────────────────────────────────────

    def filter(self, **kwargs):
        results = list(self._records)
        for key, val in kwargs.items():
            results = self._apply_filter(results, key, val)
        return JsonQuerySet(results, self._model_cls)

    def exclude(self, **kwargs):
        results = list(self._records)
        for key, val in kwargs.items():
            results = [r for r in results if not self._match(r, key, val)]
        return JsonQuerySet(results, self._model_cls)

    @staticmethod
    def _match(record: dict, key: str, val) -> bool:
        """Match a single key-value against a record dict (supports __ lookups)."""
        if '__' in key:
            parts = key.split('__', 1)
            field, lookup = parts[0], parts[1]
            field_val = record.get(field, '')
            if lookup == 'icontains':
                return str(val).lower() in str(field_val).lower()
            elif lookup == 'contains':
                return str(val) in str(field_val)
            elif lookup == 'gte':
                return field_val is not None and str(field_val) >= str(val)
            elif lookup == 'lte':
                return field_val is not None and str(field_val) <= str(val)
            elif lookup == 'gt':
                return field_val is not None and str(field_val) > str(val)
            elif lookup == 'lt':
                return field_val is not None and str(field_val) < str(val)
            elif lookup == 'in':
                return field_val in val
            elif lookup == 'isnull':
                return (field_val is None) == val
            elif lookup == 'date__gte':
                # upload_date__date__gte - compare date portion
                if field_val:
                    rec_date = str(field_val)[:10]
                    return rec_date >= str(val)
                return False
            elif lookup == 'date__lte':
                if field_val:
                    rec_date = str(field_val)[:10]
                    return rec_date <= str(val)
                return False
            else:
                return record.get(key) == val
        else:
            # Handle Django user object vs user_id
            if key == 'user':
                return record.get('user_id') == val.id
            if key == 'person':
                return record.get('person_id') == (val.id if val else None)
            if key == 'photo':
                return record.get('photo_id') == (val.id if val else None)
            if key == 'pk' or key == 'id':
                return record.get('id') == val
            return record.get(key) == val

    @staticmethod
    def _apply_filter(records: list, key: str, val) -> list:
        return [r for r in records if JsonQuerySet._match(r, key, val)]

    # ── Ordering ──────────────────────────────────────────────────────────────

    def order_by(self, *fields):
        results = list(self._records)
        for field in reversed(fields):
            reverse = field.startswith('-')
            f = field.lstrip('-')
            results.sort(
                key=lambda r: (r.get(f) is None, r.get(f) or ''),
                reverse=reverse
            )
        return JsonQuerySet(results, self._model_cls)

    # ── Slicing ───────────────────────────────────────────────────────────────

    def __getitem__(self, key):
        sliced = self._records[key]
        if isinstance(key, slice):
            return JsonQuerySet(sliced, self._model_cls)
        return self._model_cls._from_dict(sliced)

    def __iter__(self):
        for r in self._records:
            yield self._model_cls._from_dict(r)

    def __len__(self):
        return len(self._records)

    # ── Aggregation ───────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._records)

    def exists(self) -> bool:
        return bool(self._records)

    def first(self):
        if self._records:
            return self._model_cls._from_dict(self._records[0])
        return None

    def last(self):
        if self._records:
            return self._model_cls._from_dict(self._records[-1])
        return None

    def distinct(self):
        seen = set()
        unique = []
        for r in self._records:
            if r['id'] not in seen:
                seen.add(r['id'])
                unique.append(r)
        return JsonQuerySet(unique, self._model_cls)

    def values_list(self, field: str, flat: bool = False):
        if flat:
            return [r.get(field) for r in self._records]
        return [(r.get(field),) for r in self._records]

    def update(self, **kwargs):
        """Bulk update matching records."""
        for r in self._records:
            db.update_record(self._model_cls._collection, r['id'], **kwargs)
        return len(self._records)

    def delete(self):
        """Bulk delete matching records."""
        for r in self._records:
            db.delete_record(self._model_cls._collection, r['id'])
        return len(self._records)

    def annotate(self, **annotations):
        """Attach computed annotations to each record (returns self for chaining)."""
        for key, expr in annotations.items():
            for r in self._records:
                r[key] = expr(r)
        return self

    def select_related(self, *args):
        """No-op: JSON models load relations lazily. Returns self."""
        return self

    def all(self):
        return JsonQuerySet(list(self._records), self._model_cls)


# ─── Base Manager ─────────────────────────────────────────────────────────────

class JsonManager:
    """Descriptor that provides a Django-style `objects` manager on model classes."""

    def __init__(self, model_cls):
        self._model_cls = model_cls

    def all(self):
        return JsonQuerySet(db.get_all(self._model_cls._collection), self._model_cls)

    def filter(self, **kwargs):
        return self.all().filter(**kwargs)

    def exclude(self, **kwargs):
        return self.all().exclude(**kwargs)

    def get(self, **kwargs):
        results = self.filter(**kwargs)
        if results.count() == 0:
            raise LookupError(f'{self._model_cls.__name__} matching query does not exist.')
        if results.count() > 1:
            raise LookupError(f'Multiple {self._model_cls.__name__} objects returned.')
        return results.first()

    def get_or_create(self, defaults=None, **kwargs):
        try:
            obj = self.get(**kwargs)
            return obj, False
        except LookupError:
            create_data = dict(kwargs)
            if defaults:
                create_data.update(defaults)
            obj = self._model_cls(**create_data)
            obj.save()
            return obj, True

    def create(self, **kwargs):
        obj = self._model_cls(**kwargs)
        obj.save()
        return obj

    def count(self, **kwargs):
        if kwargs:
            return self.filter(**kwargs).count()
        return db.count(self._model_cls._collection)

    def exists(self, **kwargs):
        return self.filter(**kwargs).exists()


# ─── M2M Manager helpers ──────────────────────────────────────────────────────

class TagM2M:
    """Manages the photo↔tag many-to-many via tag_ids list on a Photo record."""

    def __init__(self, photo):
        self._photo = photo

    def all(self):
        tags = [
            Tag._from_dict(db.get_by_id('tags', tid))
            for tid in self._photo.tag_ids
            if db.get_by_id('tags', tid)
        ]
        return tags

    def set(self, tag_objs):
        self._photo.tag_ids = [t.id for t in tag_objs]
        if self._photo.id:
            db.update_record('photos', self._photo.id, tag_ids=self._photo.tag_ids)

    def add(self, *tag_objs):
        for t in tag_objs:
            if t.id not in self._photo.tag_ids:
                self._photo.tag_ids.append(t.id)
        if self._photo.id:
            db.update_record('photos', self._photo.id, tag_ids=self._photo.tag_ids)

    def remove(self, *tag_objs):
        ids = {t.id for t in tag_objs}
        self._photo.tag_ids = [tid for tid in self._photo.tag_ids if tid not in ids]
        if self._photo.id:
            db.update_record('photos', self._photo.id, tag_ids=self._photo.tag_ids)


class AlbumPhotoM2M:
    """Manages the album↔photo many-to-many via photo_ids list on an Album record."""

    def __init__(self, album):
        self._album = album

    def all(self):
        photos = [
            Photo._from_dict(db.get_by_id('photos', pid))
            for pid in self._album.photo_ids
            if db.get_by_id('photos', pid)
        ]
        return JsonQuerySet([p._to_dict() for p in photos], Photo)

    def add(self, *photo_objs):
        for p in photo_objs:
            if p.id not in self._album.photo_ids:
                self._album.photo_ids.append(p.id)
        if self._album.id:
            db.update_record('albums', self._album.id, photo_ids=self._album.photo_ids)

    def set(self, photo_objs):
        self._album.photo_ids = [p.id for p in photo_objs]
        if self._album.id:
            db.update_record('albums', self._album.id, photo_ids=self._album.photo_ids)


class FaceEncodingRevFK:
    """Reverse FK: photo.face_encodings — FaceEncoding records belonging to a photo."""

    def __init__(self, photo):
        self._photo = photo

    def all(self):
        records = db.filter_records('face_encodings', photo_id=self._photo.id)
        return JsonQuerySet(records, FaceEncoding)

    def select_related(self, *args):
        return self

    def filter(self, **kwargs):
        return self.all().filter(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 1. UserProfile
# ─────────────────────────────────────────────────────────────────────────────

class UserProfile:
    _collection = 'user_profiles'

    def __init__(self, **kw):
        self.id         = kw.get('id')
        self.user_id    = kw.get('user_id')
        self._user      = kw.get('_user')
        self.avatar     = MediaFile(kw.get('avatar', ''))
        self.bio        = kw.get('bio', '')
        self.dark_mode  = kw.get('dark_mode', False)
        self.created_at = kw.get('created_at', datetime.now().isoformat())

    @property
    def user(self):
        if self._user is None:
            from django.contrib.auth.models import User as DjangoUser
            self._user = DjangoUser.objects.get(id=self.user_id)
        return self._user

    @user.setter
    def user(self, u):
        self._user = u
        self.user_id = u.id if u else None

    def _to_dict(self) -> dict:
        return {
            'user_id':    self.user_id,
            'avatar':     self.avatar.name,
            'bio':        self.bio,
            'dark_mode':  self.dark_mode,
            'created_at': str(self.created_at),
        }

    @classmethod
    def _from_dict(cls, d: dict):
        obj = cls(**d)
        return obj

    def save(self, update_fields=None):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            to_save = {f: data[f] for f in update_fields} if update_fields else data
            db.update_record(self._collection, self.id, **to_save)

    def delete(self):
        if self.id:
            db.delete_record(self._collection, self.id)

    def __str__(self):
        return f'Profile – user_id={self.user_id}'

    objects = None  # set below


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tag
# ─────────────────────────────────────────────────────────────────────────────

class Tag:
    _collection = 'tags'

    def __init__(self, **kw):
        self.id             = kw.get('id')
        self.name           = kw.get('name', '')
        self.created_by_id  = kw.get('created_by_id')
        self._created_by    = kw.get('_created_by')

    @property
    def created_by(self):
        if self._created_by is None and self.created_by_id:
            from django.contrib.auth.models import User as DjangoUser
            self._created_by = DjangoUser.objects.get(id=self.created_by_id)
        return self._created_by

    @created_by.setter
    def created_by(self, u):
        self._created_by = u
        self.created_by_id = u.id if u else None

    def _to_dict(self) -> dict:
        return {
            'name':           self.name,
            'created_by_id':  self.created_by_id,
        }

    @classmethod
    def _from_dict(cls, d: dict):
        return cls(**d)

    def save(self):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            db.update_record(self._collection, self.id, **data)

    def delete(self):
        if self.id:
            db.delete_record(self._collection, self.id)

    def __str__(self):
        return self.name

    objects = None  # set below


# ─────────────────────────────────────────────────────────────────────────────
# 3. Photo
# ─────────────────────────────────────────────────────────────────────────────

class Photo:
    _collection = 'photos'

    CATEGORY_CHOICES = [
        ('selfie',  'Selfie'),
        ('group',   'Group Photo'),
        ('scenery', 'Scenery'),
        ('other',   'Other'),
    ]

    def __init__(self, **kw):
        self.id           = kw.get('id')
        self.user_id      = kw.get('user_id')
        self._user        = kw.get('_user')
        self.image        = MediaFile(kw.get('image', ''))
        self.thumbnail    = MediaFile(kw.get('thumbnail', ''))
        self.title        = kw.get('title', '')
        self.description  = kw.get('description', '')
        self.category     = kw.get('category', 'other')
        self.tag_ids      = kw.get('tag_ids', [])
        self.face_count   = kw.get('face_count', 0)
        self.is_favourite = kw.get('is_favourite', False)
        self.is_duplicate = kw.get('is_duplicate', False)
        self.upload_date  = kw.get('upload_date', datetime.now().isoformat())
        self.taken_date   = kw.get('taken_date')
        self.width        = kw.get('width')
        self.height       = kw.get('height')
        self.file_size    = kw.get('file_size')
        self.ai_processed = kw.get('ai_processed', False)

    # ── Relations ─────────────────────────────────────────────────────────────

    @property
    def user(self):
        if self._user is None and self.user_id:
            from django.contrib.auth.models import User as DjangoUser
            self._user = DjangoUser.objects.get(id=self.user_id)
        return self._user

    @user.setter
    def user(self, u):
        self._user = u
        self.user_id = u.id if u else None

    @property
    def tags(self):
        return TagM2M(self)

    @property
    def face_encodings(self):
        return FaceEncodingRevFK(self)

    # ── Serialization ─────────────────────────────────────────────────────────

    def _to_dict(self) -> dict:
        return {
            'user_id':      self.user_id,
            'image':        self.image.name,
            'thumbnail':    self.thumbnail.name if self.thumbnail else '',
            'title':        self.title,
            'description':  self.description,
            'category':     self.category,
            'tag_ids':      self.tag_ids,
            'face_count':   self.face_count,
            'is_favourite': self.is_favourite,
            'is_duplicate': self.is_duplicate,
            'upload_date':  str(self.upload_date),
            'taken_date':   str(self.taken_date) if self.taken_date else None,
            'width':        self.width,
            'height':       self.height,
            'file_size':    self.file_size,
            'ai_processed': self.ai_processed,
        }

    @classmethod
    def _from_dict(cls, d: dict):
        if d is None:
            return None
        return cls(**d)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, update_fields=None):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            to_save = {f: data[f] for f in update_fields} if update_fields else data
            db.update_record(self._collection, self.id, **to_save)

    def delete(self):
        if self.id:
            db.delete_record(self._collection, self.id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_filename(self):
        return os.path.basename(self.image.name)

    def __str__(self):
        return f'{self.title or self.image.name} (user_id={self.user_id})'

    objects = None  # set below


# ─────────────────────────────────────────────────────────────────────────────
# 4. Person
# ─────────────────────────────────────────────────────────────────────────────

class Person:
    _collection = 'persons'

    def __init__(self, **kw):
        self.id          = kw.get('id')
        self.user_id     = kw.get('user_id')
        self._user       = kw.get('_user')
        self.name        = kw.get('name', 'Unknown')
        self.cluster_id  = kw.get('cluster_id', -1)
        self.thumbnail   = MediaFile(kw.get('thumbnail', ''))
        self.photo_count = kw.get('photo_count', 0)
        self.created_at  = kw.get('created_at', datetime.now().isoformat())

    @property
    def user(self):
        if self._user is None and self.user_id:
            from django.contrib.auth.models import User as DjangoUser
            self._user = DjangoUser.objects.get(id=self.user_id)
        return self._user

    @user.setter
    def user(self, u):
        self._user = u
        self.user_id = u.id if u else None

    @property
    def face_encodings(self):
        records = db.filter_records('face_encodings', person_id=self.id)
        return JsonQuerySet(records, FaceEncoding)

    def _to_dict(self) -> dict:
        return {
            'user_id':     self.user_id,
            'name':        self.name,
            'cluster_id':  self.cluster_id,
            'thumbnail':   self.thumbnail.name if self.thumbnail else '',
            'photo_count': self.photo_count,
            'created_at':  str(self.created_at),
        }

    @classmethod
    def _from_dict(cls, d: dict):
        if d is None:
            return None
        return cls(**d)

    def save(self, update_fields=None):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            to_save = {f: data[f] for f in update_fields} if update_fields else data
            db.update_record(self._collection, self.id, **to_save)

    def delete(self):
        if self.id:
            db.delete_record(self._collection, self.id)

    def __str__(self):
        return f'{self.name} (cluster {self.cluster_id})'

    objects = None  # set below


# ─────────────────────────────────────────────────────────────────────────────
# 5. FaceEncoding
# ─────────────────────────────────────────────────────────────────────────────

class FaceEncoding:
    _collection = 'face_encodings'

    def __init__(self, **kw):
        self.id         = kw.get('id')
        self.photo_id   = kw.get('photo_id')
        self._photo     = kw.get('_photo')
        self.person_id  = kw.get('person_id')
        self._person    = kw.get('_person')
        self.encoding   = kw.get('encoding', '[]')
        self.face_index = kw.get('face_index', 0)
        self.confidence = kw.get('confidence', 0.0)
        self.top        = kw.get('top', 0)
        self.right      = kw.get('right', 0)
        self.bottom     = kw.get('bottom', 0)
        self.left       = kw.get('left', 0)
        self.face_image = MediaFile(kw.get('face_image', ''))
        self.created_at = kw.get('created_at', datetime.now().isoformat())

    @property
    def photo(self):
        if self._photo is None and self.photo_id:
            d = db.get_by_id('photos', self.photo_id)
            self._photo = Photo._from_dict(d) if d else None
        return self._photo

    @photo.setter
    def photo(self, p):
        self._photo = p
        self.photo_id = p.id if p else None

    @property
    def person(self):
        if self._person is None and self.person_id:
            d = db.get_by_id('persons', self.person_id)
            self._person = Person._from_dict(d) if d else None
        return self._person

    @person.setter
    def person(self, p):
        self._person = p
        self.person_id = p.id if p else None

    def _to_dict(self) -> dict:
        return {
            'photo_id':   self.photo_id,
            'person_id':  self.person_id,
            'encoding':   self.encoding,
            'face_index': self.face_index,
            'confidence': self.confidence,
            'top':        self.top,
            'right':      self.right,
            'bottom':     self.bottom,
            'left':       self.left,
            'face_image': self.face_image.name if self.face_image else '',
            'created_at': str(self.created_at),
        }

    @classmethod
    def _from_dict(cls, d: dict):
        if d is None:
            return None
        return cls(**d)

    def save(self, update_fields=None):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            to_save = {f: data[f] for f in update_fields} if update_fields else data
            db.update_record(self._collection, self.id, **to_save)

    def delete(self):
        if self.id:
            db.delete_record(self._collection, self.id)

    def __str__(self):
        return f'Face {self.face_index} in photo_id={self.photo_id}'

    objects = None  # set below


# ─────────────────────────────────────────────────────────────────────────────
# 6. Album
# ─────────────────────────────────────────────────────────────────────────────

class Album:
    _collection = 'albums'

    ALBUM_TYPES = [
        ('manual',   'Manual'),
        ('smart',    'Smart'),
        ('person',   'Person Album'),
        ('auto',     'Auto-generated'),
    ]

    def __init__(self, **kw):
        self.id             = kw.get('id')
        self.user_id        = kw.get('user_id')
        self._user          = kw.get('_user')
        self.name           = kw.get('name', '')
        self.description    = kw.get('description', '')
        self.cover_photo_id = kw.get('cover_photo_id')
        self.photo_ids      = kw.get('photo_ids', [])
        self.album_type     = kw.get('album_type', 'manual')
        self.is_public      = kw.get('is_public', False)
        self.created_at     = kw.get('created_at', datetime.now().isoformat())
        # Annotation field (set by views for photo count display)
        self.count          = kw.get('count', len(self.photo_ids))

    @property
    def user(self):
        if self._user is None and self.user_id:
            from django.contrib.auth.models import User as DjangoUser
            self._user = DjangoUser.objects.get(id=self.user_id)
        return self._user

    @user.setter
    def user(self, u):
        self._user = u
        self.user_id = u.id if u else None

    @property
    def photos(self):
        return AlbumPhotoM2M(self)

    @property
    def cover_photo(self):
        if self.cover_photo_id:
            d = db.get_by_id('photos', self.cover_photo_id)
            return Photo._from_dict(d) if d else None
        return None

    def _to_dict(self) -> dict:
        return {
            'user_id':        self.user_id,
            'name':           self.name,
            'description':    self.description,
            'cover_photo_id': self.cover_photo_id,
            'photo_ids':      self.photo_ids,
            'album_type':     self.album_type,
            'is_public':      self.is_public,
            'created_at':     str(self.created_at),
        }

    @classmethod
    def _from_dict(cls, d: dict):
        if d is None:
            return None
        obj = cls(**d)
        obj.count = len(obj.photo_ids)
        return obj

    def save(self, update_fields=None):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            to_save = {f: data[f] for f in update_fields} if update_fields else data
            db.update_record(self._collection, self.id, **to_save)

    def delete(self):
        if self.id:
            db.delete_record(self._collection, self.id)

    def __str__(self):
        return f'{self.name} (user_id={self.user_id})'

    objects = None  # set below


# ─────────────────────────────────────────────────────────────────────────────
# 7. PhotoSimilarity
# ─────────────────────────────────────────────────────────────────────────────

class PhotoSimilarity:
    _collection = 'photo_similarities'

    def __init__(self, **kw):
        self.id          = kw.get('id')
        self.photo_a_id  = kw.get('photo_a_id')
        self.photo_b_id  = kw.get('photo_b_id')
        self.score       = kw.get('score', 0.0)
        self.created_at  = kw.get('created_at', datetime.now().isoformat())

    def _to_dict(self) -> dict:
        return {
            'photo_a_id': self.photo_a_id,
            'photo_b_id': self.photo_b_id,
            'score':      self.score,
            'created_at': str(self.created_at),
        }

    @classmethod
    def _from_dict(cls, d: dict):
        return cls(**d)

    def save(self):
        data = self._to_dict()
        if self.id is None:
            record = db.insert(self._collection, data)
            self.id = record['id']
        else:
            db.update_record(self._collection, self.id, **data)

    objects = None  # set below


# ─── Wire up managers ─────────────────────────────────────────────────────────

for _cls in (UserProfile, Tag, Photo, Person, FaceEncoding, Album, PhotoSimilarity):
    _cls.objects = JsonManager(_cls)


# ─── Upload path helpers (kept for compatibility with AI code) ─────────────────

def photo_upload_path(username: str, filename: str) -> str:
    return f'photos/{username}/{filename}'


def face_thumbnail_path(filename: str) -> str:
    return f'faces/{filename}'
