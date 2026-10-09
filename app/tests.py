from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from .models import (
    Category,
    Product,
    QuoteRequest,
    EmailVerificationToken,
    QuoteReply,
    Notification,
    UserProfile,
    PaymentTransaction,
)


class B2BQuoteWorkflowTestCase(TestCase):
    def setUp(self):
        # Create categories and products
        self.category = Category.objects.create(name="Eco-Hydration", description="Eco friendly bottles")
        self.product = Product.objects.create(
            category=self.category,
            name="GreenBottle 500ML",
            capacity="500 ml",
            price=4.99,
            is_featured=True,
            description="Recyclable bottle"
        )
        
        # Create users
        self.admin_user = User.objects.create_superuser(
            username="admin_user",
            email="admin@cheers.com",
            password="adminpassword"
        )
        UserProfile.objects.create(user=self.admin_user, role='staff')
        
        self.b2b_user = User.objects.create_user(
            username="b2b_user",
            email="buyer@drinkcorp.com",
            password="clientpassword"
        )
        UserProfile.objects.create(
            user=self.b2b_user,
            role='distributor',
            account_type='b2b',
            company_name='Drinkcorp',
        )

        self.b2c_user = User.objects.create_user(
            username="b2c_user",
            email="shopper@gmail.com",
            password="clientpassword"
        )
        UserProfile.objects.create(
            user=self.b2c_user,
            role='customer',
            account_type='b2c',
        )
        
        self.client = Client()

    def test_anonymous_quote_request_blocked(self):
        """Test that anonymous users are blocked and shown the registration prompt."""
        url = reverse('order_request_product', kwargs={'pk': self.product.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Required")

    def test_quote_request_creation_and_token(self):
        """Test that submitting a quote request creates the request and a verification token for logged-in B2B users."""
        self.client.login(username="b2b_user", password="clientpassword")
        url = reverse('order_request_product', kwargs={'pk': self.product.id})
        post_data = {
            'name': 'John Doe',
            'email': 'john@drinkcorp.com',
            'company': 'DrinkCorp',
            'size': '500 ml',
            'quantity': 150,
            'details': 'Please quote green caps.'
        }

        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quote Request Submitted!")

        quote = QuoteRequest.objects.get(email='john@drinkcorp.com')
        self.assertEqual(quote.name, 'John Doe')
        self.assertEqual(quote.quantity, 150)
        self.assertFalse(quote.email_verified)

        token_obj = EmailVerificationToken.objects.get(quote_request=quote)
        self.assertIsNotNone(token_obj.token)
        self.assertFalse(token_obj.verified)

    def test_b2c_user_blocked_from_quote_request(self):
        """B2C retail accounts cannot access the B2B quote workflow."""
        self.client.login(username="b2c_user", password="clientpassword")
        url = reverse('order_request_product', kwargs={'pk': self.product.id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('access_denied'))

    def test_email_verification_flow(self):
        """Test that hitting the verification link activates the quote request."""
        quote = QuoteRequest.objects.create(
            product=self.product,
            name='Jane Doe',
            email='jane@example.com',
            company='JaneCorp',
            size='500 ml',
            quantity=100,
            email_verified=False
        )
        token_obj = EmailVerificationToken.create_token(quote)
        
        # Verify success view
        verify_url = reverse('verify_email', kwargs={'token': token_obj.token})
        response = self.client.get(verify_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email Verified Successfully!")
        
        # Verify status updates in database
        quote.refresh_from_db()
        token_obj.refresh_from_db()
        self.assertTrue(quote.email_verified)
        self.assertTrue(token_obj.verified)
        
        # Verify notifications are created
        notifications = Notification.objects.filter(quote_request=quote)
        self.assertTrue(notifications.filter(notification_type='email_verified').exists())
        self.assertTrue(notifications.filter(notification_type='general').exists())

    def test_quote_tracking_portal(self):
        """Test tracking portal displays details only when verified."""
        quote = QuoteRequest.objects.create(
            product=self.product,
            name='Bob Builder',
            email='bob@example.com',
            size='500 ml',
            quantity=200,
            email_verified=False
        )
        token_obj = EmailVerificationToken.create_token(quote)
        
        # Attempt to track before verification
        track_url = reverse('view_quote_status', kwargs={'token': token_obj.token})
        response = self.client.get(track_url)
        self.assertContains(response, "Please verify your email address")
        
        # Verify and check portal
        token_obj.verified = True
        token_obj.save()
        quote.email_verified = True
        quote.save()
        
        response = self.client.get(track_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quote Request Tracker")
        self.assertContains(response, "Bob Builder")

    def test_admin_access_controls(self):
        """Test that only staff/admin can manage quotes and catalog."""
        dashboard_url = reverse('dashboard')
        
        # Anonymous user redirected to login
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 302)
        
        # Non-staff B2B user logs in
        self.client.login(username='b2b_user', password='clientpassword')
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "B2B Corporate Dashboard")
        self.client.logout()
        
        # Admin staff logs in
        self.client.login(username='admin_user', password='adminpassword')
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer Messages") # Should show admin tabs

    def test_admin_reply_and_proposal(self):
        """Test that admin can submit a proposal, update quote status, and notify client."""
        quote = QuoteRequest.objects.create(
            product=self.product,
            name='Alice Smith',
            email='alice@example.com',
            size='500 ml',
            quantity=500,
            email_verified=True,
            status='pending'
        )
        EmailVerificationToken.create_token(quote)
        
        self.client.login(username='admin_user', password='adminpassword')
        
        reply_url = reverse('admin_quote_reply', kwargs={'pk': quote.id})
        post_data = {
            'message': 'We can offer discount!',
            'price_per_unit': 3.50,
            'estimated_delivery': '10 business days'
        }
        
        response = self.client.post(reply_url, post_data)
        self.assertEqual(response.status_code, 302) # Redirects to detail page
        
        # Verify reply was saved and status changed
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'quoted')
        self.assertEqual(quote.replies.count(), 1)
        
        reply = quote.replies.first()
        self.assertEqual(reply.price_per_unit, 3.50)
        self.assertEqual(reply.estimated_delivery, '10 business days')
        
        # Verify client notifications were created
        self.assertTrue(Notification.objects.filter(email='alice@example.com', notification_type='quote_reply').exists())

    def test_user_registration_with_role(self):
        """Test registration using RegistrationForm creates User and UserProfile with role."""
        url = reverse('register')
        post_data = {
            'email': 'new@distributor.com',
            'password1': 'distpass123',
            'password2': 'distpass123',
            'mobile': '+15551234'
        }
        
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302) # Success redirect to dashboard
        
        # Verify user and profile
        user = User.objects.get(email='new@distributor.com')
        self.assertEqual(user.email, 'new@distributor.com')
        self.assertEqual(user.profile.role, 'distributor')
        self.assertEqual(user.profile.account_type, 'b2b')
        self.assertEqual(user.profile.company_name, 'Distributor')

    def test_quote_payment_processing(self):
        """Test that submitting payment completes the quote status and creates transaction logs."""
        quote = QuoteRequest.objects.create(
            product=self.product,
            name='Checkout Client',
            email='checkout@example.com',
            size='500 ml',
            quantity=100,
            email_verified=True,
            status='quoted'
        )
        QuoteReply.objects.create(
            quote_request=quote,
            admin_name='admin_user',
            message='Initial proposal',
            price_per_unit=2.50
        )
        token_obj = EmailVerificationToken.create_token(quote)
        
        url = reverse('process_quote_payment', kwargs={'token': token_obj.token})
        post_data = {
            'payment_method': 'online_card'
        }
        
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302) # Redirects to tracker portal
        
        # Verify Quote Status
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'completed')
        
        # Verify transaction
        transaction = PaymentTransaction.objects.get(quote_request=quote)
        self.assertEqual(transaction.amount, 250.00)
        self.assertEqual(transaction.status, 'success')
        self.assertEqual(transaction.payment_method, 'online_card')

    def test_admin_user_role_modification(self):
        """Test that admin can modify user roles in real-time from the dashboard."""
        self.client.login(username='admin_user', password='adminpassword')
        
        url = reverse('admin_update_user_role', kwargs={'user_id': self.b2c_user.id})
        post_data = {
            'role': 'distributor'
        }

        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)

        self.b2c_user.profile.refresh_from_db()
        self.assertEqual(self.b2c_user.profile.role, 'distributor')

    def test_master_admin_bypass_login(self):
        """Test that the master admin credentials bypass standard authentication and login successfully."""
        url = reverse('login')
        post_data = {
            'username': 'cheersthepure@gmail.com',
            'password': '9705821826'
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        # Should redirect to admin dashboard
        self.assertRedirects(response, reverse('admin_dashboard'))
        
        # Verify master admin user was created/updated as superuser/staff
        user = User.objects.get(email='cheersthepure@gmail.com')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertEqual(self.client.session.get('is_admin_ops'), True)

    def test_customer_login_email_and_mobile(self):
        """Test standard customer login using email or phone number works correctly."""
        # Create a customer with a profile having a phone number
        customer = User.objects.create_user(
            username="test_customer",
            email="cust@example.com",
            password="custpassword"
        )
        UserProfile.objects.create(
            user=customer,
            role='customer',
            account_type='b2c',
            phone='9876543210'
        )
        
        # Test login via email
        url = reverse('login')
        response = self.client.post(url, {
            'username': 'cust@example.com',
            'password': 'custpassword'
        })
        self.assertEqual(response.status_code, 302)
        # B2C customers redirect to product list
        self.assertRedirects(response, reverse('product_list'))
        self.client.logout()

        # Test login via phone
        response = self.client.post(url, {
            'username': '9876543210',
            'password': 'custpassword'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('product_list'))
        self.client.logout()

        # Test incorrect password
        response = self.client.post(url, {
            'username': 'cust@example.com',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email / mobile number or password")


class B2BFullWorkflowEndToEndTestCase(TestCase):
    """
    Validates the complete 8-step B2B Distributor Workflow:
    1. Sign in
    2. View products
    3. Request a quote
    4. Specify quantity
    5. Specify preferred delivery timing
    6. View previous quotes/orders
    7. View payment status
    8. Access DispatchAI with stable buyer_id
    """
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Commercial Hydration", description="Bottles for wholesale")
        self.product = Product.objects.create(
            category=self.category,
            name="Cheers Pure 1Ltr",
            capacity="1000 ml",
            price=120.00,
            is_featured=True,
        )
        self.b2b_user = User.objects.create_user(
            username="unique_b2b_distributor",
            email="procurement_b2b_flow@apexbeverages.com",
            password="ApexSecurePassword123!",
            first_name="Rajesh",
            last_name="Kumar",
        )
        self.profile = UserProfile.objects.create(
            user=self.b2b_user,
            role="distributor",
            account_type="b2b",
            company_name="Apex Beverages Ltd",
            phone="+91 9876543210",
            address="Plot 10, Industrial Estate",
            city="Hyderabad",
            state="Telangana",
            postal_code="500032",
            gstin="36AAACA1234A1Z5",
        )

    def test_complete_b2b_workflow(self):
        # 1. Sign In
        buyer_id = self.profile.get_buyer_id()
        self.assertTrue(buyer_id.startswith('DIST-'))
        self.client.force_login(self.b2b_user)

        # 2. View Products
        products_res = self.client.get(reverse('products'))
        self.assertEqual(products_res.status_code, 200)

        # View Product Detail (ensures B2B quotation CTA is displayed)
        detail_res = self.client.get(reverse('product_detail', kwargs={'pk': self.product.pk}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "Request Bulk Quote")

        # 3. Request a Quote + 4. Specify Quantity + 5. Specify Delivery Timing
        quote_post_data = {
            'name': 'Rajesh Kumar',
            'email': 'procurement_b2b_flow@apexbeverages.com',
            'company': 'Apex Beverages Ltd',
            'size': '1000 ml',
            'quantity': 500,
            'preferred_delivery_timing': 'Weekly Recurring Distribution',
            'delivery_address': 'Warehouse #3, Gachibowli, Hyderabad',
            'details': 'Need pallets shrink-wrapped with custom wholesale label.',
        }
        quote_res = self.client.post(
            reverse('order_request_product', kwargs={'pk': self.product.pk}),
            quote_post_data,
        )
        self.assertEqual(quote_res.status_code, 200)
        self.assertContains(quote_res, "Quote Request Submitted!")

        # Verify quote in database
        quote = QuoteRequest.objects.get(email='procurement_b2b_flow@apexbeverages.com')
        self.assertEqual(quote.quantity, 500)
        self.assertEqual(quote.preferred_delivery_timing, 'Weekly Recurring Distribution')
        self.assertEqual(quote.delivery_address, 'Warehouse #3, Gachibowli, Hyderabad')
        self.assertFalse(quote.email_verified)
        self.assertEqual(quote.status, 'pending')

        # Verify email token
        token_obj = EmailVerificationToken.objects.get(quote_request=quote)
        self.client.get(reverse('verify_email', kwargs={'token': token_obj.token}))
        quote.refresh_from_db()
        self.assertTrue(quote.email_verified)

        # 6. View Quotes on B2B Dashboard
        dash_res = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "B2B Distributor Account")
        self.assertContains(dash_res, buyer_id)
        self.assertContains(dash_res, "500 units")
        self.assertContains(dash_res, "Weekly Recurring Distribution")

        # 7. Admin Quotes Wholesale Price & Payment Status Tracking
        reply = QuoteReply.objects.create(
            quote_request=quote,
            admin_name="Operations Desk",
            message="Wholesale approved at ₹85/tray for 500 units.",
            price_per_unit=85.00,
            estimated_delivery="2 business days",
        )
        quote.status = 'quoted'
        quote.save(update_fields=['status'])

        dash_after_quote = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_after_quote.status_code, 200)
        self.assertContains(dash_after_quote, "₹85.00/unit")
        self.assertContains(dash_after_quote, "Pay Online")

        # 8. Access DispatchAI with Stable Buyer Identity
        session_res = self.client.post(reverse('dispatch:sessions'))
        self.assertEqual(session_res.status_code, 201)
        session_id = session_res.json()['session_id']

        chat_res = self.client.post(
            reverse('dispatch:chat'),
            data={'session_id': session_id, 'message': 'What is the status of my 500 units 1Ltr quote?'},
            content_type='application/json',
        )
        self.assertEqual(chat_res.status_code, 200)
        chat_data = chat_res.json()
        self.assertTrue(chat_data['ok'])
        self.assertIn('content', chat_data['message'])
        self.assertIn('content', chat_data['message'])

