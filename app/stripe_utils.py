import stripe
import os
from django.conf import settings

# Configure Stripe API key
stripe.api_key = settings.STRIPE_SECRET_KEY

def create_checkout_session(quote_request, return_url_base='http://127.0.0.1:8000'):
    """Create a Stripe checkout session for a quote request"""
    try:
        # Calculate the total amount from the quote reply
        if hasattr(quote_request, 'replies') and quote_request.replies.exists():
            quote_reply = quote_request.replies.latest('created_at')
            total_amount = quote_reply.total_price
        else:
            return None
        
        # Convert amount to cents (Stripe uses cents)
        amount_cents = int(total_amount * 100)
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'inr',
                        'product_data': {
                            'name': f"{quote_request.product.name} - {quote_request.product.capacity}" if quote_request.product else "Cheers the Pure Water",
                            'description': f"Order for {quote_request.name} - Qty: {quote_request.quantity}",
                        },
                        'unit_amount': amount_cents,
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            success_url=f"{return_url_base}/payment-success/?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{return_url_base}/payment-cancel/",
            customer_email=quote_request.email,
            metadata={
                'quote_request_id': quote_request.id,
                'customer_name': quote_request.name,
                'customer_email': quote_request.email,
            }
        )
        return session
    except stripe.error.CardError as e:
        print(f"Card Error: {e.user_message}")
        return None
    except stripe.error.InvalidRequestError as e:
        print(f"Invalid Request Error: {e}")
        return None
    except Exception as e:
        print(f"Error creating checkout session: {str(e)}")
        return None


def retrieve_checkout_session(session_id):
    """Retrieve a Stripe checkout session"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session
    except stripe.error.InvalidRequestError as e:
        print(f"Session not found: {e}")
        return None
    except Exception as e:
        print(f"Error retrieving session: {str(e)}")
        return None


def retrieve_payment_intent(payment_intent_id):
    """Retrieve a Stripe payment intent"""
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return intent
    except Exception as e:
        print(f"Error retrieving payment intent: {str(e)}")
        return None


def create_checkout_session_for_order(order, return_url_base='http://127.0.0.1:8000'):
    """Create a Stripe checkout session for an Order instance"""
    try:
        amount_cents = int(order.total_amount * 100)
        line_item = {
            'price_data': {
                'currency': 'inr',
                'product_data': {
                    'name': f"Order {order.order_number}",
                    'description': f"Order for {order.shipping_name} - {order.get_customer_email()}",
                },
                'unit_amount': amount_cents,
            },
            'quantity': 1,
        }
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[line_item],
            mode='payment',
            success_url=f"{return_url_base}/payment-success/?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{return_url_base}/payment-cancel/",
            customer_email=order.get_customer_email(),
            metadata={
                'order_id': order.id,
                'order_number': order.order_number,
            }
        )
        return session
    except Exception as e:
        print(f"Error creating checkout session for order: {str(e)}")
        return None
