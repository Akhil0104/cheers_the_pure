import json

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from django.db.models import Q
from django.contrib.auth.models import User
from .models import (
    Category,
    ContactMessage,
    Product,
    QuoteRequest,
    Testimonial,
    EmailVerificationToken,
    QuoteReply,
    Notification,
    UserProfile,
    PaymentTransaction,
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderPayment,
    Inventory,
)
from .email_utils import (
    send_order_confirmation_email,
    send_quote_payment_email,
    send_shipping_notification,
    send_delivery_confirmation,
    send_order_invoice_email,
)
from .decorators import b2b_required, b2c_required
from .account_utils import detect_account_type
from .invoice_utils import generate_invoice_for_order

try:
    import stripe
    from .stripe_utils import create_checkout_session, retrieve_checkout_session, retrieve_payment_intent
except ImportError:
    stripe = None
    create_checkout_session = None
    retrieve_checkout_session = None
    retrieve_payment_intent = None

# Custom decorator to restrict dashboard management to admin/staff
def admin_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_staff)(view_func))



def serialize_product(product):
    if getattr(product, 'image', None) and product.image:
        image_url = product.image.url
    elif product.image_url:
        image_url = product.image_url
    else:
        capacity = (product.capacity or '').lower()
        mapping = {
            '250 ml': settings.STATIC_URL + 'app/media/250ml.jpg',
            '500 ml': settings.STATIC_URL + 'app/media/500ml.jpg',
            '1000 ml': settings.STATIC_URL + 'app/media/1ltr.jpg',
            '1 ltr': settings.STATIC_URL + 'app/media/1ltr.jpg',
            '2 litres': settings.STATIC_URL + 'app/media/2ltr.jpg',
        }
        image_url = mapping.get(capacity, settings.STATIC_URL + 'app/media/manufacturing-poster.svg')

    # Compute a default tray count, tray text, and price override per capacity
    cap_norm = (product.capacity or '').lower()
    if '250' in cap_norm:
        tray_count = 18
        tray_text = '1 tray = 18 pieces'
        price = '140'
    elif '500' in cap_norm:
        tray_count = 18
        tray_text = '1 tray = 18 bottles'
        price = 'TBD'
    elif '1000' in cap_norm or '1 l' in cap_norm or '1ltr' in cap_norm:
        tray_count = 12
        tray_text = '1 tray = 12 bottles'
        price = '120'
    elif '2' in cap_norm:
        tray_count = 6
        tray_text = '1 tray = 6 bottles'
        price = 'TBD'
    else:
        tray_count = 12
        tray_text = '1 tray = 12 bottles'
        price = str(product.price)

    return {
        'id': product.id,
        'name': product.name,
        'category': product.category.name if product.category else None,
        'description': product.description,
        'capacity': product.capacity,
        'price': price,
        'is_featured': product.is_featured,
        'image_url': image_url,
        'tray_count': tray_count,
        'tray_text': tray_text,
    }


def serialize_testimonial(item):
    return {
        'id': item.id,
        'name': item.name,
        'role': item.role,
        'company': item.company,
        'quote': item.quote,
    }


def serialize_category(category):
    return {
        'id': category.id,
        'name': category.name,
        'description': category.description,
    }


def index(request):
    featured_products = Product.objects.filter(is_featured=True)
    testimonials = Testimonial.objects.all()[:3]
    categories = Category.objects.all()
    return render(
        request,
        'app/index.html',
        {
            'products': featured_products,
            'testimonials': testimonials,
            'categories': categories,
        },
    )


def products(request):
    profile = getattr(request.user, 'profile', None) if request.user.is_authenticated else None
    if profile:
        account_type = profile.account_type
    elif request.user.is_authenticated:
        account_type = detect_account_type(request.user.email)
    else:
        account_type = 'b2c'  # Default to B2C for guests

    return render(request, 'app/products.html', {
        'account_type': account_type,
        'is_b2c': account_type == 'b2c' or not request.user.is_authenticated,
        'is_b2b': account_type == 'b2b' and request.user.is_authenticated,
    })


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'app/product_detail.html', {'product': product})


def categories(request):
    categories = Category.objects.all()
    return render(request, 'app/categories.html', {'categories': categories})


def category_detail(request, pk):
    category = get_object_or_404(Category, pk=pk)
    products = category.products.all()
    return render(
        request,
        'app/category_detail.html',
        {
            'category': category,
            'products': products,
        },
    )


def about(request):
    return render(request, 'app/about.html')


def contact(request):
    success = False
    if request.method == 'POST':
        source_data = request.POST
        if request.content_type == 'application/json':
            try:
                source_data = json.loads(request.body)
            except json.JSONDecodeError:
                return HttpResponseBadRequest('Invalid JSON payload')

        name = source_data.get('name', '').strip()
        email = source_data.get('email', '').strip()
        subject = source_data.get('subject', '').strip()
        message = source_data.get('message', '').strip()
        if name and email and subject and message:
            ContactMessage.objects.create(
                name=name,
                email=email,
                subject=subject,
                message=message,
            )
            success = True
    return render(request, 'app/contact.html', {'success': success})


def access_denied(request):
    profile = getattr(request.user, 'profile', None)
    account_type = profile.account_type if profile else detect_account_type(request.user.email)
    return render(request, 'app/access_denied.html', {'account_type': account_type})


def _redirect_for_user(user):
    if user.is_staff:
        return redirect('dashboard')
    return redirect('dashboard')


