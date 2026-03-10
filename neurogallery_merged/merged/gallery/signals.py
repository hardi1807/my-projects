"""
gallery/signals.py
Auto-create a JSON UserProfile whenever a new Django User is registered.
(Django's User model still lives in SQLite for auth; the profile lives in JSON.)
"""
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        from .models import UserProfile
        # Only create if one doesn't already exist
        existing = UserProfile.objects.filter(user_id=instance.id)
        if not existing.exists():
            profile = UserProfile(user_id=instance.id)
            profile.save()
