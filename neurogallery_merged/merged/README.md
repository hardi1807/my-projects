# NeuroGallery — JSON Storage Edition

No MySQL required. All app data is stored in JSON files inside `data/`.

## Quick Start

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open http://127.0.0.1:8000/auth/register/ to create your account.

## Data Files (auto-created on first run)

| File | Contents |
|------|----------|
| `data/photos.json` | Photo metadata |
| `data/albums.json` | Albums |
| `data/persons.json` | People / face clusters |
| `data/tags.json` | Tags |
| `data/face_encodings.json` | AI face encodings |
| `data/photo_similarities.json` | Duplicate scores |
| `data/user_profiles.json` | User profiles |
| `db.sqlite3` | Django auth & sessions only |