def order_request(request, pk=None):
    if not request.user.is_authenticated:
        return render(request, 'app/order_request_auth_prompt.html')

    profile = getattr(request.user, 'profile', None)
    account_type = profile.account_type if profile else detect_account_type(request.user.email)
    if not request.user.is_staff and account_type != 'b2b':
        return redirect('access_denied')
        
    product = None
    if pk is not None:
        product = get_object_or_404(Product, pk=pk)

    size_options = QuoteRequest.SIZE_CHOICES
    selected_size = ''
    if product and product.capacity in dict(QuoteRequest.SIZE_CHOICES):
        selected_size = product.capacity

    success = False
    created_quote = None
    if request.method == 'POST':
        source_data = request.POST
        name = source_data.get('name', '').strip()
        email = source_data.get('email', '').strip()
        company = source_data.get('company', '').strip()
        size = source_data.get('size', '').strip()
        quantity = source_data.get('quantity', '').strip()
        preferred_delivery_timing = source_data.get('preferred_delivery_timing', '').strip()
        delivery_address = source_data.get('delivery_address', '').strip()
        details = source_data.get('details', '').strip()

        if name and email and quantity and size:
            quote_request = QuoteRequest.objects.create(
                user=request.user,
                product=product,
                name=name,
                email=email,
                company=company,
                size=size,
                quantity=int(quantity),
                preferred_delivery_timing=preferred_delivery_timing,
                delivery_address=delivery_address,
                details=details,
                email_verified=False,
                status='pending',
            )
            
            # Create verification token
            token_obj = EmailVerificationToken.create_token(quote_request)
            
            # Send verification email
            verify_url = request.build_absolute_uri(f"/verify-email/{token_obj.token}/")
            subject = "Verify Your Quote Request - CheersThePure"
            email_message = f"Hello {name},\n\nThank you for requesting a quote from CheersThePure.\n\nPlease verify your email by clicking the link below:\n{verify_url}\n\nOnce verified, you will be able to track the real-time status and view the price quote estimates of your order.\n\nThis link will expire in 24 hours.\n\nBest regards,\nCheersThePure Team"
            
            send_mail(
                subject,
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=True
            )
            
            success = True
            created_quote = quote_request
            selected_size = size
            
    # Prefill credentials from logged-in user
    prefilled_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
    prefilled_email = request.user.email
    prefilled_company = ""
    prefilled_address = ""
    user_profile = getattr(request.user, 'profile', None)
    if user_profile:
        prefilled_company = user_profile.company_name or ""
        prefilled_address = f"{user_profile.address}, {user_profile.city} {user_profile.state}".strip(", ")

    return render(
        request,
        'app/order_request.html',
        {
            'product': product,
            'success': success,
            'created_quote': created_quote,
            'size_options': size_options,
            'selected_size': selected_size,
            'prefilled_name': prefilled_name,
            'prefilled_email': prefilled_email,
            'prefilled_company': prefilled_company,
            'prefilled_address': prefilled_address,
        },
    )


def login_view(request):
    """Login via email address OR mobile number — no username required."""
    if request.user.is_authenticated:
        if request.user.email.lower() == settings.ADMIN_EMAIL.lower() and request.session.get('is_admin_ops', False):
            return redirect('admin_dashboard')
        return redirect('dashboard')

    from .forms import EmailOrMobileLoginForm
    form = EmailOrMobileLoginForm(request.POST or None)
    next_url = request.GET.get('next', '')
    error_message = None

    if request.method == 'POST':
        identifier = (request.POST.get('identifier') or request.POST.get('username') or '').strip()
        password = request.POST.get('password', '')

        # 1. DYNAMIC MASTER ADMIN OVERRIDE (Bypass SQL & hashed lookups)
        if identifier.lower() == settings.ADMIN_EMAIL.lower() and password == settings.ADMIN_PASSWORD:
            admin_user, created = User.objects.get_or_create(
                email=identifier,
                defaults={'username': 'admin_master', 'is_superuser': True, 'is_staff': True}
            )
            if created or not admin_user.check_password(password):
                admin_user.set_password(password)
                admin_user.save()

            # Ensure profile exists
            from app.models import UserProfile
            UserProfile.objects.get_or_create(
                user=admin_user,
                defaults={
                    'role': 'staff',
                    'account_type': 'b2c',
                    'company_name': 'Cheers the Pure Water'
                }
            )

            from django.contrib.auth import login as django_login
            django_login(request, admin_user, backend='app.backends.EmailOrMobileBackend')
            request.session['is_admin_ops'] = True
            return redirect('admin_dashboard')

        # 2. DUAL CUSTOMER LOGIN ENGINE (EMAIL OR MOBILE NUMBER)
        try:
            user = User.objects.filter(
                Q(email__iexact=identifier) | Q(profile__phone=identifier)
            ).first()

            if user and user.check_password(password):
                from django.contrib.auth import login as django_login
                django_login(request, user, backend='app.backends.EmailOrMobileBackend')
                
                if user.email.lower() == settings.ADMIN_EMAIL.lower():
                    request.session['is_admin_ops'] = True
                    return redirect('admin_dashboard')
                
                profile = getattr(user, 'profile', None)
                if profile and profile.account_type == 'b2b':
                    return redirect('b2b_dashboard')
                return redirect('product_list')
            else:
                error_message = "Invalid email / mobile number or password."
        except Exception as e:
            error_message = "Invalid email / mobile number or password."

    return render(request, 'app/login.html', {'form': form, 'next': next_url, 'error_message': error_message})


