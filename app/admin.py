from django.contrib import admin

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
from .email_utils import send_shipping_notification, send_delivery_confirmation


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'description')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'capacity', 'price', 'is_featured', 'created_at')
    list_filter = ('category', 'is_featured')
    search_fields = ('name', 'description')


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'company', 'created_at')
    search_fields = ('name', 'role', 'company', 'quote')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'company', 'product', 'quantity', 'email_verified', 'status', 'created_at')
    list_filter = ('status', 'email_verified', 'product')
    search_fields = ('name', 'email', 'company', 'details')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('quote_request', 'token', 'expires_at', 'verified', 'created_at')
    list_filter = ('verified',)
    search_fields = ('quote_request__email', 'token')


@admin.register(QuoteReply)
class QuoteReplyAdmin(admin.ModelAdmin):
    list_display = ('quote_request', 'admin_name', 'price_per_unit', 'estimated_delivery', 'created_at')
    search_fields = ('quote_request__name', 'quote_request__email', 'admin_name', 'message')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('email', 'title', 'message')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'account_type', 'role', 'company_name', 'phone', 'created_at')
    list_filter = ('account_type', 'role')
    search_fields = ('user__username', 'user__email', 'company_name', 'phone')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('quote_request', 'amount', 'payment_method', 'transaction_id', 'status', 'created_at')
    list_filter = ('status', 'payment_method')
    search_fields = ('quote_request__name', 'transaction_id')


# B2C E-Commerce Admin

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_total_quantity', 'get_total_price', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')

    def get_total_quantity(self, obj):
        return obj.get_total_quantity()
    get_total_quantity.short_description = 'Items'

    def get_total_price(self, obj):
        return f"₹{obj.get_total_price()}"
    get_total_price.short_description = 'Total Price'


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity', 'get_total_price', 'added_at')
    list_filter = ('product', 'added_at')
    search_fields = ('cart__user__username', 'product__name')
    readonly_fields = ('added_at', 'updated_at')

    def get_total_price(self, obj):
        return f"₹{obj.get_total_price()}"
    get_total_price.short_description = 'Total'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'shipping_name', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'shipping_name', 'shipping_email', 'shipping_phone')
    readonly_fields = ('order_number', 'created_at', 'updated_at', 'shipped_at', 'delivered_at')
    actions = ['mark_as_processing', 'mark_as_shipped', 'mark_as_delivered', 'mark_as_cancelled']
    
    fieldsets = (
        ('Order Info', {
            'fields': ('order_number', 'user', 'guest_email', 'total_amount', 'status')
        }),
        ('Shipping Details', {
            'fields': ('shipping_name', 'shipping_email', 'shipping_phone', 'shipping_address', 'shipping_city', 'shipping_state', 'shipping_postal_code')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'shipped_at', 'delivered_at'),
            'classes': ('collapse',)
        }),
    )
    
    def mark_as_processing(self, request, queryset):
        """Mark selected orders as processing"""
        updated = queryset.update(status='processing')
        self.message_user(request, f'{updated} order(s) marked as processing.')
    mark_as_processing.short_description = 'Mark selected orders as processing'
    
    def mark_as_shipped(self, request, queryset):
        """Mark selected orders as shipped"""
        from django.utils import timezone
        updated = queryset.update(status='shipped', shipped_at=timezone.now())
        self.message_user(request, f'{updated} order(s) marked as shipped.')
        
        # Send shipping notification emails
        for order in queryset:
            send_shipping_notification(order)
    mark_as_shipped.short_description = 'Mark selected orders as shipped'
    
    def mark_as_delivered(self, request, queryset):
        """Mark selected orders as delivered"""
        from django.utils import timezone
        updated = queryset.update(status='delivered', delivered_at=timezone.now())
        self.message_user(request, f'{updated} order(s) marked as delivered.')
        
        # Send delivery confirmation emails
        for order in queryset:
            send_delivery_confirmation(order)
    mark_as_delivered.short_description = 'Mark selected orders as delivered'
    
    def mark_as_cancelled(self, request, queryset):
        """Mark selected orders as cancelled and restore inventory"""
        from django.utils import timezone
        
        for order in queryset:
            # Restore inventory
            for item in order.items.all():
                inventory = Inventory.objects.filter(product=item.product).first()
                if inventory:
                    inventory.quantity_in_stock += item.quantity
                    inventory.save()
            
            # Update order status
            order.status = 'cancelled'
            order.save()
        
        updated = queryset.count()
        self.message_user(request, f'{updated} order(s) cancelled and inventory restored.')
    mark_as_cancelled.short_description = 'Cancel selected orders & restore inventory'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'quantity', 'product_price', 'get_total_price')
    list_filter = ('order__created_at', 'product')
    search_fields = ('order__order_number', 'product_name')
    readonly_fields = ('created_at',)

    def get_total_price(self, obj):
        return f"₹{obj.get_total_price()}"
    get_total_price.short_description = 'Total'


@admin.register(OrderPayment)
class OrderPaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'amount', 'payment_method', 'transaction_id', 'status', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('order__order_number', 'transaction_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity_in_stock', 'reorder_level', 'is_low_stock', 'last_restocked')
    list_filter = ('last_restocked',)
    search_fields = ('product__name',)
    readonly_fields = ('updated_at',)

    def is_low_stock(self, obj):
        return obj.is_low_stock()
    is_low_stock.boolean = True
    is_low_stock.short_description = 'Low Stock'


# --- ANTI-GRAVITY B2B CLEANUP ---
from django.contrib.auth.models import Group

# Hide unnecessary retail models from the corporate admin dashboard
models_to_hide = [Cart, CartItem, Product, Inventory, Order, OrderItem, OrderPayment, Group]

for model in models_to_hide:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass


