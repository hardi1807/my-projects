"""
gallery/views.py  –  NeuroGallery (JSON storage edition)
"""
import json
import os
import random
import threading
import logging

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings as django_settings
import time

from .models import Photo, Album, Person, FaceEncoding, Tag, UserProfile
from .forms import (
    RegisterForm, LoginForm,
    PhotoUploadForm, AlbumForm,
    UserProfileForm, SearchForm, OTPVerifyForm,
)

logger = logging.getLogger(__name__)


# ─── Helper: JSON-based get_object_or_404 ────────────────────────────────────

def get_json_or_404(model_cls, **kwargs):
    """Return model instance matching kwargs or raise Http404."""
    try:
        return model_cls.objects.get(**kwargs)
    except (LookupError, Exception):
        raise Http404(f'{model_cls.__name__} not found.')


# ─── Helper: ensure UserProfile exists ───────────────────────────────────────

def get_or_create_profile(user):
    """Return the UserProfile for the given Django User, creating if needed."""
    try:
        return UserProfile.objects.get(user_id=user.id)
    except LookupError:
        profile = UserProfile(user_id=user.id)
        profile.save()
        return profile


# ══════════════════════════════════════════════════════════════════════════════
# Authentication
# ══════════════════════════════════════════════════════════════════════════════