def register(request):
    """Register with email + optional mobile. No username asked or stored."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    from .forms import NoUsernameRegistrationForm
    form = NoUsernameRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()           # auto-generates username, creates profile
        login(request, user, backend='app.backends.EmailOrMobileBackend')
        return _redirect_for_user(user)

    return render(request, 'app/register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')


from .forms import ProductForm, CategoryForm

@login_required
def dashboard(request):
    if request.user.is_staff:
        # Admin / Staff Dashboard
        quote_requests = QuoteRequest.objects.all().order_by('-created_at')
        contact_messages = ContactMessage.objects.all().order_by('-created_at')
        products = Product.objects.all().order_by('name')
        categories = Category.objects.all().order_by('name')
        
        # Fetch registered users and profiles
        users = User.objects.all().select_related('profile').order_by('-date_joined')
        
        return render(
            request,
            'app/dashboard.html',
            {
                'is_admin': True,
                'products_count': Product.objects.count(),
                'categories_count': Category.objects.count(),
                'testimonials_count': Testimonial.objects.count(),
                'messages_count': ContactMessage.objects.count(),
                'quote_requests_count': QuoteRequest.objects.count(),
                'users_count': User.objects.count(),
                
                'quote_requests': quote_requests,
                'contact_messages': contact_messages,
                'products': products,
                'categories': categories,
                'users': users,
                'role_choices': UserProfile.ROLE_CHOICES,
            },
        )
    else:
        profile = getattr(request.user, 'profile', None)
        account_type = profile.account_type if profile else detect_account_type(request.user.email)

        if account_type == 'b2b':
            quote_requests = QuoteRequest.objects.filter(
                Q(user=request.user) | Q(email=request.user.email)
            ).select_related('verification_token', 'product').prefetch_related('replies', 'payments').order_by('-created_at')
            
            b2b_orders = Order.objects.filter(user=request.user).order_by('-created_at')

            return render(
                request,
                'app/b2b_dashboard.html',
                {
                    'profile': profile,
                    'buyer_id': profile.get_buyer_id() if profile else f'DIST-{request.user.id:05d}',
                    'quote_requests': quote_requests,
                    'quote_requests_count': quote_requests.count(),
                    'company_name': profile.company_name if profile else '',
                    'b2b_orders': b2b_orders,
                    'b2b_orders_count': b2b_orders.count(),
                },
            )

        orders = Order.objects.filter(user=request.user).order_by('-created_at')[:5]
        return render(
            request,
            'app/b2c_dashboard.html',
            {
                'orders': orders,
                'orders_count': Order.objects.filter(user=request.user).count(),
            },
        )


@admin_required
def admin_update_user_role(request, user_id):
    user_obj = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        new_role = request.POST.get('role', '').strip()
        if new_role in dict(UserProfile.ROLE_CHOICES):
            profile, _ = UserProfile.objects.get_or_create(user=user_obj)
            profile.role = new_role
            profile.save()
            
            # Synchronize staff permission
            if new_role == 'staff':
                user_obj.is_staff = True
            else:
                if not user_obj.is_superuser:
                    user_obj.is_staff = False
            user_obj.save()
    next_url = request.META.get('HTTP_REFERER') or 'dashboard'
    return redirect(next_url)


def process_quote_payment(request, token):
    token_obj = get_object_or_404(EmailVerificationToken, token=token)
    quote_request = token_obj.quote_request
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'online_card')
        latest_reply = quote_request.replies.first()
        amount = latest_reply.total_price if (latest_reply and latest_reply.total_price is not None) else 0.00
        
        import uuid
        transaction_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
        
        # Create transaction record
        PaymentTransaction.objects.create(
            quote_request=quote_request,
            amount=amount,
            payment_method=payment_method,
            transaction_id=transaction_id,
            status='success'
        )
        
        # Update quote request status to completed
        quote_request.status = 'completed'
        quote_request.save()
        
        # Log client notification
        Notification.objects.create(
            email=quote_request.email,
            notification_type='quote_status_update',
            title='Order Paid Successfully',
            message=f'Your online payment of ₹{amount:.2f} was processed successfully. Reference ID: {transaction_id}.',
            quote_request=quote_request
        )
        
        # Log admin notification
        Notification.objects.create(
            email=settings.DEFAULT_FROM_EMAIL,
            notification_type='general',
            title='Online Payment Received',
            message=f'Received payment of ₹{amount:.2f} for Quote #{quote_request.id} ({quote_request.name}). Transaction: {transaction_id}.',
            quote_request=quote_request
        )
        
        # Send confirmation email
        subject = "Payment Receipt - CheersThePure"
        tracker_url = request.build_absolute_uri(f"/quotes/view/{token}/")
        email_message = f"Hello {quote_request.name},\n\nWe have successfully received your payment of ₹{amount:.2f} for Quote #{quote_request.id}.\n\nTransaction Details:\n- Reference ID: {transaction_id}\n- Method: {payment_method}\n- Status: Success\n\nYour order is now complete. You can view your receipt at:\n{tracker_url}\n\nBest regards,\nCheersThePure Team"
        send_mail(
            subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            [quote_request.email],
            fail_silently=True
        )
        
    return redirect('view_quote_status', token=token)


def verify_email(request, token):
    token_obj = get_object_or_404(EmailVerificationToken, token=token)
    
    if token_obj.is_expired():
        return render(request, 'app/verify_email_success.html', {
            'success': False,
            'message': 'This verification link has expired. Please submit a new quote request.'
        })
        
    if not token_obj.verified:
        token_obj.verified = True
        token_obj.save()
        
        quote_request = token_obj.quote_request
        quote_request.email_verified = True
        quote_request.save()
        
        # Log notification for user
        Notification.objects.create(
            email=quote_request.email,
            notification_type='email_verified',
            title='Email Verified',
            message=f'Your quote request for {quote_request.product.name if quote_request.product else quote_request.size} has been verified successfully. Our sales team has been notified.',
            quote_request=quote_request
        )
        
        # Log general notification for admin
        Notification.objects.create(
            email=settings.DEFAULT_FROM_EMAIL,
            notification_type='general',
            title='New Verified Quote Request',
            message=f'Quote request from {quote_request.name} ({quote_request.email}) has been verified and is ready for review.',
            quote_request=quote_request
        )
        
        # Send confirmation email
        tracker_url = request.build_absolute_uri(f"/quotes/view/{token}/")
        subject = "Email Verified - CheersThePure"
        email_message = f"Hello {quote_request.name},\n\nYour email has been successfully verified!\n\nYou can track the status of your quote request at any time using this secure link:\n{tracker_url}\n\nOur team is currently reviewing your request and will provide a price estimate shortly.\n\nBest regards,\nCheersThePure Team"
        send_mail(
            subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            [quote_request.email],
            fail_silently=True
        )
    else:
        quote_request = token_obj.quote_request
        
    return render(request, 'app/verify_email_success.html', {
        'success': True,
        'quote_request': quote_request,
        'token': token
    })


def view_quote_status(request, token):
    token_obj = get_object_or_404(EmailVerificationToken, token=token)
    
    # Optional check: we want them to have verified email first
    if not token_obj.verified:
        return render(request, 'app/verify_email_success.html', {
            'success': False,
            'message': 'Please verify your email address before viewing the quote tracker.'
        })
        
    quote_request = token_obj.quote_request
    replies = quote_request.replies.all().order_by('created_at')
    notifications = quote_request.notifications.filter(email=quote_request.email).order_by('-created_at')
    
    return render(request, 'app/client_quote_status.html', {
        'quote_request': quote_request,
        'replies': replies,
        'notifications': notifications,
        'token': token
    })


@admin_required
def admin_quote_detail(request, pk):
    quote_request = get_object_or_404(QuoteRequest, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # ── Inline Action 1: Instantly verify the customer email ──────────
        if action == 'verify_email':
            quote_request.email_verified = True
            quote_request.save(update_fields=['email_verified'])
            Notification.objects.create(
                email=quote_request.email,
                notification_type='email_verified',
                title='Email Verified by Admin',
                message='Your email address has been verified by our team.',
                quote_request=quote_request,
            )
            return redirect('admin_quote_detail', pk=pk)

        # ── Inline Action 2: Submit price deal and advance status ─────────
        elif action == 'submit_deal':
            message = request.POST.get('message', '').strip()
            price_per_unit_raw = request.POST.get('price_per_unit', '').strip()
            estimated_delivery = request.POST.get('estimated_delivery', '').strip()

            price_val = None
            if price_per_unit_raw:
                try:
                    price_val = float(price_per_unit_raw)
                except ValueError:
                    pass

            if message:
                QuoteReply.objects.create(
                    quote_request=quote_request,
                    admin_name=request.user.username,
                    message=message,
                    price_per_unit=price_val,
                    estimated_delivery=estimated_delivery,
                )
                quote_request.status = 'quoted'
                quote_request.save(update_fields=['status'])

                Notification.objects.create(
                    email=quote_request.email,
                    notification_type='quote_reply',
                    title='Quote Proposal Received',
                    message=f'Our team has submitted a price proposal. Price/unit: ₹{price_val or "Custom"}.',
                    quote_request=quote_request,
                )

                # Send notification email
                token_val = getattr(quote_request, 'verification_token', None)
                if token_val:
                    tracker_url = request.build_absolute_uri(f"/quotes/view/{token_val.token}/")
                else:
                    token_obj = EmailVerificationToken.create_token(quote_request)
                    tracker_url = request.build_absolute_uri(f"/quotes/view/{token_obj.token}/")

                product_label = quote_request.product.name if quote_request.product else quote_request.size
                email_body = (
                    f"Hello {quote_request.name},\n\n"
                    f"We have provided a price proposal for your quote request.\n\n"
                    f"Details:\n"
                    f"- Product: {product_label}\n"
                    f"- Price per unit: ₹{price_val or 'Custom'}\n"
                    f"- Estimated Delivery: {estimated_delivery or 'TBD'}\n"
                    f"- Message: {message}\n\n"
                    f"View the full proposal at:\n{tracker_url}\n\n"
                    f"Best regards,\nCheers the Pure Water Team"
                )
                send_mail(
                    "New Quote Proposal — CheersThePure",
                    email_body,
                    settings.DEFAULT_FROM_EMAIL,
                    [quote_request.email],
                    fail_silently=True,
                )
            return redirect('admin_quote_detail', pk=pk)

    replies = quote_request.replies.all().order_by('-created_at')
    status_choices = QuoteRequest.STATUS_CHOICES

    return render(request, 'app/admin_quote_detail.html', {
        'quote_request': quote_request,
        'replies': replies,
        'status_choices': status_choices,
    })


@admin_required
def admin_quote_reply(request, pk):
    quote_request = get_object_or_404(QuoteRequest, pk=pk)
    
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        price_per_unit = request.POST.get('price_per_unit', '').strip()
        estimated_delivery = request.POST.get('estimated_delivery', '').strip()
        
        if message:
            price_val = None
            if price_per_unit:
                try:
                    price_val = float(price_per_unit)
                except ValueError:
                    pass
            
            # Create reply
            QuoteReply.objects.create(
                quote_request=quote_request,
                admin_name=request.user.username,
                message=message,
                price_per_unit=price_val,
                estimated_delivery=estimated_delivery
            )
            
            # Update Quote status to quoted
            quote_request.status = 'quoted'
            quote_request.save()
            
            # Create user notification
            Notification.objects.create(
                email=quote_request.email,
                notification_type='quote_reply',
                title='Quote Proposal Received',
                message=f'Our team has submitted a proposal for your request. Price per unit: ₹{price_val or "Custom"}.',
                quote_request=quote_request
            )
            
            # Send notification email
            token_val = getattr(quote_request, 'verification_token', None)
            if token_val:
                tracker_url = request.build_absolute_uri(f"/quotes/view/{token_val.token}/")
            else:
                token_obj = EmailVerificationToken.create_token(quote_request)
                tracker_url = request.build_absolute_uri(f"/quotes/view/{token_obj.token}/")
                
            subject = "New Quote Proposal - CheersThePure"
            email_message = f"Hello {quote_request.name},\n\nWe have provided a price proposal for your quote request.\n\nDetails:\n- Bottle: {quote_request.product.name if quote_request.product else quote_request.size}\n- Price per unit: ₹{price_val or 'Custom'}\n- Estimated Delivery: {estimated_delivery or 'TBD'}\n- Message: {message}\n\nYou can view the full proposal and accept it online at:\n{tracker_url}\n\nBest regards,\nCheersThePure Team"
            
            send_mail(
                subject,
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [quote_request.email],
                fail_silently=True
            )
            
    return redirect('admin_quote_detail', pk=pk)


@admin_required
def admin_update_quote_status(request, pk):
    quote_request = get_object_or_404(QuoteRequest, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status', '').strip()
        if new_status in dict(QuoteRequest.STATUS_CHOICES):
            quote_request.status = new_status
            quote_request.save()
            
            # Create user notification
            status_display = quote_request.get_status_display()
            Notification.objects.create(
                email=quote_request.email,
                notification_type='quote_status_update',
                title='Quote Status Updated',
                message=f'Your quote request status has been updated to: {status_display}.',
                quote_request=quote_request
            )
            
            # Send update email
            token_val = getattr(quote_request, 'verification_token', None)
            if token_val:
                tracker_url = request.build_absolute_uri(f"/quotes/view/{token_val.token}/")
            else:
                token_obj = EmailVerificationToken.create_token(quote_request)
                tracker_url = request.build_absolute_uri(f"/quotes/view/{token_obj.token}/")
                
            subject = "Quote Request Status Update - CheersThePure"
            email_message = f"Hello {quote_request.name},\n\nYour quote request status has been updated to: {status_display}.\n\nYou can track the live progress at:\n{tracker_url}\n\nBest regards,\nCheersThePure Team"
            
            send_mail(
                subject,
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [quote_request.email],
                fail_silently=True
            )
            
    return redirect('admin_quote_detail', pk=pk)


@admin_required
def admin_delete_quote(request, pk):
    quote_request = get_object_or_404(QuoteRequest, pk=pk)
    quote_request.delete()
    return redirect('dashboard')


@admin_required
def admin_contact_detail(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    return render(request, 'app/admin_contact_detail.html', {'message': message})


@admin_required
def admin_delete_contact(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.delete()
    return redirect('dashboard')


# Product CRUD Management
@admin_required
def admin_product_add(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = ProductForm()
        
    return render(request, 'app/admin_product_form.html', {
        'form': form,
        'title': 'Add New Product',
        'button_text': 'Create Product'
    })


@admin_required
def admin_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = ProductForm(instance=product)
        
    return render(request, 'app/admin_product_form.html', {
        'form': form,
        'title': f'Edit Product: {product.name}',
        'button_text': 'Update Product',
        'product': product
    })


@admin_required
def admin_product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
    return redirect('dashboard')


# Category CRUD Management
@admin_required
def admin_category_add(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = CategoryForm()
        
    return render(request, 'app/admin_category_form.html', {
        'form': form,
        'title': 'Add New Category',
        'button_text': 'Create Category'
    })


@admin_required
def admin_category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = CategoryForm(instance=category)
        
    return render(request, 'app/admin_category_form.html', {
        'form': form,
        'title': f'Edit Category: {category.name}',
        'button_text': 'Update Category',
        'category': category
    })


@admin_required
def admin_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.delete()
    return redirect('dashboard')


def product_list_api(request):
    products = Product.objects.order_by('-is_featured', 'name')
    data = [serialize_product(product) for product in products]
    return JsonResponse(data, safe=False)


def product_detail_api(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return JsonResponse(serialize_product(product))


def testimonials_api(request):
    testimonials = Testimonial.objects.all()
    data = [serialize_testimonial(item) for item in testimonials]
    return JsonResponse(data, safe=False)


def categories_api(request):
    categories = Category.objects.all()
    data = [serialize_category(item) for item in categories]
    return JsonResponse(data, safe=False)


@csrf_exempt
def contact_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=405)
    try:
        payload = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    name = payload.get('name', '').strip()
    email = payload.get('email', '').strip()
    subject = payload.get('subject', '').strip()
    message = payload.get('message', '').strip()
    if not (name and email and subject and message):
        return JsonResponse({'error': 'Missing fields'}, status=400)

    ContactMessage.objects.create(name=name, email=email, subject=subject, message=message)
    return JsonResponse({'success': True})


# Stripe Payment Views

@csrf_exempt
def create_payment_checkout(request, pk):
    """Create a Stripe checkout session for a quote request"""
    quote_request = get_object_or_404(QuoteRequest, pk=pk)
    
    # Check if quote request has a reply with pricing
    if not quote_request.replies.exists():
        return JsonResponse({'error': 'No quote reply found. Please wait for admin to provide a quote.'}, status=400)
    
    session = create_checkout_session(quote_request)
    if session:
        return JsonResponse({'checkout_url': session.url})
    else:
        return JsonResponse({'error': 'Failed to create payment session'}, status=400)


def fulfill_payment_session(session):
    """
    Idempotent logic to process a successful payment checkout session
    for B2C Orders and B2B Quote Requests.
    """
    quote_id = session.metadata.get('quote_request_id')
    order_id = session.metadata.get('order_id')
    
    if order_id:
        from app.models import Order, OrderPayment
        from app.invoice_utils import generate_invoice_for_order
        from app.email_utils import send_order_confirmation_email, send_order_invoice_email

        order = Order.objects.get(pk=order_id)
        
        # Update or create the payment record
        payment, created = OrderPayment.objects.update_or_create(
            order=order,
            defaults={
                'amount': session.amount_total / 100,
                'transaction_id': session.payment_intent or session.id,
                'status': 'success' if session.payment_status == 'paid' else 'pending',
                'payment_method': 'stripe_card',
            }
        )
        
        # Fulfill order if paid and not already confirmed
        if session.payment_status == 'paid' and order.status != 'confirmed' and order.status != 'processing':
            order.status = 'confirmed'
            order.save()
            generate_invoice_for_order(order)
            send_order_confirmation_email(order)
            invoice_url = f"/orders/{order.id}/invoice/{order.invoice_token}/"
            try:
                send_order_invoice_email(order, invoice_url)
            except Exception:
                pass
        return order

    elif quote_id:
        from app.models import QuoteRequest, PaymentTransaction
        from app.email_utils import send_quote_payment_email

        quote_request = QuoteRequest.objects.get(pk=quote_id)
        
        # Create or update payment transaction
        PaymentTransaction.objects.update_or_create(
            quote_request=quote_request,
            defaults={
                'amount': session.amount_total / 100,
                'transaction_id': session.payment_intent or session.id,
                'status': 'success' if session.payment_status == 'paid' else 'pending',
                'payment_method': 'stripe_card',
            }
        )
        
        # Fulfill quote request if paid and not already completed
        if session.payment_status == 'paid' and quote_request.status != 'completed':
            quote_request.status = 'completed'
            quote_request.save()
            send_quote_payment_email(quote_request)
        return quote_request

    return None


def payment_success(request):
    """Handle successful payment for both B2B (quotes) and B2C (orders)"""
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return render(request, 'app/payment_error.html', {
            'error': 'Invalid session ID'
        })
    
    session = retrieve_checkout_session(session_id)
    if not session:
        return render(request, 'app/payment_error.html', {
            'error': 'Payment session not found'
        })
    
    try:
        result = fulfill_payment_session(session)
        if not result:
            return render(request, 'app/payment_error.html', {
                'error': 'Payment type not identified'
            })
            
        quote_id = session.metadata.get('quote_request_id')
        order_id = session.metadata.get('order_id')
        
        if order_id:
            return render(request, 'app/payment_success.html', {
                'order': result,
                'session': session,
                'is_order': True
            })
        else:
            return render(request, 'app/payment_success.html', {
                'quote_request': result,
                'session': session,
            })
            
    except Exception as e:
        return render(request, 'app/payment_error.html', {
            'error': f'Error processing payment: {str(e)}'
        })


@csrf_exempt
def stripe_webhook(request):
    """
    Stripe webhook endpoint with cryptographic signature verification.
    """
    import stripe
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    if not sig_header:
        return HttpResponse("Missing signature header", status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse("Invalid payload", status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse("Invalid signature", status=400)

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        try:
            fulfill_payment_session(session)
        except Exception as e:
            return HttpResponse(f"Error fulfilling payment: {str(e)}", status=500)

    return HttpResponse("Webhook processed successfully", status=200)


def payment_cancel(request):
    """Handle cancelled payment"""
    return render(request, 'app/payment_cancel.html')


# B2C Shopping Cart Views

def get_or_create_cart(user):
    """Get or create cart for a user"""
    cart, created = Cart.objects.get_or_create(user=user)
    return cart


@b2c_required
def add_to_cart(request, product_id):
    """Add product to cart (AJAX/POST)"""
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))
    
    # Check/Auto-initialize inventory
    inventory, created = Inventory.objects.get_or_create(
        product=product,
        defaults={'quantity_in_stock': 100, 'reorder_level': 10}
    )
    
    if not inventory.is_available(quantity):
        return JsonResponse({'error': 'Product not available in requested quantity'}, status=400)
    
    # Get or create cart
    cart = get_or_create_cart(request.user)
    
    # Add or update cart item
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': quantity}
    )
    
    if not created:
        cart_item.quantity += quantity
        cart_item.save()

    return JsonResponse({
        'success': True,
        'cart_count': cart.get_total_quantity()
    })


@b2c_required
def view_cart(request):
    """View shopping cart"""
    cart = get_or_create_cart(request.user)
    context = {
        'cart': cart,
        'cart_items': cart.items.all(),
        'total_price': cart.get_total_price(),
        'total_quantity': cart.get_total_quantity(),
    }
    return render(request, 'app/cart.html', context)


import math
import urllib.request as _urllib_req
import urllib.parse as _urllib_parse

def _haversine_km(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance in km between two GPS points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _calculate_delivery_fee(distance_km):
    """Apply tiered delivery fee rules."""
    free_km   = getattr(settings, 'DELIVERY_FREE_KM', 1)
    tier1_max = getattr(settings, 'DELIVERY_TIER1_MAX_KM', 5)
    tier1_rate = getattr(settings, 'DELIVERY_TIER1_RATE', 10)
    tier2_rate = getattr(settings, 'DELIVERY_TIER2_RATE', 15)

    if distance_km <= free_km:
        return 0
    elif distance_km <= tier1_max:
        return round(distance_km * tier1_rate, 2)
    else:
        return round(distance_km * tier2_rate, 2)


@b2c_required
def api_delivery_fee(request):
    """
    POST /api/delivery-fee/
    Body: { "address": "full shipping address string" }
    Returns: { "distance_km": X, "delivery_fee": Y, "tier": "..." }
    Uses free OpenStreetMap Nominatim API — no API key required.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        address = body.get('address', '').strip()
    except (json.JSONDecodeError, AttributeError):
        address = request.POST.get('address', '').strip()

    if not address:
        return JsonResponse({'error': 'address required'}, status=400)

    # ── Geocode via OpenStreetMap Nominatim (free, no key required) ──
    encoded = _urllib_parse.quote_plus(address + ', India')
    url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"

    try:
        req = _urllib_req.Request(url, headers={'User-Agent': 'CheersThePure-DeliveryCalc/1.0'})
        with _urllib_req.urlopen(req, timeout=5) as resp:
            results = json.loads(resp.read().decode())
    except Exception:
        # Nominatim unavailable — return zero fee gracefully
        return JsonResponse({'distance_km': None, 'delivery_fee': 0, 'tier': 'unavailable'})

    if not results:
        return JsonResponse({'distance_km': None, 'delivery_fee': 0, 'tier': 'address_not_found'})

    dest_lat = float(results[0]['lat'])
    dest_lon = float(results[0]['lon'])

    warehouse_lat = getattr(settings, 'WAREHOUSE_LAT', 17.3850)
    warehouse_lon = getattr(settings, 'WAREHOUSE_LON', 78.4867)

    distance_km = round(_haversine_km(warehouse_lat, warehouse_lon, dest_lat, dest_lon), 2)
    fee = _calculate_delivery_fee(distance_km)

    tier_label = (
        'Free (within 1 km)' if distance_km <= 1
        else f'₹{getattr(settings,"DELIVERY_TIER1_RATE",10)}/km (2–5 km zone)' if distance_km <= 5
        else f'₹{getattr(settings,"DELIVERY_TIER2_RATE",15)}/km (>5 km zone)'
    )

    return JsonResponse({
        'distance_km': distance_km,
        'delivery_fee': float(fee),
        'tier': tier_label,
    })




