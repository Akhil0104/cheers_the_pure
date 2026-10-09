"""Email notification utility functions"""
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def send_order_confirmation_email(order):
    """Send order confirmation email to customer"""
    try:
        subject = f'Order Confirmation #{order.order_number} - Cheers the Pure Water'
        
        # Build order items summary
        items_summary = '\n'.join([
            f"  • {item.product_name} x{item.quantity} @ ₹{item.product_price} = ₹{item.get_total_price()}"
            for item in order.items.all()
        ])
        
        message = f"""
Dear {order.shipping_name},

Thank you for your order! We have received your payment and your order is now confirmed.

Order Details:
Order Number: {order.order_number}
Date: {order.created_at.strftime('%B %d, %Y at %H:%M')}

Items Ordered:
{items_summary}

Total: ₹{order.total_amount}

Shipping Address:
{order.shipping_address}
{order.shipping_city}, {order.shipping_state} {order.shipping_postal_code}

Your order will be processed and shipped shortly. You will receive a shipping notification with tracking information.

For any queries, please contact us at cheersthepure@gmail.com

Thank you for choosing Cheers the Pure Water!

Best regards,
Cheers the Pure Water Team
"""
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [order.shipping_email],
            fail_silently=True
        )
    except Exception as e:
        print(f"Error sending order confirmation email: {str(e)}")


def send_order_invoice_email(order, invoice_url):
    """Send a rich HTML invoice confirmation email after successful B2C payment."""
    try:
        # Build a quick items summary for the plain-text fallback
        items_text = '\n'.join([
            f"  • {item.product_name} x{item.quantity} @ ₹{item.product_price} = ₹{item.get_total_price()}"
            for item in order.items.all()
        ])

        plain_text = f"""Dear {order.shipping_name},

Your payment has been confirmed and your invoice is ready.

Order #{order.order_number}

Items:
{items_text}

Total Paid: ₹{order.total_amount}

View your invoice here:
{invoice_url}

Thank you for choosing Cheers the Pure Water!
Best regards,
Cheers the Pure Water Team
"""

        # Rich HTML email body
        items_rows_html = ''.join([
            f"""<tr>
              <td style="padding:0.75rem 1rem;border-bottom:1px solid #e2e8f0;font-size:0.9rem;">
                {item.product_name}
              </td>
              <td style="padding:0.75rem 1rem;border-bottom:1px solid #e2e8f0;font-size:0.9rem;text-align:right;">
                ₹{item.product_price}
              </td>
              <td style="padding:0.75rem 1rem;border-bottom:1px solid #e2e8f0;font-size:0.9rem;text-align:center;">
                {item.quantity}
              </td>
              <td style="padding:0.75rem 1rem;border-bottom:1px solid #e2e8f0;font-size:0.9rem;text-align:right;font-weight:700;">
                ₹{item.get_total_price()}
              </td>
            </tr>"""
            for item in order.items.all()
        ])

        html_message = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Invoice #{order.order_number}</title>
</head>
<body style="font-family:'Inter','Helvetica Neue',Arial,sans-serif;background:#f0f9ff;margin:0;padding:2rem 0;color:#0f172a;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:1.5rem;overflow:hidden;box-shadow:0 16px 60px rgba(15,23,42,0.10);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0c1a40 0%,#0369a1 100%);padding:2rem 2.5rem;">
      <h1 style="color:#ffffff;font-size:1.6rem;font-weight:800;margin:0 0 0.3rem;">Cheers the Pure Water</h1>
      <p style="color:rgba(255,255,255,0.6);font-size:0.85rem;margin:0;">Invoice Confirmation</p>
      <div style="display:inline-block;background:rgba(22,163,74,0.2);border:2px solid rgba(22,163,74,0.5);
                  color:#86efac;font-size:0.8rem;font-weight:800;letter-spacing:0.1em;
                  padding:0.25rem 0.85rem;border-radius:999px;margin-top:0.8rem;">
        ✓ PAYMENT CONFIRMED
      </div>
    </div>

    <!-- Body -->
    <div style="padding:2rem 2.5rem;">

      <p style="font-size:1rem;color:#0f172a;margin:0 0 1.5rem;">
        Dear <strong>{order.shipping_name}</strong>,<br />
        Your order has been paid and confirmed. Here is your invoice summary.
      </p>

      <!-- Order Meta -->
      <table style="width:100%;border-collapse:collapse;margin-bottom:1.5rem;background:#f8fafc;border-radius:0.75rem;overflow:hidden;">
        <tr>
          <td style="padding:0.6rem 1rem;font-size:0.85rem;color:#64748b;font-weight:500;">Order Number</td>
          <td style="padding:0.6rem 1rem;font-size:0.85rem;font-weight:700;text-align:right;">{order.order_number}</td>
        </tr>
        <tr style="background:#ffffff;">
          <td style="padding:0.6rem 1rem;font-size:0.85rem;color:#64748b;font-weight:500;">Order Date</td>
          <td style="padding:0.6rem 1rem;font-size:0.85rem;font-weight:700;text-align:right;">{order.created_at.strftime('%B %d, %Y')}</td>
        </tr>
        <tr>
          <td style="padding:0.6rem 1rem;font-size:0.85rem;color:#64748b;font-weight:500;">Shipping To</td>
          <td style="padding:0.6rem 1rem;font-size:0.85rem;font-weight:700;text-align:right;">{order.shipping_city}, {order.shipping_state}</td>
        </tr>
      </table>

      <!-- Items Table -->
      <table style="width:100%;border-collapse:collapse;margin-bottom:1.5rem;">
        <thead>
          <tr style="background:linear-gradient(135deg,#0c1a40,#1e3a5f);">
            <th style="padding:0.75rem 1rem;color:rgba(255,255,255,0.8);font-size:0.78rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;text-align:left;">Item</th>
            <th style="padding:0.75rem 1rem;color:rgba(255,255,255,0.8);font-size:0.78rem;font-weight:700;text-transform:uppercase;text-align:right;">Unit Price</th>
            <th style="padding:0.75rem 1rem;color:rgba(255,255,255,0.8);font-size:0.78rem;font-weight:700;text-transform:uppercase;text-align:center;">Qty</th>
            <th style="padding:0.75rem 1rem;color:rgba(255,255,255,0.8);font-size:0.78rem;font-weight:700;text-transform:uppercase;text-align:right;">Total</th>
          </tr>
        </thead>
        <tbody>
          {items_rows_html}
        </tbody>
        <tfoot>
          <tr style="background:#f0f9ff;">
            <td colspan="3" style="padding:1rem;font-weight:800;font-size:1rem;text-align:right;color:#0c1a40;">
              Total Paid
            </td>
            <td style="padding:1rem;font-weight:800;font-size:1.15rem;text-align:right;color:#0284c7;">
              ₹{order.total_amount}
            </td>
          </tr>
        </tfoot>
      </table>

      <!-- CTA Button -->
      <div style="text-align:center;margin:2rem 0;">
        <a href="{invoice_url}"
           style="display:inline-block;background:linear-gradient(135deg,#0ea5e9,#4f46e5);
                  color:#ffffff;text-decoration:none;font-weight:700;font-size:1rem;
                  padding:0.9rem 2.5rem;border-radius:999px;
                  box-shadow:0 6px 22px rgba(14,165,233,0.35);">
          🧾 View Full Invoice
        </a>
      </div>

      <p style="font-size:0.85rem;color:#64748b;text-align:center;margin:0;">
        Track your order status from your
        <a href="#" style="color:#0284c7;text-decoration:none;font-weight:600;">account dashboard</a>.
      </p>

    </div>

    <!-- Footer -->
    <div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:1.25rem 2.5rem;text-align:center;">
      <p style="font-size:0.8rem;color:#94a3b8;margin:0;">
        © Cheers the Pure Water · cheersthepure@gmail.com<br />
        This is an automated confirmation. Please do not reply to this email.
      </p>
    </div>

  </div>
