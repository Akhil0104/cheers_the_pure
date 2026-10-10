from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import uuid
from datetime import timedelta

class Category(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class Product(models.Model):
    CAPACITY_CHOICES = [
        ('250 ml', '250 ml'),
        ('500 ml', '500 ml'),
        ('1000 ml', '1 Ltr'),
        ('2 litres', '2 litres'),
    ]

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=255)
    capacity = models.CharField(max_length=100, choices=CAPACITY_CHOICES)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    is_featured = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.capacity})"

class Testimonial(models.Model):
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True)
    quote = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.company or self.role}"

class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.subject}"

class QuoteRequest(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='quote_requests',
        null=True,
        blank=True,
    )
    SIZE_CHOICES = [
        ('250 ml', '250 ml'),
        ('500 ml', '500 ml'),
        ('1000 ml', '1 Ltr'),
        ('2 litres', '2 litres'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('contacted', 'Contacted by Admin'),
        ('quoted', 'Quote Provided'),
        ('completed', 'Completed'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name='quote_requests',
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=150)
    email = models.EmailField()
    company = models.CharField(max_length=200, blank=True)
    size = models.CharField(max_length=50, choices=SIZE_CHOICES, default='500 ml')
    quantity = models.PositiveIntegerField(default=1)
    preferred_delivery_timing = models.CharField(
        max_length=150,
        blank=True,
        help_text='Preferred delivery timing (e.g. Urgent / Within 48h, Weekly supply, Specific Date)',
    )
    delivery_address = models.TextField(
        blank=True,
        help_text='Wholesale shipment delivery address',
    )
    details = models.TextField(blank=True)
    inquiry_idempotency_key = models.CharField(max_length=36, unique=True, null=True, blank=True, editable=False)
    email_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.product or 'Quote request'}"


class EmailVerificationToken(models.Model):
    quote_request = models.OneToOneField(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name='verification_token',
    )
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Token for {self.quote_request.email}"

    def is_expired(self):
        return timezone.now() > self.expires_at

    @staticmethod
    def create_token(quote_request):
        token = str(uuid.uuid4())
        expires_at = timezone.now() + timedelta(hours=24)
        verification_token, created = EmailVerificationToken.objects.update_or_create(
            quote_request=quote_request,
            defaults={'token': token, 'expires_at': expires_at, 'verified': False}
        )
        return verification_token


class QuoteReply(models.Model):
    quote_request = models.ForeignKey(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    admin_name = models.CharField(max_length=150)
    message = models.TextField()
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_delivery = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Reply to {self.quote_request.name} by {self.admin_name}"

    @property
    def total_price(self):
        if self.price_per_unit is not None:
            return self.price_per_unit * self.quote_request.quantity
        return None



class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('email_verified', 'Email Verified'),
        ('quote_reply', 'Quote Reply'),
        ('quote_status_update', 'Status Update'),
        ('general', 'General Notification'),
    ]

    email = models.EmailField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    quote_request = models.ForeignKey(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_read']),
            models.Index(fields=['email', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} for {self.email}"

    def mark_as_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save()


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('distributor', 'Distributor / Wholesaler'),
        ('partner', 'Hospitality / Event Partner'),
        ('staff', 'Business Staff / Admin'),
    ]
    ACCOUNT_TYPE_CHOICES = [
        ('b2c', 'B2C Retail Customer'),
        ('b2b', 'B2B Corporate Account'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    buyer_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Stable unique identifier for B2B distributor / customer (e.g. DIST-00042, CUST-00010)',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPE_CHOICES, default='b2c')
    company_name = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=200, blank=True)  # AI-inferred via Ollama for B2B accounts
    phone = models.CharField(max_length=20, blank=True)
    
    # Delivery & Business Information
    address = models.TextField(blank=True, help_text='Primary billing / delivery address')
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    gstin = models.CharField(max_length=30, blank=True, help_text='GSTIN / Tax ID for B2B wholesale invoicing')
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} [{self.get_buyer_id()}] — {self.get_account_type_display()}"

    def get_buyer_id(self):
        """Return stable unique buyer identity."""
        if self.buyer_id:
            return self.buyer_id
        if self.user_id:
            prefix = 'DIST' if self.account_type == 'b2b' else 'CUST'
            return f"{prefix}-{self.user_id:05d}"
        return f"BUYER-{uuid.uuid4().hex[:8].upper()}"

    def get_order_history(self):
        """Return all orders placed by this user."""
        return self.user.orders.all().order_by('-created_at')

    def get_quote_history(self):
        """Return all B2B quote requests placed by this user."""
        return self.user.quote_requests.all().order_by('-created_at')

    def save(self, *args, **kwargs):
        if not self.buyer_id and self.user_id:
            self.buyer_id = self.get_buyer_id()
        super().save(*args, **kwargs)

    @property
    def is_b2c(self):
        return self.account_type == 'b2c'

    @property
    def is_b2b(self):
        return self.account_type == 'b2b'


class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    quote_request = models.ForeignKey(QuoteRequest, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='online_card')
    transaction_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment of ₹{self.amount} for Quote #{self.quote_request.id} ({self.status})"


# B2C E-Commerce Models (Shopping Cart & Orders)

class Cart(models.Model):
    """Shopping cart for B2C customers"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Cart for {self.user.username}"

    def get_total_price(self):
        """Calculate total price of all items in cart"""
        return sum(item.get_total_price() for item in self.items.all())

    def get_total_quantity(self):
        """Get total quantity of items in cart"""
        return sum(item.quantity for item in self.items.all())

    def clear(self):
        """Clear all items from cart"""
        self.items.all().delete()


class CartItem(models.Model):
    """Individual item in shopping cart"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cart', 'product')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.product.name} x {self.quantity} in {self.cart.user.username}'s cart"

    def get_total_price(self):
        """Calculate total price for this cart item"""
        return self.product.price * self.quantity


class Order(models.Model):
    """B2C Order for direct retail purchases"""
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    guest_email = models.EmailField(blank=True)  # For guest checkout
    order_number = models.CharField(max_length=50, unique=True)
    
    # Shipping Details
    shipping_name = models.CharField(max_length=150)
    shipping_email = models.EmailField()
    shipping_phone = models.CharField(max_length=20)
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100)
    shipping_postal_code = models.CharField(max_length=10)
    
    # Order Details
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='pending')

    # Delivery logistics
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    delivery_distance_km = models.FloatField(null=True, blank=True)

    # Payment split (COD: 30% advance online, 70% at delivery)
    PAYMENT_METHOD_CHOICES = [
        ('online', 'Pay Online (Full)'),
        ('cod', 'Cash on Delivery (30% Advance)'),
    ]
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='online')
    advance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Invoice
    invoice_token = models.CharField(max_length=64, unique=True, blank=True)
    invoice_generated_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['shipping_email']),
        ]

    def __str__(self):
        return f"Order {self.order_number} - {self.shipping_name}"

    def get_customer_email(self):
        """Get email for order notifications"""
        if self.user:
            return self.user.email
        return self.guest_email

    @staticmethod
    def generate_order_number():
        """Generate unique order number"""
        from django.utils import timezone
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        import random
        random_suffix = random.randint(1000, 9999)
        return f"ORD-{timestamp}-{random_suffix}"

    def ensure_invoice_token(self):
        if not self.invoice_token:
            self.invoice_token = uuid.uuid4().hex
        return self.invoice_token

    def get_tracking_milestones(self):
        """Return ordered milestone dicts for the order tracking timeline."""
        status_order = ['confirmed', 'processing', 'shipped', 'delivered']
        labels = {
            'confirmed': 'Order Confirmed',
            'processing': 'Processing',
            'shipped': 'Shipped',
            'delivered': 'Delivered',
        }
        current_idx = status_order.index(self.status) if self.status in status_order else -1
        if self.status == 'pending':
            current_idx = -1
        milestones = []
        for idx, key in enumerate(status_order):
            if self.status == 'cancelled':
                state = 'cancelled' if idx == 0 else 'pending'
            elif idx < current_idx:
                state = 'completed'
            elif idx == current_idx:
                state = 'active'
            else:
                state = 'pending'
            milestones.append({'key': key, 'label': labels[key], 'state': state})
        return milestones


class OrderItem(models.Model):
    """Individual item in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)  # Store product name in case it's deleted
    product_price = models.DecimalField(max_digits=10, decimal_places=2)  # Store price at purchase time
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product_name} x {self.quantity} in Order {self.order.order_number}"

    def get_total_price(self):
        """Calculate total price for this order item"""
        return self.product_price * self.quantity


class OrderPayment(models.Model):
    """Payment transaction for B2C orders"""
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='stripe_card')
    transaction_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment ₹{self.amount} for {self.order.order_number} ({self.status})"


class Inventory(models.Model):
    """Track product inventory/stock levels"""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='inventory')
    quantity_in_stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)  # Alert when stock falls below this
    last_restocked = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Inventories'

    def __str__(self):
        return f"{self.product.name} - {self.quantity_in_stock} in stock"

    def is_low_stock(self):
        """Check if stock is low"""
        return self.quantity_in_stock <= self.reorder_level

    def is_available(self, quantity):
        """Check if product is available in requested quantity"""
        return self.quantity_in_stock >= quantity
