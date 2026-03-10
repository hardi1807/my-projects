"""
gallery/migrations/0001_initial.py

Only Django's built-in auth / session tables are migrated to SQLite.
All NeuroGallery app data (Photo, Album, Person, Tag, etc.) is stored
in JSON files under BASE_DIR/data/ — no database tables needed for them.
"""
from django.db import migrations


class Migration(migrations.Migration):
    """Empty migration — gallery app has no database models."""

    initial = True
    dependencies = []
    operations = []
