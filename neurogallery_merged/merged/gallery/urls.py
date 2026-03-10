"""gallery/urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    # Root → dashboard
    path('', views.dashboard, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Gallery / timeline
    path('gallery/', views.gallery_view, name='gallery'),
    path('photo/<int:pk>/', views.photo_detail, name='photo_detail'),
    path('photo/<int:pk>/delete/', views.delete_photo, name='delete_photo'),
    path('photo/<int:pk>/favourite/', views.toggle_favourite, name='toggle_favourite'),

    # Upload
    path('upload/', views.upload_photos, name='upload'),

    # People
    path('people/', views.people_view, name='people'),
    path('people/<int:pk>/', views.person_detail, name='person_detail'),
    path('people/cluster/', views.run_clustering, name='run_clustering'),

    # Albums
    path('albums/', views.albums_view, name='albums'),
    path('albums/<int:pk>/', views.album_detail, name='album_detail'),
    path('albums/create/', views.create_album, name='create_album'),
    path('albums/add/', views.add_to_album, name='add_to_album'),

    # Search
    path('search/', views.search_view, name='search'),

    # Profile
    path('profile/', views.profile_view, name='profile'),
    path('profile/dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
]