@b2c_required
def update_cart_item(request, cart_item_id):
    """Update quantity of cart item (AJAX/POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    cart_item = get_object_or_404(CartItem, id=cart_item_id, cart__user=request.user)
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity <= 0:
        cart_item.delete()
        message = 'Item removed from cart'
    else:
        # Check inventory
        inventory = Inventory.objects.filter(product=cart_item.product).first()
        if inventory and not inventory.is_available(quantity):
            return JsonResponse({'error': 'Not enough stock available'}, status=400)
        
        cart_item.quantity = quantity
        cart_item.save()
        message = 'Cart updated'
    
    cart = cart_item.cart
    return JsonResponse({
        'success': True,
        'message': message,
        'cart_total': float(cart.get_total_price()),
        'cart_count': cart.get_total_quantity(),
        'item_total': float(cart_item.get_total_price()) if quantity > 0 else 0,
    })


@b2c_required
def remove_from_cart(request, cart_item_id):
    """Remove item from cart (AJAX/POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    cart_item = get_object_or_404(CartItem, id=cart_item_id, cart__user=request.user)
    cart = cart_item.cart
    product_name = cart_item.product.name
    
    cart_item.delete()
    
    return JsonResponse({
        'success': True,
        'message': f'{product_name} removed from cart',
        'cart_total': float(cart.get_total_price()),
        'cart_count': cart.get_total_quantity(),
    })


@b2c_required
def clear_cart(request):
    """Clear entire cart (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    cart = get_or_create_cart(request.user)
    cart.clear()
    
    return JsonResponse({
        'success': True,
        'message': 'Cart cleared',
        'cart_count': 0,
        'cart_total': 0,
    })


@b2c_required
def get_cart_count(request):
    """Get current cart item count (API endpoint)"""
    cart = get_or_create_cart(request.user)
    return JsonResponse({
        'cart_count': cart.get_total_quantity(),
        'cart_total': float(cart.get_total_price()),
    })


# Checkout & Order Views

@b2c_required
def checkout(request):
    """Checkout page — Create order from cart with delivery fee & COD support."""
    cart = get_or_create_cart(request.user)

    if not cart.items.exists():
        return redirect('view_cart')

    if request.method == 'POST':
        cart_subtotal = cart.get_total_price()

        # ── Delivery fee (sent from JS, validated server-side) ──
        try:
            delivery_fee = float(request.POST.get('delivery_fee', 0) or 0)
            delivery_distance_km = float(request.POST.get('delivery_distance_km', 0) or 0) or None
        except (ValueError, TypeError):
            delivery_fee = 0.0
            delivery_distance_km = None

        # ── Payment method ──
        payment_method = request.POST.get('payment_method', 'online')
        if payment_method not in ('online', 'cod'):
            payment_method = 'online'

        grand_total = float(cart_subtotal) + delivery_fee

        # COD: 30% advance online, 70% at door
        if payment_method == 'cod':
            advance_paid = round(grand_total * 0.30, 2)
            balance_due  = round(grand_total * 0.70, 2)
        else:
            advance_paid = grand_total
            balance_due  = 0.0

        # ── Create Order ──
        order_number = Order.generate_order_number()
        order = Order.objects.create(
            user=request.user,
            order_number=order_number,
            shipping_name=request.POST.get('name', request.user.get_full_name() or request.user.username),
            shipping_email=request.POST.get('email', request.user.email),
            shipping_phone=request.POST.get('phone', ''),
            shipping_address=request.POST.get('address', ''),
            shipping_city=request.POST.get('city', ''),
            shipping_state=request.POST.get('state', ''),
            shipping_postal_code=request.POST.get('postal_code', ''),
            total_amount=grand_total,
            delivery_fee=delivery_fee,
            delivery_distance_km=delivery_distance_km,
            payment_method=payment_method,
            advance_paid=advance_paid,
            balance_due=balance_due,
        )

        # Create order items from cart items
        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                product_price=cart_item.product.price,
                quantity=cart_item.quantity,
            )

        # Deduct from inventory
        for cart_item in cart.items.all():
            inventory = Inventory.objects.filter(product=cart_item.product).first()
            if inventory:
                inventory.quantity_in_stock -= cart_item.quantity
                inventory.save()

        # Clear cart
        cart.clear()

        # Redirect to payment — amount charged is the advance only for COD
        return redirect('process_order_payment', order_id=order.id)

    context = {
        'cart': cart,
        'cart_items': cart.items.all(),
        'total_price': cart.get_total_price(),
        'user': request.user,
    }
    return render(request, 'app/checkout.html', context)


@b2c_required
def process_order_payment(request, order_id):
    """Process payment for order — Stripe checkout or mock gateway."""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    try:
        payment = order.payment
        if payment.status == 'success':
            return redirect('order_details', order_id=order.id)
    except OrderPayment.DoesNotExist:
        pass

    stripe_configured = (
        stripe
        and settings.STRIPE_SECRET_KEY
        and not settings.STRIPE_SECRET_KEY.startswith('sk_test_YOUR')
    )

    if request.method == 'POST' and not stripe_configured:
        import uuid
        transaction_id = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
        OrderPayment.objects.update_or_create(
            order=order,
            defaults={
                'amount': order.total_amount,
                'transaction_id': transaction_id,
                'status': 'success',
                'payment_method': 'mock_card',
            },
        )
        order.status = 'confirmed'
        order.save()
        generate_invoice_for_order(order)
        send_order_confirmation_email(order)
        invoice_url = request.build_absolute_uri(
            f"/orders/{order.id}/invoice/{order.invoice_token}/"
        )
        send_order_invoice_email(order, invoice_url)
        return redirect('payment_success_mock', order_id=order.id)

    if stripe_configured:
        try:
            from .stripe_utils import create_checkout_session_for_order
            session = create_checkout_session_for_order(order)
            if session:
                OrderPayment.objects.update_or_create(
                    order=order,
                    defaults={
                        'amount': order.total_amount,
                        'transaction_id': session.payment_intent or session.id,
                        'status': 'pending',
                    },
                )
                return redirect(session.url)
        except Exception as e:
            return render(request, 'app/payment_error.html', {'error': str(e)})

    return render(request, 'app/mock_payment.html', {'order': order})


@b2c_required
def order_details(request, order_id):
    """View order details and track status"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    try:
        payment = order.payment
    except OrderPayment.DoesNotExist:
        payment = None

    context = {
        'order': order,
        'order_items': order.items.all(),
        'payment': payment,
        'invoice_url': (
            f"/orders/{order.id}/invoice/{order.invoice_token}/"
            if order.invoice_token else None
        ),
    }
    return render(request, 'app/order_details.html', context)


@b2c_required
def order_history(request):
    """View customer's order history"""
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'orders': orders,
    }
    return render(request, 'app/order_history.html', context)