</body>
</html>"""

        send_mail(
            subject=f'Invoice #{order.order_number} — Cheers the Pure Water',
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.shipping_email],
            fail_silently=True,
            html_message=html_message,
        )
    except Exception as e:
        print(f"Error sending invoice email: {str(e)}")


def send_quote_payment_email(quote_request):
    """Send payment confirmation email for B2B quote"""
    try:
        subject = f'Payment Received - Quote #{quote_request.id} - Cheers the Pure Water'
        
        # Get the latest reply
        reply = quote_request.replies.first()
        if not reply:
            return
        
        message = f"""
Dear {quote_request.business_name},

Thank you for your payment! We have successfully received your payment for quote #{quote_request.id}.

Quote Details:
Products: {quote_request.product_details}
Quantity: {quote_request.quantity_required}
Quoted Price: ₹{reply.total_price}

Payment Status: Completed
Transaction Date: {timezone.now().strftime('%B %d, %Y at %H:%M')}

Your order is now confirmed and will be processed according to the timeline discussed. Our team will coordinate with you regarding delivery and logistics.

For any further information, please contact us at cheersthepure@gmail.com

Thank you for your business!

Best regards,
Cheers the Pure Water Team
"""
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [quote_request.email],
            fail_silently=True
        )
    except Exception as e:
        print(f"Error sending quote payment email: {str(e)}")


def send_shipping_notification(order):
    """Send shipping notification email"""
    try:
        subject = f'Your Order #{order.order_number} Has Been Shipped!'
        
        items_summary = '\n'.join([
            f"  • {item.product_name} x{item.quantity}"
            for item in order.items.all()
        ])
        
        message = f"""
Dear {order.shipping_name},

Great news! Your order has been shipped and is on its way to you.

Order Number: {order.order_number}
Shipped Date: {order.shipped_at.strftime('%B %d, %Y') if order.shipped_at else 'Recently'}

Items in Your Order:
{items_summary}

Shipping Address:
{order.shipping_address}
{order.shipping_city}, {order.shipping_state} {order.shipping_postal_code}

Your package will arrive within 5-7 business days depending on your location. You can track your order by contacting us with your order number.

For any questions, please reach out to cheersthepure@gmail.com

Thank you for choosing Cheers the Pure Water!

Best regards,
Cheers the Pure Water Team
"""
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [order.shipping_email],
            fail_silently=True
        )
    except Exception as e:
        print(f"Error sending shipping notification: {str(e)}")


def send_delivery_confirmation(order):
    """Send delivery confirmation email"""
    try:
        subject = f'Order #{order.order_number} Delivered Successfully!'
        
        message = f"""
Dear {order.shipping_name},

Your order has been successfully delivered! We hope you're satisfied with your purchase.

Order Number: {order.order_number}
Delivered Date: {order.delivered_at.strftime('%B %d, %Y') if order.delivered_at else 'Recently'}
Total Amount: ₹{order.total_amount}

Thank you for shopping with Cheers the Pure Water. We appreciate your business and look forward to serving you again!

If you have any feedback or concerns about your order, please don't hesitate to contact us at cheersthepure@gmail.com

Best regards,
Cheers the Pure Water Team
"""
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [order.shipping_email],
            fail_silently=True
        )
    except Exception as e:
        print(f"Error sending delivery confirmation: {str(e)}")
