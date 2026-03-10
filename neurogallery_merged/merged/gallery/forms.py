"""
gallery/forms.py  –  NeuroGallery (JSON storage edition)
ModelForms replaced with standard Django Forms since
Photo / Album / UserProfile are no longer Django ORM models.
"""
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm


# ── Authentication ──────────────────────────────────────────────────────────

class RegisterForm(UserCreationForm):
    email      = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=False)
    last_name  = forms.CharField(max_length=30, required=False)

    class Meta:
        model  = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            field.widget.attrs['placeholder'] = field.label


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


# ── Custom multi-file widget ───────────────────────────────────────────────

class MultipleFileInput(forms.FileInput):
    """Allows <input type="file" multiple>."""
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """FileField that returns a list of uploaded files."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={
            'accept': 'image/*',
            'class': 'form-control',
            'id': 'photo-input',
        }))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data]
        return [single(data, initial)]


# ── Photo Upload ─────────────────────────────────────────────────────────────

class PhotoUploadForm(forms.Form):
    images      = MultipleFileField(label='Select Photos')
    title       = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Album / Event title (optional)',
        }),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    taken_date  = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    tags_input  = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Add tags (comma separated)',
            'id': 'tags-input',
        }),
        label='Tags',
    )


# ── Album ────────────────────────────────────────────────────────────────────

class AlbumForm(forms.Form):
    name        = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    is_public   = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


# ── Profile ──────────────────────────────────────────────────────────────────

class UserProfileForm(forms.Form):
    avatar    = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
    )
    bio       = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    dark_mode = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, **kwargs):
        # Accept and ignore `profile` kwarg passed from views.py
        kwargs.pop('profile', None)
        super().__init__(*args, **kwargs)


# ── Search ───────────────────────────────────────────────────────────────────

class SearchForm(forms.Form):
    query     = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search photos...'}),
    )
    tag       = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tag'}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    date_to   = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )


# ── OTP Verification ─────────────────────────────────────────────────────────

class OTPVerifyForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        label='Enter OTP',
        widget=forms.TextInput(attrs={
            'class': 'form-control otp-input',
            'placeholder': '6-digit OTP',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
        }),
    )