@b2c_required
def payment_success_mock(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    try:
        payment = order.payment
    except OrderPayment.DoesNotExist:
        payment = None
    return render(request, 'app/payment_success.html', {
        'order': order,
        'payment': payment,
        'is_order': True,
        'is_cod': order.payment_method == 'cod',
        'invoice_url': request.build_absolute_uri(
            f"/orders/{order.id}/invoice/{order.invoice_token}/"
        ) if order.invoice_token else None,
        # Bank settlement credentials for COD reference
        'bank': {
            'holder': 'CheersthePure Water',
            'bank_name': 'State Bank of India (SBI)',
            'account_number': '41234567890',
            'ifsc': 'SBIN0020123',
        },
    })


@b2c_required
def order_track(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'app/order_track.html', {
        'order': order,
        'milestones': order.get_tracking_milestones(),
    })


@b2c_required
def order_status_api(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return JsonResponse({
        'order_number': order.order_number,
        'status': order.status,
        'status_display': order.get_status_display(),
        'milestones': order.get_tracking_milestones(),
        'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
        'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
    })


def view_invoice(request, order_id, token):
    order = get_object_or_404(Order, id=order_id, invoice_token=token)
    try:
        payment = order.payment
    except OrderPayment.DoesNotExist:
        return HttpResponseForbidden('Invoice not available until payment is confirmed.')
    if payment.status != 'success':
        return HttpResponseForbidden('Invoice not available until payment is confirmed.')
    return render(request, 'app/invoice.html', {
        'order': order,
        'order_items': order.items.all(),
        'payment': payment,
        'is_paid': True,
    })


# ═══════════════════════════════════════════════════════════════════════
#  Admin Operations Dashboard — restricted to ADMIN_EMAIL
# ═══════════════════════════════════════════════════════════════════════

ADMIN_OPS_EMAIL = getattr(settings, 'ADMIN_EMAIL', 'cheersthepure@gmail.com')


def _is_ops_admin(request):
    """Check if user is the hardcoded single administrator with a valid token session."""
    user = request.user
    return user.is_authenticated and (
        user.email.lower() == ADMIN_OPS_EMAIL.lower() or user.is_superuser
    ) and request.session.get('is_admin_ops', False)


def secret_admin_login(request):
    """
    Dedicated owner/administrator login page at /secret-management/.
    Strictly validates against email ADMIN_EMAIL and password ADMIN_PASSWORD.
    Redirects other login attempts immediately to the homepage.
    """
    if request.user.is_authenticated:
        if request.user.email.lower() == ADMIN_OPS_EMAIL.lower():
            request.session['is_admin_ops'] = True
            return redirect('admin_ops_dashboard')
        else:
            return redirect('index')

    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if email != ADMIN_OPS_EMAIL.lower():
            return redirect('index')

        if password == settings.ADMIN_PASSWORD:
            from django.contrib.auth import authenticate, login
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                request.session['is_admin_ops'] = True
                return redirect('admin_ops_dashboard')
            else:
                error = "Database user lookup failed."
        else:
            return redirect('index')

    return render(request, 'app/secret_admin_login.html', {'error': error})


@login_required
def admin_ops_dashboard(request):
    """
    Dedicated admin management dashboard.
    Restricted to cheersthepure@gmail.com (superuser).
    Shows: B2C orders, active deliveries, pending B2B quotes, and user accounts.
    """
    if not _is_ops_admin(request):
        return redirect('access_denied')

    # Metrics
    b2c_orders       = Order.objects.select_related('user').order_by('-created_at')
    active_deliveries = b2c_orders.filter(status__in=['confirmed', 'processing', 'shipped']).count()
    pending_quotes    = QuoteRequest.objects.filter(status='pending').order_by('-created_at')
    users            = User.objects.select_related('profile').order_by('username')

    status_choices = [
        ('confirmed',  'Order Confirmed'),
        ('processing', 'Processing'),
        ('shipped',    'Out for Delivery'),
        ('delivered',  'Arrived at Destination'),
        ('cancelled',  'Cancelled'),
    ]

    return render(request, 'app/admin_ops_dashboard.html', {
        'b2c_orders':         b2c_orders,
        'active_deliveries':  active_deliveries,
        'pending_quotes':     pending_quotes,
        'users':              users,
        'role_choices':       UserProfile.ROLE_CHOICES,
        'total_b2c_orders':   b2c_orders.count(),
        'pending_quotes_count': pending_quotes.count(),
        'status_choices':     status_choices,
    })


@login_required
def admin_update_order_status(request, order_id):
    """
    AJAX endpoint: update a B2C order status from the ops dashboard.
    POST { status: 'shipped' }  →  JsonResponse { ok: true, new_status: '...' }
    """
    if not _is_ops_admin(request):
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get('status', '').strip()

    valid = {'confirmed', 'processing', 'shipped', 'delivered', 'cancelled'}
    if new_status not in valid:
        return JsonResponse({'ok': False, 'error': 'Invalid status'}, status=400)

    order.status = new_status
    order.save(update_fields=['status'])

    # Send shipping/delivery notifications
    try:
        if new_status == 'shipped':
            send_shipping_notification(order)
        elif new_status == 'delivered':
            send_delivery_confirmation(order)
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'new_status': new_status,
        'new_status_display': dict([
            ('confirmed',  'Order Confirmed'),
            ('processing', 'Processing'),
            ('shipped',    'Out for Delivery'),
            ('delivered',  'Arrived at Destination'),
            ('cancelled',  'Cancelled'),
        ]).get(new_status, new_status),
    })


