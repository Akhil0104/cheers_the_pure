# Stripe Payment Integration for Cheers the Pure Water

This guide explains how to set up and use Stripe payment integration in your Django ecommerce application.

## Setup Instructions

### 1. Install Dependencies

Dependencies are already in `requirements.txt`:
```
stripe>=7.0.0
python-dotenv>=1.0.0
```

Run:
```bash
pip install -r requirements.txt
```

### 2. Get Stripe API Keys

1. Go to [Stripe Dashboard](https://dashboard.stripe.com/)
2. Sign up for a free Stripe account
3. Navigate to **Developers > API Keys**
4. Copy your **Publishable Key** (starts with `pk_test_` or `pk_live_`)
5. Copy your **Secret Key** (starts with `sk_test_` or `sk_live_`)

### 3. Configure Environment Variables

Create or update your `.env` file:

```env
STRIPE_PUBLIC_KEY=pk_test_YOUR_PUBLIC_KEY
STRIPE_SECRET_KEY=sk_test_YOUR_SECRET_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET
```

**For production**, replace `test` keys with live keys:
```env
STRIPE_PUBLIC_KEY=pk_live_YOUR_PUBLIC_KEY
STRIPE_SECRET_KEY=sk_live_YOUR_SECRET_KEY
```

### 4. Payment Flow

The payment integration works as follows:

1. **Customer requests a quote** → Quote request is created
2. **Admin provides a quote reply** → Includes pricing
3. **Customer initiates payment** → Redirected to Stripe checkout
4. **Payment processed** → Stripe handles card processing
5. **Payment success/cancel** → Callback to your application

### 5. API Endpoints

#### Create Payment Checkout
```
GET /payment/checkout/<quote_request_id>/
```
Creates a Stripe checkout session and redirects to Stripe checkout page.

**Example:**
```html
<a href="{% url 'create_payment_checkout' pk=quote_request.id %}" class="btn btn-primary">
    Pay Now
</a>
```

#### Payment Success
```
GET /payment-success/?session_id=<session_id>
```
Handles successful payment. Updates:
- `PaymentTransaction` status to "success"
- `QuoteRequest` status to "completed"

#### Payment Cancel
```
GET /payment-cancel/
```
Handles cancelled payment. No data is updated, allows customer to try again.

### 6. Models

The `PaymentTransaction` model is already in your database:

```python
class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    quote_request = models.ForeignKey(QuoteRequest, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='online_card')
    transaction_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
```

### 7. Using Payment in Templates

Add a "Pay Now" button in your quote status view:

```html
{% if quote_request.replies.exists %}
    {% with reply=quote_request.replies.latest %}
        <div class="payment-section">
            <h4>Total Amount: ₹{{ reply.total_price }}</h4>
            <a href="{% url 'create_payment_checkout' pk=quote_request.id %}" 
               class="btn btn-success btn-lg">
                Pay with Stripe
            </a>
        </div>
    {% endwith %}
{% else %}
    <p class="alert alert-info">
        Awaiting quote from admin. Payment will be available after quote is provided.
    </p>
{% endif %}
```

### 8. Testing with Stripe

Use these test card numbers:

| Card Number | Status |
|------------|--------|
| 4242 4242 4242 4242 | Success |
| 4000 0000 0000 0002 | Declined |
| 4000 0025 0000 3155 | 3D Secure required |

**Expiry:** Any future date (e.g., 12/25)
**CVC:** Any 3 digits (e.g., 123)

### 9. Webhook Setup (Optional - for production)

Webhooks allow Stripe to notify your application of payment events.

1. In Stripe Dashboard, go to **Developers > Webhooks**
2. Add endpoint: `https://yourdomain.com/webhook/stripe/`
3. Select events: `charge.succeeded`, `charge.failed`
4. Copy the signing secret to your `.env` as `STRIPE_WEBHOOK_SECRET`

### 10. Security Considerations

- **Never hardcode API keys** - always use environment variables
- **Use HTTPS** - Stripe requires secure connections for production
- **Keep secrets private** - don't commit `.env` to git (already in .gitignore)
- **Validate amounts** - always verify amounts server-side
- **Handle PCI compliance** - Stripe handles card data, never store it

### 11. Troubleshooting

**Error: "No module named 'stripe'"**
```bash
pip install stripe
```

**Error: "STRIPE_SECRET_KEY not found"**
- Check your `.env` file exists
- Ensure you've restarted the Django server after changing `.env`
- Try: `python manage.py shell` → `from django.conf import settings` → `print(settings.STRIPE_SECRET_KEY)`

**Payment creates session but doesn't redirect**
- Check your `STRIPE_PUBLIC_KEY` is correct (test key)
- Check browser console for JavaScript errors
- Verify quote request has a reply with pricing

**Test cards not working**
- Use test keys from Stripe Dashboard (pk_test_, sk_test_)
- Make sure you're not using live keys in development

### 12. Admin Integration

View payment transactions in Django admin:
```
Admin > App > Payment Transactions
```

Sort by:
- Status (Success, Pending, Failed)
- Amount
- Creation date
- Quote request

### 13. Next Steps

1. **Email Notifications**: Send payment confirmation emails
2. **Invoice Generation**: Create PDF invoices after payment
3. **Refunds**: Implement refund functionality in admin
4. **Recurring Payments**: Set up subscriptions for wholesale customers
5. **Analytics**: Track payment metrics and trends

### Support

For Stripe API documentation: https://stripe.com/docs
For Django integration help: https://django.readthedocs.io/
