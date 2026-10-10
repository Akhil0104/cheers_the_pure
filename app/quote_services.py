from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.urls import reverse

from .models import EmailVerificationToken, QuoteRequest


class IdempotencyConflict(Exception):
    """The same idempotency key was reused with different inquiry data."""


def _matches_existing_inquiry(quote, *, user, name, email, company, size, quantity, details):
    return (
        quote.user_id == getattr(user, "pk", None)
        and quote.name == name
        and quote.email == email
        and quote.company == company
        and quote.size == size
        and quote.quantity == quantity
        and quote.details == details
    )


def _send_verification_email(request, quote, token):
    verify_url = request.build_absolute_uri(reverse("verify_email", args=[token.token]))
    message = (
        f"Hello {quote.name},\n\n"
        "Thank you for requesting a quote from CheersThePure.\n\n"
        f"Verify your email using this link: {verify_url}\n\n"
        "The link expires in 24 hours. Once verified, our team can review your pending inquiry.\n\n"
        "Best regards,\nCheersThePure Team"
    )
    send_mail(
        "Verify Your Quote Request - CheersThePure",
        message,
        settings.DEFAULT_FROM_EMAIL,
        [quote.email],
        fail_silently=True,
    )


def create_quote_request_workflow(
    *,
    request,
    user,
    name,
    email,
    company="",
    size="500 ml",
    quantity=1,
    details="",
    product=None,
    preferred_delivery_timing="",
    delivery_address="",
    idempotency_key=None,
):
    """Persist a pending quote and run the established email-verification workflow."""
    pending_status = next(
        (value for value, _label in QuoteRequest.STATUS_CHOICES if value == "pending"),
        None,
    )
    if pending_status is None:
        raise ImproperlyConfigured("QuoteRequest must define a pending status.")

    def existing_for_key():
        if not idempotency_key:
            return None
        return QuoteRequest.objects.filter(inquiry_idempotency_key=idempotency_key).first()

    existing = existing_for_key()
    if existing:
        if not _matches_existing_inquiry(
            existing,
            user=user,
            name=name,
            email=email,
            company=company,
            size=size,
            quantity=quantity,
            details=details,
        ):
            raise IdempotencyConflict
        return existing, False

    try:
        with transaction.atomic():
            quote = QuoteRequest.objects.create(
                user=user,
                product=product,
                name=name,
                email=email,
                company=company,
                size=size,
                quantity=quantity,
                preferred_delivery_timing=preferred_delivery_timing,
                delivery_address=delivery_address,
                details=details,
                email_verified=False,
                status=pending_status,
                inquiry_idempotency_key=idempotency_key,
            )
            verification_token = EmailVerificationToken.create_token(quote)
            transaction.on_commit(
                lambda: _send_verification_email(request, quote, verification_token)
            )
            return quote, True
    except IntegrityError:
        existing = existing_for_key()
        if existing and _matches_existing_inquiry(
            existing,
            user=user,
            name=name,
            email=email,
            company=company,
            size=size,
            quantity=quantity,
            details=details,
        ):
            return existing, False
        if existing:
            raise IdempotencyConflict
        raise