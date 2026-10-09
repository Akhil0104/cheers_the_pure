"""
Forms for Cheers the Pure Water.

Key changes from original:
  - RegistrationForm replaced with NoUsernameRegistrationForm
    (no username field shown; auto-generated internally)
  - LoginForm replaced with EmailOrMobileLoginForm
    (accepts email address OR mobile number + password)
"""

import re
import uuid

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Product, Category, UserProfile
from .account_utils import detect_account_type, parse_company_name_from_email


# ── Product / Category forms (unchanged) ────────────────────────────────────

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['category', 'name', 'capacity', 'price', 'is_featured', 'description', 'image', 'image_url']
        widgets = {
            'category':    forms.Select(attrs={'class': 'form-input'}),
            'name':        forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Product Name'}),
            'capacity':    forms.Select(attrs={'class': 'form-input'}),
            'price':       forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Price (e.g. 5.99)', 'step': '0.01'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'Product Description', 'rows': 4}),
            'image':       forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'image_url':   forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Image URL (optional)'}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Category Name'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'Category Description', 'rows': 4}),
        }


# ── Login Form ───────────────────────────────────────────────────────────────

class EmailOrMobileLoginForm(forms.Form):
    """
    No-username login form.  Accepts email address OR mobile number.
    The field is named 'username' internally so Django's auth machinery works.
    """

    username = forms.CharField(
        label='Email Address or Mobile Number',
        max_length=254,
        widget=forms.TextInput(attrs={
            'class':       'form-input',
            'placeholder': 'your@email.com  or  +91 9876543210',
            'autofocus':   True,
            'id':          'id_login_credential',
        }),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class':       'form-input',
            'placeholder': 'Enter your password',
            'id':          'id_login_password',
        }),
    )


# ── Registration Form ────────────────────────────────────────────────────────

_MOBILE_RE = re.compile(r'^\+?[\d\s\-]{7,15}$')


def _auto_username(email: str, mobile: str) -> str:
    """
    Generate a unique username derived from email or mobile.
    The username is never shown to the user — it's only for Django internals.
    """
    if email:
        base = re.sub(r'[^\w]', '_', email.split('@')[0])[:28]
    elif mobile:
        base = re.sub(r'[\s\-\+]', '', mobile)[:28]
    else:
        base = 'user'

    suffix = uuid.uuid4().hex[:6]
    return f"{base}_{suffix}"


class NoUsernameRegistrationForm(forms.Form):
    """
    Registration form that accepts email + optional mobile number.
    Username is completely hidden from the user — auto-generated internally.
    B2C/B2B account type is detected automatically from the email domain.
    """

    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class':       'form-input',
            'placeholder': 'your@email.com',
            'id':          'id_reg_email',
            'autocomplete': 'email',
        }),
    )

    mobile = forms.CharField(
        label='Mobile Number (optional)',
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class':       'form-input',
            'placeholder': '+91 9876543210',
            'id':          'id_reg_mobile',
            'autocomplete': 'tel',
            'inputmode':   'tel',
        }),
    )

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class':       'form-input',
            'placeholder': 'Choose a strong password',
            'id':          'id_reg_password1',
            'autocomplete': 'new-password',
        }),
    )

    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class':       'form-input',
            'placeholder': 'Repeat your password',
            'id':          'id_reg_password2',
            'autocomplete': 'new-password',
        }),
    )

    # ── Validation ──

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email address already exists.')
        return email

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile', '').strip()
        if not mobile:
            return mobile
        digits = re.sub(r'[\s\-]', '', mobile)
        if not _MOBILE_RE.match(mobile):
            raise ValidationError('Enter a valid mobile number (7–15 digits, optional +).')
        # Check uniqueness in UserProfile.phone
        if UserProfile.objects.filter(phone=digits).exists():
            raise ValidationError('An account with this mobile number already exists.')
        return digits

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1', '')
        p2 = self.cleaned_data.get('password2', '')
        if p1 and p2 and p1 != p2:
            raise ValidationError('The two passwords do not match.')
        try:
            validate_password(p1)
        except ValidationError as exc:
            raise ValidationError(exc.messages)
        return p2

    # ── Save ──

    def save(self):
        """Create User + UserProfile. Returns the new User instance."""
        email  = self.cleaned_data['email']
        mobile = self.cleaned_data.get('mobile', '')
        pw     = self.cleaned_data['password1']

        username = _auto_username(email, mobile)

        # Detect B2C vs B2B from email domain
        account_type = detect_account_type(email)
        company_name = ''
        role         = 'customer'
        if account_type == 'b2b':
            company_name = parse_company_name_from_email(email)
            role         = 'distributor'

        # Create the Django User (username hidden from UI)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=pw,
        )

        # Create UserProfile with phone/mobile
        profile = UserProfile.objects.create(
            user=user,
            role=role,
            account_type=account_type,
            company_name=company_name,
            phone=mobile,
        )

        # Async Ollama enrichment for B2B (fails silently if offline)
        if account_type == 'b2b':
            try:
                from .account_utils import enrich_b2b_profile_with_ollama
                enrich_b2b_profile_with_ollama(email, profile)
            except Exception:
                pass

        return user