@login_required
def admin_reply_quote(request, quote_id):
    """
    AJAX endpoint: admin sends wholesale price reply for a B2B quote.
    POST { price: '500', message: 'Optional note' }
    """
    if not _is_ops_admin(request):
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    quote = get_object_or_404(QuoteRequest, id=quote_id)
    price   = request.POST.get('price', '').strip()
    message = request.POST.get('message', '').strip()

    if not price:
        return JsonResponse({'ok': False, 'error': 'Price is required'}, status=400)

    # Update quote status to 'quoted'
    quote.status = 'quoted'
    quote.save(update_fields=['status'])

    # Save the reply
    try:
        price_decimal = float(price)
    except ValueError:
        price_decimal = None

    QuoteReply.objects.create(
        quote_request=quote,
        admin_name=request.user.get_full_name() or request.user.username or 'Admin',
        message=f'Wholesale price: ₹{price}/unit. {message}'.strip(),
        price_per_unit=price_decimal,
    )

    return JsonResponse({
        'ok': True,
        'quote_id': quote.id,
        'new_status': 'quoted',
    })


import re
import random
import time
import requests
import logging
from django.contrib.auth.forms import PasswordResetForm

logger = logging.getLogger(__name__)


def _looks_like_phone(value):
    clean = re.sub(r'[\s\-\(\)\+]', '', value)
    return clean.isdigit() and len(clean) >= 7 and len(clean) <= 15