def register_view(request):
    """Step 1: fill registration form → generate OTP → send to email."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']

        # Check email uniqueness
        if User.objects.filter(email=email).exists():
            form.add_error('email', 'An account with this email already exists.')
            return render(request, 'auth/register.html', {'form': form})

        otp_code = str(random.randint(100000, 999999))
        request.session['otp_code']    = otp_code
        request.session['otp_expiry']  = time.time() + getattr(django_settings, 'OTP_EXPIRY_SECONDS', 600)
        request.session['otp_regdata'] = {
            'username':   form.cleaned_data['username'],
            'email':      email,
            'first_name': form.cleaned_data.get('first_name', ''),
            'last_name':  form.cleaned_data.get('last_name', ''),
            'password':   form.cleaned_data['password1'],
        }

        try:
            send_mail(
                subject='NeuroGallery – Your Registration OTP',
                message=(
                    f'Hello {form.cleaned_data["username"]},\n\n'
                    f'Your NeuroGallery registration OTP is:\n\n'
                    f'  {otp_code}\n\n'
                    f'This OTP is valid for 10 minutes. Do not share it with anyone.\n\n'
                    f'– NeuroGallery Team'
                ),
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            messages.info(request, f'OTP sent to {email}. Please check your inbox.')
        except Exception as exc:
            logger.error('OTP email failed: %s', exc)
            messages.warning(request,
                'Could not send OTP email (check SMTP settings). '
                f'For testing, your OTP is: {otp_code}')

        return redirect('verify_otp')

    return render(request, 'auth/register.html', {'form': form})


def verify_otp_view(request):
    """Step 2: verify OTP → create account → login."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    reg_data = request.session.get('otp_regdata')
    if not reg_data:
        messages.error(request, 'Session expired. Please register again.')
        return redirect('register')

    form  = OTPVerifyForm(request.POST or None)
    email = reg_data.get('email', '')

    if request.method == 'POST':
        if 'resend' in request.POST:
            otp_code = str(random.randint(100000, 999999))
            request.session['otp_code']   = otp_code
            request.session['otp_expiry'] = time.time() + getattr(django_settings, 'OTP_EXPIRY_SECONDS', 600)
            try:
                send_mail(
                    subject='NeuroGallery – Resend OTP',
                    message=f'Your new OTP is: {otp_code}  (valid 10 minutes)',
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                messages.info(request, f'New OTP sent to {email}.')
            except Exception as exc:
                logger.error('Resend OTP failed: %s', exc)
                messages.warning(request, f'Email failed. OTP: {otp_code}')
            return redirect('verify_otp')

        if form.is_valid():
            entered_otp = form.cleaned_data['otp']
            stored_otp  = request.session.get('otp_code', '')
            expiry      = request.session.get('otp_expiry', 0)

            if time.time() > expiry:
                messages.error(request, 'OTP has expired. Please register again.')
                for k in ('otp_code', 'otp_expiry', 'otp_regdata'):
                    request.session.pop(k, None)
                return redirect('register')

            if entered_otp != stored_otp:
                messages.error(request, 'Invalid OTP. Please try again.')
                return render(request, 'auth/verify_otp.html', {'form': form, 'email': email})

            # Create Django user (still uses SQLite for auth)
            user = User.objects.create_user(
                username   = reg_data['username'],
                email      = reg_data['email'],
                password   = reg_data['password'],
                first_name = reg_data.get('first_name', ''),
                last_name  = reg_data.get('last_name', ''),
            )
            # Create JSON profile
            profile = UserProfile(user_id=user.id)
            profile.save()

            for k in ('otp_code', 'otp_expiry', 'otp_regdata'):
                request.session.pop(k, None)

            login(request, user)
            messages.success(request, f'Welcome to NeuroGallery, {user.username}! Your email is verified.')
            return redirect('dashboard')

    return render(request, 'auth/verify_otp.html', {'form': form, 'email': email})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def dashboard(request):
    user   = request.user
    photos = Photo.objects.filter(user=user)

    stats = {
        'total_photos': photos.count(),
        'total_albums': Album.objects.filter(user=user).count(),
        'total_people': Person.objects.filter(user=user).count(),
        'selfies':      photos.filter(category='selfie').count(),
        'group_photos': photos.filter(category='group').count(),
        'favourites':   photos.filter(is_favourite=True).count(),
    }
    recent_photos = photos.order_by('-upload_date')[:12]
    recent_albums = Album.objects.filter(user=user).order_by('-created_at')[:6]
    top_people    = Person.objects.filter(user=user).order_by('-photo_count')[:6]

    return render(request, 'gallery/dashboard.html', {
        'stats':         stats,
        'recent_photos': list(recent_photos),
        'recent_albums': list(recent_albums),
        'top_people':    list(top_people),
    })


# ══════════════════════════════════════════════════════════════════════════════
# Photo Upload
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def upload_photos(request):
    form = PhotoUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        files       = request.FILES.getlist('images')
        title       = form.cleaned_data.get('title', '')
        description = form.cleaned_data.get('description', '')
        taken_date  = form.cleaned_data.get('taken_date')
        tags_raw    = form.cleaned_data.get('tags_input', '')

        # Parse tags
        tag_list = [t.strip() for t in tags_raw.split(',') if t.strip()]
        tag_objs = []
        for t in tag_list:
            tag, _ = Tag.objects.get_or_create(
                name=t.lower(),
                defaults={'created_by_id': request.user.id}
            )
            tag_objs.append(tag)

        saved = []
        for f in files:
            # Save the uploaded file to media storage
            from django.core.files.storage import default_storage
            rel_path = f'photos/{request.user.username}/{f.name}'
            file_path = default_storage.save(rel_path, f)

            photo = Photo(
                user_id     = request.user.id,
                title       = title,
                description = description,
                taken_date  = str(taken_date) if taken_date else None,
            )
            photo.image = MediaFile(file_path)
            photo.save()

            if tag_objs:
                photo.tags.set(tag_objs)

            saved.append(photo)

        # Run AI processing in background thread
        def _ai_worker(photos):
            from .ai.image_processor import process_photo
            from .ai.face_clusterer  import cluster_faces
            from .ai.smart_albums    import build_smart_albums
            for p in photos:
                try:
                    process_photo(p)
                except Exception as exc:
                    logger.error('AI processing error: %s', exc)
            try:
                cluster_faces(request.user)
                build_smart_albums(request.user)
            except Exception as exc:
                logger.error('Clustering/smart-albums error: %s', exc)

        t = threading.Thread(target=_ai_worker, args=(saved,), daemon=True)
        t.start()

        messages.success(request, f'{len(saved)} photo(s) uploaded successfully! AI processing started.')
        return redirect('gallery')

    return render(request, 'gallery/upload.html', {'form': form})


# ── Import missing MediaFile class ────────────────────────────────────────────
from .models import MediaFile   # noqa: E402 (needed after Photo class)


# ══════════════════════════════════════════════════════════════════════════════
# Gallery (timeline)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def gallery_view(request):
    photos = Photo.objects.filter(user=request.user).order_by('-upload_date')
    paginator = Paginator(list(photos), 24)
    page      = paginator.get_page(request.GET.get('page'))
    return render(request, 'gallery/gallery.html', {'page_obj': page, 'photos': page.object_list})


@login_required
def photo_detail(request, pk):
    photo   = get_json_or_404(Photo, pk=pk, user=request.user)
    all_ids = Photo.objects.filter(user=request.user).order_by('-upload_date').values_list('id', flat=True)
    idx     = all_ids.index(pk) if pk in all_ids else 0
    prev_id = all_ids[idx - 1] if idx > 0 else None
    next_id = all_ids[idx + 1] if idx < len(all_ids) - 1 else None
    faces   = list(photo.face_encodings.select_related('person').all())
    return render(request, 'gallery/photo_detail.html', {
        'photo':   photo,
        'prev_id': prev_id,
        'next_id': next_id,
        'faces':   faces,
    })


@login_required
def delete_photo(request, pk):
    photo = get_json_or_404(Photo, pk=pk, user=request.user)
    if request.method == 'POST':
        photo.image.delete(save=False)
        if photo.thumbnail:
            photo.thumbnail.delete(save=False)
        photo.delete()
        messages.success(request, 'Photo deleted.')
        return redirect('gallery')
    return render(request, 'gallery/confirm_delete.html', {'photo': photo})


@login_required
def toggle_favourite(request, pk):
    photo = get_json_or_404(Photo, pk=pk, user=request.user)
    photo.is_favourite = not photo.is_favourite
    photo.save(update_fields=['is_favourite'])
    return JsonResponse({'is_favourite': photo.is_favourite})


# ══════════════════════════════════════════════════════════════════════════════
# People (face clusters)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def people_view(request):
    people = list(Person.objects.filter(user=request.user).order_by('-photo_count'))
    return render(request, 'gallery/people.html', {'people': people})


@login_required
def person_detail(request, pk):
    person    = get_json_or_404(Person, pk=pk, user=request.user)
    photo_ids = (
        FaceEncoding.objects
        .filter(person_id=person.id)
        .values_list('photo_id', flat=True)
    )
    photo_ids = list(set(photo_ids))  # distinct
    photos    = Photo.objects.filter(user=request.user).filter(id__in=photo_ids).order_by('-upload_date')
    if request.method == 'POST':
        person.name = request.POST.get('name', person.name)
        person.save(update_fields=['name'])
        messages.success(request, 'Name updated.')
        return redirect('person_detail', pk=pk)
    return render(request, 'gallery/person_detail.html', {'person': person, 'photos': list(photos)})


@login_required
def run_clustering(request):
    """Force re-detect faces on every photo, then re-cluster all faces (background)."""
    user = request.user

    # Reset AI flags
    Photo.objects.filter(user=user).update(ai_processed=False, face_count=0)
    # Delete existing face encodings and persons for this user
    all_photo_ids = Photo.objects.filter(user=user).values_list('id', flat=True)
    for pid in all_photo_ids:
        FaceEncoding.objects.filter(photo_id=pid).delete()
    Person.objects.filter(user=user).delete()

    def _cluster_worker():
        from .ai.image_processor import process_photo
        from .ai.face_clusterer  import cluster_faces
        from .ai.smart_albums    import build_smart_albums
        photos = list(Photo.objects.filter(user=user))
        for photo in photos:
            try:
                process_photo(photo)
            except Exception as exc:
                logger.error('Re-process error on photo %s: %s', photo.id, exc)
        try:
            n = cluster_faces(user)
            build_smart_albums(user)
            logger.info('Clustering complete – %d person(s) found for user %s.', n, user.username)
        except Exception as exc:
            logger.error('Clustering/smart-albums error: %s', exc)

    t = threading.Thread(target=_cluster_worker, daemon=True)
    t.start()

    messages.success(request, 'Face clustering started in background. Refresh this page in a moment to see results.')
    return redirect('people')


# ══════════════════════════════════════════════════════════════════════════════
# Albums
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def albums_view(request):
    albums = list(Album.objects.filter(user=request.user).order_by('-created_at'))
    # Attach photo count annotation
    for album in albums:
        album.count = len(album.photo_ids)
    return render(request, 'gallery/albums.html', {'albums': albums})


@login_required
def album_detail(request, pk):
    album  = get_json_or_404(Album, pk=pk, user=request.user)
    photos = list(album.photos.all().order_by('-upload_date'))
    return render(request, 'gallery/album_detail.html', {'album': album, 'photos': photos})


@login_required
def create_album(request):
    form = AlbumForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        album = Album(
            user_id     = request.user.id,
            name        = form.cleaned_data['name'],
            description = form.cleaned_data.get('description', ''),
            is_public   = form.cleaned_data.get('is_public', False),
            album_type  = 'manual',
        )
        album.save()
        messages.success(request, f'Album "{album.name}" created.')
        return redirect('album_detail', pk=album.id)
    return render(request, 'gallery/create_album.html', {'form': form})


@login_required
def add_to_album(request):
    """AJAX: add selected photos to an album."""
    if request.method == 'POST':
        album_id  = request.POST.get('album_id')
        photo_ids = request.POST.getlist('photo_ids')
        try:
            album = Album.objects.get(pk=int(album_id), user=request.user)
        except LookupError:
            raise Http404('Album not found.')
        photos = Photo.objects.filter(user=request.user).filter(id__in=[int(pid) for pid in photo_ids])
        album.photos.add(*list(photos))
        return JsonResponse({'status': 'ok', 'added': photos.count()})
    return JsonResponse({'status': 'error'}, status=400)


# ══════════════════════════════════════════════════════════════════════════════
# Search
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def search_view(request):
    form   = SearchForm(request.GET or None)
    photos = Photo.objects.filter(user=request.user)

    if form.is_valid():
        q         = form.cleaned_data.get('query', '')
        tag       = form.cleaned_data.get('tag', '')
        date_from = form.cleaned_data.get('date_from')
        date_to   = form.cleaned_data.get('date_to')

        if q:
            q_lower = q.lower()
            photos = photos.filter(title__icontains=q_lower)
            # Also search description and image name (manual OR logic)
            all_user_photos = Photo.objects.filter(user=request.user)
            desc_matches = all_user_photos.filter(description__icontains=q_lower)
            img_matches  = all_user_photos.filter(image__icontains=q_lower)
            # Merge IDs
            merged_ids = {p['id'] for p in photos._records} | \
                         {p['id'] for p in desc_matches._records} | \
                         {p['id'] for p in img_matches._records}
            photos = Photo.objects.filter(user=request.user).filter(id__in=list(merged_ids))

        if tag:
            # Filter photos whose tag_ids contain a tag matching the name
            matching_tags = Tag.objects.filter(name__icontains=tag.lower())
            tag_ids = [t.id for t in matching_tags]
            photos = JsonQuerySet(
                [r for r in photos._records if any(tid in r.get('tag_ids', []) for tid in tag_ids)],
                Photo
            )

        if date_from:
            photos = photos.filter(upload_date__date__gte=date_from)
        if date_to:
            photos = photos.filter(upload_date__date__lte=date_to)

    photos = photos.order_by('-upload_date')
    paginator = Paginator(list(photos), 24)
    page      = paginator.get_page(request.GET.get('page'))

    return render(request, 'gallery/search.html', {
        'form':     form,
        'page_obj': page,
        'photos':   page.object_list,
        'query':    request.GET.get('query', ''),
    })


# ── Import JsonQuerySet for search_view ───────────────────────────────────────
from .models import JsonQuerySet   # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Profile
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def profile_view(request):
    profile = get_or_create_profile(request.user)
    form    = UserProfileForm(request.POST or None, request.FILES or None, profile=profile)
    if request.method == 'POST' and form.is_valid():
        profile.bio       = form.cleaned_data.get('bio', '')
        profile.dark_mode = form.cleaned_data.get('dark_mode', False)
        if 'avatar' in request.FILES:
            from django.core.files.storage import default_storage
            avatar_file = request.FILES['avatar']
            avatar_path = default_storage.save(f'avatars/{avatar_file.name}', avatar_file)
            profile.avatar = MediaFile(avatar_path)
        profile.save()
        messages.success(request, 'Profile updated.')
        return redirect('profile')
    return render(request, 'gallery/profile.html', {'form': form, 'profile': profile})


# ══════════════════════════════════════════════════════════════════════════════
# Toggle dark mode (AJAX)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def toggle_dark_mode(request):
    profile = get_or_create_profile(request.user)
    profile.dark_mode = not profile.dark_mode
    profile.save(update_fields=['dark_mode'])
    return JsonResponse({'dark_mode': profile.dark_mode})
