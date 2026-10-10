# Core additions to core/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-development-secret-key')
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',') if os.environ.get('ALLOWED_HOSTS') else ['localhost', '127.0.0.1', 'testserver']

# Admin credentials from environment variables for secure secret management
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'cheersthepure@gmail.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'change-this-admin-password')
SMS_GATEWAY_TOKEN = os.environ.get('SMS_GATEWAY_TOKEN', '')

# ── Authentication Backends ──────────────────────────────────────────────────
# Primary: email OR mobile number login (no username required).
# Fallback: Django's default ModelBackend (keeps Django admin working).
import sys
AUTHENTICATION_BACKENDS = [
    'app.backends.EmailOrMobileBackend',
    'django.contrib.auth.backends.ModelBackend',
]
if 'test' not in sys.argv:
    AUTHENTICATION_BACKENDS.insert(0, 'axes.backends.AxesBackend')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'app',
    'dispatch',  # DispatchAI — B2B AI agent
    'ai_builder',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'app' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'app.context_processors.account_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'app' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email Configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@cheers.com')

# Notification Settings
NOTIFICATION_EMAIL_ENABLED = os.environ.get('NOTIFICATION_EMAIL_ENABLED', 'True').lower() in ('1', 'true', 'yes')
VERIFICATION_TOKEN_EXPIRY_HOURS = int(os.environ.get('VERIFICATION_TOKEN_EXPIRY_HOURS', 24))

# Stripe Payment Configuration
STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_YOUR_TEST_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_YOUR_TEST_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', 'whsec_YOUR_TEST_WEBHOOK_SECRET')

# ── Warehouse / Distribution Centre Coordinates ──────────────────────────────
# Update these to your actual warehouse GPS location.
# Default: Hyderabad city centre (17.3850°N, 78.4867°E)
WAREHOUSE_LAT = float(os.environ.get('WAREHOUSE_LAT', '17.3850'))
WAREHOUSE_LON = float(os.environ.get('WAREHOUSE_LON', '78.4867'))

# ── Delivery Fee Tiers (distance in km, fee in INR/km) ───────────────────────
DELIVERY_FREE_KM = 1        # Distance <= this → ₹0
DELIVERY_TIER1_MAX_KM = 5   # 2–5 km → TIER1_RATE per km
DELIVERY_TIER1_RATE = 10    # ₹10 per km (2–5 km band)
DELIVERY_TIER2_RATE = 15    # ₹15 per km (> 5 km band)

# ── Django-Axes Configuration (Rate Limiting) ────────────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # Lock out for 1 hour after 5 failed attempts
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'app/lockout.html'

# ── Django Authentication Configuration ───────────────────────────
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'index'

# ── Production Django Security Hardening ──────────────────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Ensure allowed hosts has the custom production domain
    if 'cheersthepure.com' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append('cheersthepure.com')


# ── DispatchAI Configuration ─────────────────────────────────────────────────

# Groq LLM — https://console.groq.com/keys
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

# Trusted same-origin endpoint used by the SaaSsum builder; never comes from SiteSchema.
SAASSUM_INQUIRY_API_URL = os.environ.get(
    'SAASSUM_INQUIRY_API_URL',
    '/api/v1/inquiry/submit/',
)

# Hindsight Persistent Memory — https://api.hindsight.vectorize.io
HINDSIGHT_URL = os.environ.get('HINDSIGHT_URL', os.environ.get('HINDSIGHT_API_URL', 'https://api.hindsight.vectorize.io'))
HINDSIGHT_API_KEY = os.environ.get('HINDSIGHT_API_KEY', '')
HINDSIGHT_APP_ID = os.environ.get('HINDSIGHT_APP_ID', 'cheersthepure')

# DispatchAI — feature flags
DISPATCHAI_ENABLED = os.environ.get('DISPATCHAI_ENABLED', 'True').lower() in ('1', 'true', 'yes')
DISPATCHAI_MAX_MSG_LENGTH = int(os.environ.get('DISPATCHAI_MAX_MSG_LENGTH', 2000))
DISPATCHAI_RECALL_LIMIT = int(os.environ.get('DISPATCHAI_RECALL_LIMIT', 10))