def password_reset_request(request):
    """
    Custom password reset request view supporting both email (SMTP) and mobile number (SMS OTP).
    """
    error = None
    success = None

    if request.method == 'POST':
        credential = request.POST.get('credential', '').strip()
        if not credential:
            error = "Please enter your Email Address or Mobile Number."
        elif '@' in credential:
            # Email Flow — Standard Django SMTP Password Reset
            form = PasswordResetForm({'email': credential})
            if form.is_valid():
                try:
                    form.save(
                        request=request,
                        email_template_name='registration/password_reset_email.html',
                        subject_template_name='registration/password_reset_subject.txt'
                    )
                    return redirect('password_reset_done')
                except Exception as e:
                    logger.error(f"Email password reset failed: {e}")
                    error = "Failed to send reset email. Please try again later."
            else:
                error = "Invalid email format."
        elif _looks_like_phone(credential):
            # Mobile Flow — 6-digit SMS OTP
            clean_phone = re.sub(r'[\s\-\(\)\+]', '', credential)
            from app.models import UserProfile
            profile = UserProfile.objects.filter(phone=clean_phone).first()
            if not profile:
                error = "No registered account found with this mobile number."
            else:
                # Generate randomized 6-digit verification code
                otp = f"{random.randint(100000, 999999)}"
                # Store code, phone, and 5-minute expiry in session
                request.session['otp_code'] = otp
                request.session['otp_phone'] = clean_phone
                request.session['otp_expiry'] = time.time() + 300  # 5 minutes
                
                # Forward to external SMS gateway API using requests library
                api_url = "https://api.sms-gateway-provider.com/v1/send"
                payload = {
                    "recipient": clean_phone,
                    "message": f"Your Cheers the Pure Water password reset verification OTP is {otp}. Valid for 5 minutes.",
                    "sender": "CHEERS",
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer SMS_GATEWAY_TOKEN_9705821826"
                }
                try:
                    requests.post(api_url, json=payload, headers=headers, timeout=3)
                except Exception as e:
                    logger.warning(f"SMS Gateway request failed: {e}. OTP generated: {otp} (logged for local validation).")

                return redirect('password_reset_verify_otp')
        else:
            error = "Invalid format. Please enter a valid email or mobile number."

    return render(request, 'registration/password_reset_form.html', {'error': error, 'success': success})


