# app/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from ai_builder import views as ai_builder_views

urlpatterns = [
    path('builder/', ai_builder_views.workspace, name='site_builder'),
    path('builder/share/<uuid:share_token>/', ai_builder_views.shared_site, name='shared_site'),
    path('api/site-builder/sites/', ai_builder_views.site_collection, name='site_builder_sites'),
    path('api/site-builder/sites/<uuid:site_id>/', ai_builder_views.site_detail, name='site_builder_site'),
    path('api/site-builder/sites/<uuid:site_id>/publish/', ai_builder_views.publish_site, name='site_builder_publish'),
    path('api/site-builder/generate/', ai_builder_views.generate_site, name='site_builder_generate'),
    path('api/site-builder/refine/', ai_builder_views.refine_section, name='site_builder_refine'),
    path('api/site-builder/business-assistant/', ai_builder_views.business_assistant, name='site_builder_business_assistant'),
    path('api/site-builder/inquiry/', ai_builder_views.submit_inquiry, name='site_builder_inquiry'),
    path('api/v1/inquiry/submit/', ai_builder_views.submit_inquiry, name='saassum_inquiry_submit'),
    path('', views.index, name='index'),
    path('products/', views.products, name='products'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('categories/', views.categories, name='categories'),
    path('categories/<int:pk>/', views.category_detail, name='category_detail'),
    path('about/', views.about, name='about'),
    path('order/', views.order_request, name='order_request'),
    path('order/<int:pk>/', views.order_request, name='order_request_product'),
    
    # Email verification & client-side quote status tracking
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('quotes/view/<str:token>/', views.view_quote_status, name='view_quote_status'),
    path('quotes/view/<str:token>/pay/', views.process_quote_payment, name='process_quote_payment'),
    
    # User account views & Dashboard
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('secret-management/', views.secret_admin_login, name='secret_admin_login'),
    path('access-denied/', views.access_denied, name='access_denied'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Password Reset flow (Custom Email SMTP & Mobile SMS OTP)
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/verify-otp/', views.password_reset_verify_otp, name='password_reset_verify_otp'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    
    # Admin User management in dashboard
    path('dashboard/users/<int:user_id>/role/', views.admin_update_user_role, name='admin_update_user_role'),
    
    # Admin dashboard specific management views
    path('dashboard/quote/<int:pk>/', views.admin_quote_detail, name='admin_quote_detail'),
    path('dashboard/quote/<int:pk>/reply/', views.admin_quote_reply, name='admin_quote_reply'),
    path('dashboard/quote/<int:pk>/status/', views.admin_update_quote_status, name='admin_update_quote_status'),
    path('dashboard/quote/<int:pk>/delete/', views.admin_delete_quote, name='admin_delete_quote'),
    path('dashboard/contact/<int:pk>/', views.admin_contact_detail, name='admin_contact_detail'),
    path('dashboard/contact/<int:pk>/delete/', views.admin_delete_contact, name='admin_delete_contact'),
    
    # Product CRUD on dashboard
    path('dashboard/product/add/', views.admin_product_add, name='admin_product_add'),
    path('dashboard/product/<int:pk>/edit/', views.admin_product_edit, name='admin_product_edit'),
    path('dashboard/product/<int:pk>/delete/', views.admin_product_delete, name='admin_product_delete'),
    
    # Category CRUD on dashboard
    path('dashboard/category/add/', views.admin_category_add, name='admin_category_add'),
    path('dashboard/category/<int:pk>/edit/', views.admin_category_edit, name='admin_category_edit'),
    path('dashboard/category/<int:pk>/delete/', views.admin_category_delete, name='admin_category_delete'),

    # API endpoints
    path('api/products/', views.product_list_api, name='api_products'),
    path('api/products/<int:pk>/', views.product_detail_api, name='api_product_detail'),
    path('api/testimonials/', views.testimonials_api, name='api_testimonials'),
    path('api/categories/', views.categories_api, name='api_categories'),
    
    # Stripe Payment endpoints
    path('payment/checkout/<int:pk>/', views.create_payment_checkout, name='create_payment_checkout'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('payment-cancel/', views.payment_cancel, name='payment_cancel'),
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    
    # B2C Shopping Cart endpoints
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/item/<int:cart_item_id>/update/', views.update_cart_item, name='update_cart_item'),
    path('cart/item/<int:cart_item_id>/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
    path('api/cart/count/', views.get_cart_count, name='get_cart_count'),
    path('api/delivery-fee/', views.api_delivery_fee, name='api_delivery_fee'),
    
    # B2C Checkout & Order endpoints
    path('checkout/', views.checkout, name='checkout'),
    path('order/<int:order_id>/pay/', views.process_order_payment, name='process_order_payment'),
    path('order/<int:order_id>/', views.order_details, name='order_details'),
    path('orders/', views.order_history, name='order_history'),
    path('orders/track/<int:order_id>/', views.order_track, name='order_track'),
    path('api/orders/<int:order_id>/status/', views.order_status_api, name='order_status_api'),
    path('orders/<int:order_id>/invoice/<str:token>/', views.view_invoice, name='view_invoice'),
    path('payment/mock-success/<int:order_id>/', views.payment_success_mock, name='payment_success_mock'),

    # ── Admin Ops Dashboard (restricted to cheersthepure@gmail.com) ──────────
    path('admin-ops/', views.admin_ops_dashboard, name='admin_ops_dashboard'),
    path('api/orders/<int:order_id>/update-status/', views.admin_update_order_status, name='admin_update_order_status'),
    path('api/quotes/<int:quote_id>/reply/', views.admin_reply_quote, name='admin_reply_quote'),

    # Compatibility Aliases for User Redirect Strings
    path('admin-dashboard/', views.admin_ops_dashboard, name='admin_dashboard'),
    path('b2b-dashboard/', views.dashboard, name='b2b_dashboard'),
    path('product-list/', views.products, name='product_list'),
]
