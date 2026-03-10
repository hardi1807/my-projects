"""gallery/auth_urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    path('register/',   views.register_view,    name='register'),
    path('verify-otp/', views.verify_otp_view,  name='verify_otp'),
    path('login/',      views.login_view,        name='login'),
    path('logout/',     views.logout_view,       name='logout'),
]