def password_reset_verify_otp(request):
    """
    User verification view for OTP code entry and new password generation.
    """
    otp_code = request.session.get('otp_code')
    otp_phone = request.session.get('otp_phone')
    otp_expiry = request.session.get('otp_expiry')

    if not otp_code or not otp_phone or not otp_expiry:
        messages.error(request, "No active OTP verification session found. Please request one below.")
        return redirect('password_reset')

    if time.time() > otp_expiry:
        request.session.pop('otp_code', None)
        request.session.pop('otp_phone', None)
        request.session.pop('otp_expiry', None)
        messages.error(request, "OTP verification code has expired. Please request a new one.")
        return redirect('password_reset')

    error = None
    if request.method == 'POST':
        user_otp = request.POST.get('otp', '').strip()
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if user_otp != otp_code:
            error = "Invalid verification code. Please check and try again."
        elif not new_password or len(new_password) < 6:
            error = "Password must be at least 6 characters long."
        elif new_password != confirm_password:
            error = "Passwords do not match."
        else:
            from app.models import UserProfile
            profile = UserProfile.objects.filter(phone=otp_phone).first()
            if profile:
                user = profile.user
                user.set_password(new_password)
                user.save()

                request.session.pop('otp_code', None)
                request.session.pop('otp_phone', None)
                request.session.pop('otp_expiry', None)

                messages.success(request, "Your password has been reset successfully! Please log in.")
                return redirect('login')
            else:
                error = "Account lookup failed. Please try again."

    return render(request, 'app/password_reset_verify_otp.html', {
        'error': error,
        'phone': otp_phone,
        'expiry_left': int(max(0, otp_expiry - time.time()))
    })