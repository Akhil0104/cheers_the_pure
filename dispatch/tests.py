"""
Unit and Integration Tests for DispatchAI.
"""

from decimal import Decimal
import time
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from app.models import (
    Category,
    Product,
    Inventory,
    UserProfile,
    Order,
    OrderItem,
    OrderPayment,
    QuoteRequest,
    QuoteReply,
    PaymentTransaction,
)
from dispatch.models import (
    ConversationSession,
    ConversationMessage,
    DispatchDecision,
    BusinessRule,
    AgentActionLog,
)
from dispatch.config import (
    mask_secret,
    get_groq_api_key,
    is_groq_configured,
    get_groq_config,
    get_hindsight_url,
    get_hindsight_api_key,
    is_hindsight_configured,
    get_hindsight_config,
    validate_dispatch_environment,
)
from unittest.mock import MagicMock, patch
from dispatch.services import (
    get_product_information,
    get_current_price,
    get_available_inventory,
    get_customer_orders,
    get_quote_information,
    get_payment_status,
    recall_customer_memory,
    retain_customer_memory,
    search_customer_memories,
    forget_customer_memory,
    is_hindsight_service_available,
    normalize_buyer_id,
    process_dispatch_chat,
    validate_buyer_identity,
)
from dispatch.tools import (
    search_product,
    get_current_price as tool_get_current_price,
    get_customer_order_history,
    get_quote_status,
    get_payment_status as tool_get_payment_status,
    create_quote_request,
    prepare_order_request,
    check_delivery_preference,
    summarize_customer_requirements,
)
from dispatch.memory_extractor import (
    is_trivial_message,
    extract_contextual_memories,
    extract_memories_fallback,
)
from dispatch.context_builder import build as build_context
from dispatch.prompts.system import build_system_prompt
from dispatch.rules_engine import validate_response
from dispatch.agent import process_message


class DispatchConfigTestCase(TestCase):
    def test_mask_secret(self):
        self.assertEqual(mask_secret(None), '[NOT SET]')
        self.assertEqual(mask_secret(''), '[NOT SET]')
        self.assertEqual(mask_secret('short'), '***')
        masked = mask_secret('gsk_1234567890abcdef')
        self.assertTrue(masked.startswith('gsk_'))
        self.assertTrue(masked.endswith('def'))
        self.assertIn('...', masked)
        self.assertNotIn('1234567890', masked)

    def test_safe_config_dicts_no_secrets(self):
        groq_cfg = get_groq_config()
        self.assertIn('configured', groq_cfg)
        self.assertIn('api_key_masked', groq_cfg)
        self.assertNotIn('gsk_', str(groq_cfg.get('api_key_masked'))) if not is_groq_configured() else None

        hindsight_cfg = get_hindsight_config()
        self.assertIn('configured', hindsight_cfg)
        self.assertIn('api_url', hindsight_cfg)
        self.assertIn('api_key_masked', hindsight_cfg)

    def test_startup_validation(self):
        report = validate_dispatch_environment()
        self.assertIn('groq', report)
        self.assertIn('hindsight', report)
        self.assertIn('ready', report)


class DispatchModelsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='b2b_buyer', email='buyer@wholesale.com', password='pass')
        UserProfile.objects.create(user=self.user, account_type='b2b', role='distributor', company_name='Wholesale Co')

    def test_create_session_and_messages(self):
        session = ConversationSession.objects.create(user=self.user, title='Bulk Order 500ml')
        self.assertEqual(session.messages.count(), 0)

        msg1 = ConversationMessage.objects.create(session=session, role='user', content='Hello DispatchAI')
        msg2 = ConversationMessage.objects.create(session=session, role='assistant', content='Hello, how can I assist?')

        self.assertEqual(session.messages.count(), 2)
        recent = session.get_recent_messages()
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0].content, 'Hello DispatchAI')
        self.assertEqual(recent[1].content, 'Hello, how can I assist?')

    def test_business_rule_creation(self):
        rule = BusinessRule.objects.create(
            name='Minimum Wholesale Quantity',
            rule_type='moq',
            description='Orders must be at least 100 units',
            parameters={'min_qty': 100},
            priority=10,
        )
        self.assertTrue(rule.is_active)
        self.assertIn('100', rule.description)


class DispatchRulesEngineTestCase(TestCase):
    def setUp(self):
        BusinessRule.objects.create(
            name='MOQ 100',
            rule_type='moq',
            description='Minimum order quantity is 100 units',
            parameters={'min_qty': 100},
            is_active=True,
        )
        BusinessRule.objects.create(
            name='Price Floor 3.00',
            rule_type='price_floor',
            description='Floor price is 3.00',
            parameters={'min_price': 3.00},
            is_active=True,
        )

    def test_valid_response_passes(self):
        text = "I can offer 500 units of 500ml at ₹4.50/unit."
        final_text, applied = validate_response(text, {})
        self.assertEqual(final_text, text)
        self.assertEqual(applied, [])

    def test_moq_violation_corrected(self):
        text = "I can quote you for 20 units at ₹5.00 each."
        final_text, applied = validate_response(text, {})
        self.assertIn('minimum order quantity', final_text.lower())
        self.assertIn('MOQ 100', applied)

    def test_price_floor_violation_corrected(self):
        text = "I can offer 500 units at ₹2.50 per unit."
        final_text, applied = validate_response(text, {})
        self.assertIn('minimum wholesale price', final_text.lower())
        self.assertIn('Price Floor 3.00', applied)


class DispatchAPIAccessControlTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.b2b_user = User.objects.create_user(username='b2b_user', email='b2b@company.com', password='password123')
        UserProfile.objects.create(user=self.b2b_user, account_type='b2b', role='distributor', company_name='Acme Corp')

        self.b2c_user = User.objects.create_user(username='b2c_user', email='b2c@gmail.com', password='password123')
        UserProfile.objects.create(user=self.b2c_user, account_type='b2c', role='customer')

    def test_unauthenticated_access_denied(self):
        response = self.client.get(reverse('dispatch:sessions'))
        # Should redirect to login or return 302/401/403
        self.assertIn(response.status_code, [302, 401, 403])

    def test_b2c_user_blocked_from_dispatch(self):
        self.client.force_login(self.b2c_user)
        response = self.client.get(reverse('dispatch:sessions'))
        self.assertEqual(response.status_code, 403)

    def test_b2b_user_can_access_sessions(self):
        self.client.force_login(self.b2b_user)
        response = self.client.get(reverse('dispatch:sessions'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['sessions'], [])

    def test_b2b_user_can_send_chat(self):
        self.client.force_login(self.b2b_user)
        response = self.client.post(
            reverse('dispatch:chat'),
            data={'message': 'What products do you offer?'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('session_id', data)
        self.assertIn('content', data['message'])


class ProductAndPricingServicesTestCase(TestCase):
    """
    Validates that DispatchAI's service layer deterministically retrieves
    real product catalog, inventory, order, quote, and payment data from SQL
    and strictly forbids inventing prices or unlisted products.
    """

    def setUp(self):
        self.category = Category.objects.create(name='Packaged Water', description='Premium mineral water')
        self.p500 = Product.objects.create(
            category=self.category,
            name='Pure Mineral Water 500ml',
            capacity='500 ml',
            price=Decimal('4.50'),
            is_featured=True,
            description='Standard 500ml water bottle',
        )
        self.inv500 = Inventory.objects.create(
            product=self.p500,
            quantity_in_stock=2500,
            reorder_level=500,
        )

        self.p1000 = Product.objects.create(
            category=self.category,
            name='Pure Mineral Water 1L',
            capacity='1000 ml',
            price=Decimal('9.00'),
            is_featured=True,
            description='Standard 1 Litre bottle',
        )
        self.inv1000 = Inventory.objects.create(
            product=self.p1000,
            quantity_in_stock=1200,
            reorder_level=300,
        )

        self.user = User.objects.create_user(
            username='distributor_hyd',
            email='hyd@distributor.in',
            password='securepassword',
            first_name='Ramesh',
            last_name='Kumar',
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            account_type='b2b',
            role='distributor',
            company_name='Deccan Beverages Pvt Ltd',
            phone='+91 98765 43210',
            address='Plot 42, IDA Nacharam',
            city='Hyderabad',
            state='Telangana',
            postal_code='500076',
            gstin='36AAAAA0000A1Z5',
        )

    def test_get_product_information_all(self):
        prods = get_product_information()
        self.assertIsInstance(prods, list)
        self.assertEqual(len(prods), 2)
        names = [p['name'] for p in prods]
        self.assertIn('Pure Mineral Water 500ml', names)
        self.assertIn('Pure Mineral Water 1L', names)

        p500_info = next(p for p in prods if p['id'] == self.p500.id)
        self.assertEqual(p500_info['price'], Decimal('4.50'))
        self.assertEqual(p500_info['price_display'], '₹4.50')
        self.assertEqual(p500_info['stock_quantity'], 2500)
        self.assertTrue(p500_info['is_in_stock'])
        self.assertEqual(p500_info['units_per_tray'], 18)

    def test_get_product_information_by_id_and_name(self):
        by_id = get_product_information(self.p500.id)
        self.assertIsNotNone(by_id)
        self.assertEqual(by_id['name'], 'Pure Mineral Water 500ml')
        self.assertEqual(by_id['price'], Decimal('4.50'))

        by_str_id = get_product_information(str(self.p1000.id))
        self.assertIsNotNone(by_str_id)
        self.assertEqual(by_str_id['name'], 'Pure Mineral Water 1L')

        by_capacity = get_product_information('500 ml')
        self.assertIsNotNone(by_capacity)
        self.assertEqual(by_capacity['id'], self.p500.id)

    def test_get_product_information_non_existent_returns_none(self):
        non_existent_id = get_product_information(999999)
        self.assertIsNone(non_existent_id)

        non_existent_name = get_product_information('20 Gallon Giant Drum')
        self.assertIsNone(non_existent_name)

    def test_get_current_price_deterministic(self):
        price500 = get_current_price(self.p500.id)
        self.assertEqual(price500, Decimal('4.50'))

        price1000 = get_current_price('Pure Mineral Water 1L')
        self.assertEqual(price1000, Decimal('9.00'))

    def test_get_current_price_cannot_invent_unlisted_product_price(self):
        """
        Critical safety test: The price function MUST return None when
        querying unlisted products, guaranteeing the agent cannot fetch or
        invent arbitrary pricing.
        """
        unlisted_products = [
            '20L Water Can',
            '5 Gallon Dispenser Jug',
            'Alkaline Sparkling Infusion',
            'Flavored Lemon Mint 750ml',
            99999,
        ]
        for item in unlisted_products:
            price = get_current_price(item)
            self.assertIsNone(
                price,
                f"Expected None for unlisted product '{item}', but received {price}"
            )

    def test_get_available_inventory(self):
        stock500 = get_available_inventory(self.p500.id)
        self.assertEqual(stock500, 2500)

        stock_missing = get_available_inventory('Unlisted Product')
        self.assertIsNone(stock_missing)

    def test_get_customer_orders_and_payment_status(self):
        order = Order.objects.create(
            user=self.user,
            order_number='ORD-2026-TEST-001',
            shipping_name='Ramesh Kumar',
            shipping_email=self.user.email,
            shipping_phone='+91 98765 43210',
            shipping_address='Plot 42, IDA Nacharam',
            shipping_city='Hyderabad',
            shipping_state='Telangana',
            shipping_postal_code='500076',
            total_amount=Decimal('4500.00'),
            advance_paid=Decimal('1350.00'),
            balance_due=Decimal('3150.00'),
            status='processing',
            payment_method='cod',
        )
        OrderItem.objects.create(
            order=order,
            product=self.p500,
            product_name=self.p500.name,
            product_price=self.p500.price,
            quantity=1000,
        )
        OrderPayment.objects.create(
            order=order,
            amount=Decimal('1350.00'),
            payment_method='upi',
            transaction_id='TXN-TEST-123456',
            status='success',
        )

        orders = get_customer_orders(self.user)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['order_number'], 'ORD-2026-TEST-001')
        self.assertEqual(orders[0]['total_amount'], Decimal('4500.00'))
        self.assertEqual(orders[0]['advance_paid'], Decimal('1350.00'))
        self.assertEqual(orders[0]['balance_due'], Decimal('3150.00'))
        self.assertEqual(orders[0]['payment_status'], 'success')
        self.assertEqual(len(orders[0]['items']), 1)
        self.assertEqual(orders[0]['items'][0]['product_name'], self.p500.name)

        # Payment status service test
        payment_info = get_payment_status(self.user, order_number='ORD-2026-TEST-001')
        self.assertTrue(payment_info['found'])
        self.assertEqual(payment_info['order_status'], 'processing')
        self.assertEqual(payment_info['payment_status'], 'success')
        self.assertEqual(payment_info['advance_paid'], Decimal('1350.00'))
        self.assertEqual(payment_info['balance_due'], Decimal('3150.00'))

    def test_get_quote_information_and_replies(self):
        quote = QuoteRequest.objects.create(
            user=self.user,
            product=self.p500,
            size='500 ml',
            quantity=5000,
            name='Ramesh Kumar',
            email=self.user.email,
            company='Deccan Beverages',
            preferred_delivery_timing='Within 3 business days',
            delivery_address='Plot 42, IDA Nacharam, Hyderabad',
            status='quoted',
        )
        QuoteReply.objects.create(
            quote_request=quote,
            admin_name='Sales Team Hyderabad',
            message='Approved volume price of ₹4.20/unit for 5000 units.',
            price_per_unit=Decimal('4.20'),
            estimated_delivery='2 business days',
        )
        PaymentTransaction.objects.create(
            quote_request=quote,
            amount=Decimal('21000.00'),
            payment_method='bank_transfer',
            transaction_id='TXN-QUOTE-789',
            status='success',
        )

        quotes = get_quote_information(self.user)
        self.assertIsInstance(quotes, list)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]['id'], quote.id)
        self.assertEqual(quotes[0]['quantity'], 5000)
        self.assertEqual(quotes[0]['quoted_unit_price'], Decimal('4.20'))
        self.assertEqual(quotes[0]['quoted_total_price'], Decimal('21000.00'))
        self.assertTrue(quotes[0]['is_paid'])

        # Payment status service for quote
        pay_quote = get_payment_status(self.user, quote_id=quote.id)
        self.assertTrue(pay_quote['found'])
        self.assertEqual(pay_quote['entity_type'], 'quote')
        self.assertTrue(pay_quote['is_paid'])
        self.assertEqual(pay_quote['quoted_total_price'], Decimal('21000.00'))

    def test_context_builder_and_system_prompt_grounding(self):
        """
        Verify that context_builder only provides real catalog items
        and system prompt contains anti-hallucination constraints.
        """
        context = build_context(self.user, user_message="What is the price of 20L jars?")
        catalog_names = [p['name'] for p in context['products']]
        self.assertIn('Pure Mineral Water 500ml', catalog_names)
        self.assertIn('Pure Mineral Water 1L', catalog_names)
        self.assertNotIn('20L Water Can', catalog_names)

        system_prompt = build_system_prompt(context, business_rules=[])
        self.assertIn('Strict Catalog Grounding', system_prompt)
        self.assertIn('Zero-Hallucination on Unlisted Products', system_prompt)
        self.assertIn('Pure Mineral Water 500ml (500 ml) — ₹4.50/unit', system_prompt)


class HindsightServiceTestCase(TestCase):
    """
    Unit tests for Hindsight Persistent Memory service integration.
    Validates buyer isolation, timeout handling, auth failure handling,
    empty query safety, and fail-safe resilience.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='hindsight_buyer',
            email='buyer@hindsight.in',
            password='secretpassword',
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            account_type='b2b',
            role='distributor',
            buyer_id='DIST-99001',
            company_name='Telangana Water Hub',
        )

    def test_normalize_buyer_id(self):
        # User instance with profile
        self.assertEqual(normalize_buyer_id(self.user), 'DIST-99001')

        # User instance without profile
        user_no_prof = User.objects.create_user(username='noprofile', email='noprof@mail.com', password='pwd')
        self.assertEqual(normalize_buyer_id(user_no_prof), f'DIST-{user_no_prof.id:05d}')

        # Direct UserProfile
        self.assertEqual(normalize_buyer_id(self.profile), 'DIST-99001')

        # String and integer
        self.assertEqual(normalize_buyer_id('DIST-00123'), 'DIST-00123')
        self.assertEqual(normalize_buyer_id(42), 'DIST-00042')
        self.assertEqual(normalize_buyer_id(None), '')

    def test_recall_customer_memory_unconfigured_fails_gracefully(self):
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=False):
            memories = recall_customer_memory(buyer_id=self.user, query='delivery preferences')
            self.assertEqual(memories, [])

    def test_recall_customer_memory_empty_inputs(self):
        self.assertEqual(recall_customer_memory(buyer_id='', query='test'), [])
        self.assertEqual(recall_customer_memory(buyer_id=self.user, query=''), [])

    def test_recall_customer_memory_handles_timeout_gracefully(self):
        import httpx
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=True), \
             patch('dispatch.services.hindsight_service.get_hindsight_api_key', return_value='hsk_test_key_12345'), \
             patch('dispatch.services.hindsight_service.get_hindsight_url', return_value='https://api.hindsight.vectorize.io'), \
             patch('httpx.post', side_effect=httpx.TimeoutException('Request timed out')):
            # Mock SDK to raise TimeoutException as well so fallback is tested
            with patch('hindsight_client.Hindsight', side_effect=Exception('Timeout connecting to host')):
                memories = recall_customer_memory(buyer_id=self.user, query='warehouse hours')
                self.assertEqual(memories, [])

    def test_recall_customer_memory_handles_auth_failure_gracefully(self):
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=True), \
             patch('dispatch.services.hindsight_service.get_hindsight_api_key', return_value='hsk_invalid_key'), \
             patch('dispatch.services.hindsight_service.get_hindsight_url', return_value='https://api.hindsight.vectorize.io'):
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            with patch('httpx.post', return_value=mock_resp), \
                 patch('hindsight_client.Hindsight', side_effect=Exception('401 Unauthorized')):
                memories = recall_customer_memory(buyer_id=self.user, query='preferred times')
                self.assertEqual(memories, [])

    def test_recall_customer_memory_handles_malformed_json(self):
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=True), \
             patch('dispatch.services.hindsight_service.get_hindsight_api_key', return_value='hsk_valid_key'), \
             patch('dispatch.services.hindsight_service.get_hindsight_url', return_value='https://api.hindsight.vectorize.io'):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.side_effect = ValueError('Invalid JSON syntax')
            with patch('httpx.post', return_value=mock_resp), \
                 patch('hindsight_client.Hindsight', side_effect=Exception('SDK not available')):
                memories = recall_customer_memory(buyer_id=self.user, query='warehouse rules')
                self.assertEqual(memories, [])

    def test_recall_customer_memory_successful_http_parse(self):
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=True), \
             patch('dispatch.services.hindsight_service.get_hindsight_api_key', return_value='hsk_valid_key'), \
             patch('dispatch.services.hindsight_service.get_hindsight_url', return_value='https://api.hindsight.vectorize.io'):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                'memories': [
                    {
                        'id': 'mem_101',
                        'content': 'Warehouse cannot receive deliveries before 4 PM',
                        'category': 'warehouse_restrictions',
                        'score': 0.95,
                    }
                ]
            }
            with patch('httpx.post', return_value=mock_resp), \
                 patch('hindsight_client.Hindsight', side_effect=Exception('SDK bypass for test')):
                memories = recall_customer_memory(buyer_id=self.user, query='when can we deliver?')
                self.assertEqual(len(memories), 1)
                self.assertEqual(memories[0]['category'], 'warehouse_restrictions')
                self.assertIn('before 4 PM', memories[0]['content'])

    def test_retain_customer_memory_unconfigured_and_empty(self):
        self.assertEqual(retain_customer_memory(buyer_id=self.user, content=''), [])
        self.assertEqual(retain_customer_memory(buyer_id='', content='Some preference'), [])
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=False):
            res = retain_customer_memory(buyer_id=self.user, content='Requires tailgate unloading')
            self.assertEqual(res, [])

    def test_is_hindsight_service_available_no_crash(self):
        status = is_hindsight_service_available()
        self.assertIsInstance(status, bool)

    def test_forget_customer_memory_handles_unconfigured(self):
        with patch('dispatch.services.hindsight_service.is_hindsight_configured', return_value=False):
            res = forget_customer_memory('mem_123')
            self.assertFalse(res)


class MemoryExtractorTestCase(TestCase):
    """
    Validates B2B memory extraction rules:
    - Discards trivial acknowledgments ('Okay thanks', 'Hi', 'Sure', 'Bye')
    - Extracts meaningful operational constraints (warehouse timings, recurring orders)
    - Rejects treating unverified claims as official contracts
    """

    def test_is_trivial_message(self):
        trivial_messages = [
            'ok', 'okay', 'OK', 'thanks', 'thank you', 'thx', 'Okay thanks',
            'sounds good', 'great', 'cool', 'sure', 'yes', 'no', 'bye',
            'good morning', 'much appreciated', 'alright',
        ]
        for msg in trivial_messages:
            self.assertTrue(
                is_trivial_message(msg),
                f"Expected '{msg}' to be recognized as trivial chit-chat",
            )

    def test_substantive_b2b_messages_not_trivial(self):
        substantive_messages = [
            'Our warehouse cannot receive deliveries before 4 PM.',
            'We require 500 trays of 500ml every alternate Tuesday.',
            'Please deliver to Gate 3 with hydraulic lift.',
            'We are expanding to 10 new cafeteria locations in HITEC city.',
            'Can we get a volume quote for 10000 units of 1L?',
        ]
        for msg in substantive_messages:
            self.assertFalse(
                is_trivial_message(msg),
                f"Expected '{msg}' to be substantive B2B context",
            )

    def test_extract_memories_fallback_warehouse_restriction(self):
        text = "Our warehouse cannot receive deliveries before 4 PM."
        memories = extract_memories_fallback(text)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['category'], 'warehouse_restrictions')
        self.assertIn('before 4 PM', memories[0]['content'])

    def test_extract_memories_fallback_recurring_pattern(self):
        text = "We need 500 trays every week for our banquet hall."
        memories = extract_memories_fallback(text)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['category'], 'recurring_order_patterns')
        self.assertIn('500 trays', memories[0]['content'])

    def test_extract_contextual_memories_filters_trivial_chat(self):
        memories = extract_contextual_memories(
            user_message='Okay thanks.',
            ai_response='You are welcome! Let me know if you need anything else.',
            buyer_id='DIST-001',
        )
        self.assertEqual(memories, [])


class DispatchAIServiceTestCase(TestCase):
    """
    Validates the complete 9-step DispatchAI reasoning pipeline:
    1. Receive buyer_id + user message
    2. Validate buyer identity & B2B access
    3. Recall Hindsight persistent memory
    4. Retrieve authoritative SQL catalog, orders, and quotes
    5. Construct controlled prompt with strict negative constraints
    6. Send to Groq (configured model)
    7. Validate response against business rules
    8. Retain new memory
    9. Return final response & save audit decision
    """

    def setUp(self):
        self.category = Category.objects.create(name='Packaged Water')
        self.p500 = Product.objects.create(
            category=self.category,
            name='Pure Mineral Water 500ml',
            capacity='500 ml',
            price=Decimal('4.50'),
            is_featured=True,
        )
        Inventory.objects.create(product=self.p500, quantity_in_stock=5000)

        # B2B Buyer
        self.b2b_user = User.objects.create_user(
            username='b2b_agent_buyer',
            email='agent_buyer@wholesale.in',
            password='password123',
        )
        self.b2b_profile = UserProfile.objects.create(
            user=self.b2b_user,
            account_type='b2b',
            role='distributor',
            company_name='Deccan Logistics Hub',
            buyer_id='DIST-88001',
        )

        # B2C User
        self.b2c_user = User.objects.create_user(
            username='b2c_agent_buyer',
            email='retail@customer.com',
            password='password123',
        )
        self.b2c_profile = UserProfile.objects.create(
            user=self.b2c_user,
            account_type='b2c',
            role='customer',
        )

    def test_validate_buyer_identity_b2b_success(self):
        is_valid, user, buyer_id, err = validate_buyer_identity(self.b2b_user)
        self.assertTrue(is_valid)
        self.assertEqual(user, self.b2b_user)
        self.assertEqual(buyer_id, 'DIST-88001')
        self.assertIsNone(err)

    def test_validate_buyer_identity_b2c_access_denied(self):
        is_valid, user, buyer_id, err = validate_buyer_identity(self.b2c_user)
        self.assertFalse(is_valid)
        self.assertIn('Access restricted', err)

    def test_validate_buyer_identity_non_existent(self):
        is_valid, user, buyer_id, err = validate_buyer_identity('NON_EXISTENT_BUYER_ID')
        self.assertFalse(is_valid)
        self.assertIn('not found', err)

    def test_9_step_pipeline_execution_with_mocked_groq(self):
        mock_groq_resp = {
            'content': 'We can supply 500 trays (9000 units) of 500ml at ₹4.50 per unit. Estimated delivery is 2 business days.',
            'model': 'llama-3.3-70b-versatile',
            'tokens_used': 142,
            'latency_ms': 250,
            'finish_reason': 'stop',
        }

        with patch('dispatch.groq_client.chat', return_value=mock_groq_resp), \
             patch('dispatch.services.dispatch_ai_service.recall_customer_memory', return_value=[{'content': 'Prefers morning delivery', 'category': 'preferred_delivery_time'}]) as mock_recall, \
             patch('dispatch.services.dispatch_ai_service.retain_customer_memory', return_value=['mem_new_1']) as mock_retain:

            result = process_dispatch_chat(
                buyer=self.b2b_user,
                user_message="I need 500 trays of 500ml water delivered to Nacharam.",
            )

            self.assertTrue(result['ok'])
            self.assertEqual(result['buyer_id'], 'DIST-88001')
            self.assertIn('₹4.50', result['content'])
            self.assertFalse(result['error'])
            self.assertEqual(result['memories_count'], 1)
            self.assertEqual(result['model'], 'llama-3.3-70b-versatile')

            # Verify session and messages created
            session = ConversationSession.objects.filter(user=self.b2b_user).first()
            self.assertIsNotNone(session)
            self.assertEqual(session.messages.count(), 2)

            # Verify audit decision logged
            decision = DispatchDecision.objects.filter(session=session).first()
            self.assertIsNotNone(decision)
            self.assertIn(decision.decision_type, ['quote_price', 'delivery_estimate', 'stock_check'])

    def test_agent_fallback_when_groq_unconfigured(self):
        with patch('dispatch.groq_client.chat', side_effect=RuntimeError('Groq unconfigured')):
            result = process_dispatch_chat(
                buyer=self.b2b_user,
                user_message="What is the price of 500ml?",
            )
            self.assertTrue(result['ok'])
            self.assertTrue(result['error'])
            self.assertIn('cheersthepure@gmail.com', result['content'])


class AgentChatAPITestCase(TestCase):
    """
    Integration tests for production endpoint POST /api/agent/chat.
    Validates authentication, B2B authorization, request body validation,
    secure buyer_id derivation, rate limiting, and structured JSON output.
    """

    def setUp(self):
        self.client = Client()

        # B2B User
        self.b2b_user = User.objects.create_user(
            username='api_b2b_distributor',
            email='dist@deccan.in',
            password='Password123!',
        )
        self.b2b_profile = UserProfile.objects.create(
            user=self.b2b_user,
            account_type='b2b',
            role='distributor',
            company_name='Deccan Beverages',
            buyer_id='DIST-77001',
        )

        # B2C User
        self.b2c_user = User.objects.create_user(
            username='api_b2c_shopper',
            email='shopper@gmail.com',
            password='Password123!',
        )
        self.b2c_profile = UserProfile.objects.create(
            user=self.b2c_user,
            account_type='b2c',
            role='customer',
        )

    def test_unauthenticated_request_returns_401(self):
        response = self.client.post(
            '/api/agent/chat',
            data={'message': 'What are your wholesale rates?'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Authentication required', data['error'])

    def test_b2c_user_returns_403(self):
        self.client.force_login(self.b2c_user)
        response = self.client.post(
            '/api/agent/chat',
            data={'message': 'Give me wholesale prices.'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Access restricted', data['error'])

    def test_empty_message_returns_400(self):
        self.client.force_login(self.b2b_user)
        response = self.client.post(
            '/api/agent/chat',
            data={'message': ''},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('required', data['error'].lower())

    def test_message_too_long_returns_400(self):
        self.client.force_login(self.b2b_user)
        huge_message = "A" * 4001
        response = self.client.post(
            '/api/agent/chat',
            data={'message': huge_message},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('exceeds maximum', data['error'].lower())

    def test_b2b_user_success_response_structure(self):
        self.client.force_login(self.b2b_user)
        mock_groq = {
            'content': 'We offer 500ml water at ₹4.50/unit for wholesale orders.',
            'model': 'llama-3.3-70b-versatile',
            'tokens_used': 95,
            'latency_ms': 180,
            'finish_reason': 'stop',
        }

        with patch('dispatch.groq_client.chat', return_value=mock_groq), \
             patch('dispatch.services.dispatch_ai_service.recall_customer_memory', return_value=[]), \
             patch('dispatch.services.dispatch_ai_service.retain_customer_memory', return_value=[]):

            response = self.client.post(
                '/api/agent/chat',
                data={'message': 'What is the price of 500ml water?'},
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertIn('reply', data)
            self.assertIn('₹4.50', data['reply'])
            self.assertIn('memory_used', data)
            self.assertIn('memory_summary', data)
            self.assertIn('sources', data)
            self.assertIsInstance(data['sources'], list)
            self.assertIn('actions', data)
            self.assertIsInstance(data['actions'], list)
            self.assertEqual(data['buyer_id'], 'DIST-77001')

    def test_buyer_id_derived_securely_when_omitted(self):
        self.client.force_login(self.b2b_user)
        mock_groq = {
            'content': 'Hello, how can I assist with your supply requirements?',
            'model': 'llama-3.3-70b-versatile',
            'tokens_used': 45,
            'latency_ms': 120,
            'finish_reason': 'stop',
        }

        with patch('dispatch.groq_client.chat', return_value=mock_groq), \
             patch('dispatch.services.dispatch_ai_service.recall_customer_memory', return_value=[]), \
             patch('dispatch.services.dispatch_ai_service.retain_customer_memory', return_value=[]):

            response = self.client.post(
                '/api/agent/chat',
                data={'message': 'Hello DispatchAI'},
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['buyer_id'], 'DIST-77001')

    def test_rate_limiting_triggers_429(self):
        self.client.force_login(self.b2b_user)
        with patch('dispatch.views.is_rate_limited', return_value=True):
            response = self.client.post(
                '/api/agent/chat',
                data={'message': 'Rapid query'},
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 429)
            data = response.json()
            self.assertFalse(data['success'])
            self.assertIn('Rate limit exceeded', data['error'])


class DispatchToolsTestCase(TestCase):
    """
    Validates the 9 safe backend tools, two-phase confirmation workflows,
    and AgentActionLog audit trail.
    """

    def setUp(self):
        self.category = Category.objects.create(name='Pure Mineral Water')
        self.p500 = Product.objects.create(
            category=self.category,
            name='Pure Mineral Water 500ml',
            capacity='500 ml',
            price=Decimal('4.50'),
            is_featured=True,
        )
        self.inv500 = Inventory.objects.create(
            product=self.p500,
            quantity_in_stock=10000,
        )

        self.user = User.objects.create_user(
            username='tool_test_buyer',
            email='tools@deccan.in',
            password='Password123!',
            first_name='Anil',
            last_name='Reddy',
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            account_type='b2b',
            role='distributor',
            company_name='Deccan Beverages',
            buyer_id='DIST-55001',
            address='Plot 15, IDA Nacharam',
            city='Hyderabad',
            state='Telangana',
            postal_code='500076',
            gstin='36BBBBB0000B1Z8',
        )

    def test_tool_search_product(self):
        # Search by query
        results = search_product(query='500ml')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Pure Mineral Water 500ml')

        # Search by non-existent query
        no_match = search_product(query='NonExistentBrand')
        self.assertEqual(len(no_match), 0)

    def test_tool_get_current_price(self):
        price = tool_get_current_price(self.p500.id)
        self.assertEqual(price, Decimal('4.50'))

        unlisted_price = tool_get_current_price('20L Water Jar')
        self.assertIsNone(unlisted_price)

    def test_tool_create_quote_request_proposal_and_confirmation(self):
        # Step 1: Proposal mode (confirmed=False)
        proposal = create_quote_request(
            user=self.user,
            product_identifier=self.p500.id,
            quantity=500,
            preferred_delivery_timing='Within 48 hours',
            delivery_address='Plot 15, IDA Nacharam',
            confirmed=False,
        )
        self.assertTrue(proposal['success'])
        self.assertTrue(proposal['is_proposal'])
        self.assertTrue(proposal['requires_confirmation'])
        self.assertIn('proposal_id', proposal)
        self.assertIn('500 units', proposal['explanation'])

        # Verify QuoteRequest was NOT yet written to DB
        self.assertEqual(QuoteRequest.objects.filter(user=self.user).count(), 0)

        # Verify AgentActionLog recorded as 'proposed'
        log = AgentActionLog.objects.filter(user=self.user, action_type='create_quote_request').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'proposed')
        self.assertTrue(log.is_sensitive)

        # Step 2: Confirmed execution mode (confirmed=True)
        execution = create_quote_request(
            user=self.user,
            product_identifier=self.p500.id,
            quantity=500,
            preferred_delivery_timing='Within 48 hours',
            delivery_address='Plot 15, IDA Nacharam',
            confirmed=True,
        )
        self.assertTrue(execution['success'])
        self.assertFalse(execution['is_proposal'])
        self.assertIn('quote_id', execution)

        # Verify QuoteRequest was written to DB
        self.assertEqual(QuoteRequest.objects.filter(user=self.user).count(), 1)
        created_quote = QuoteRequest.objects.filter(user=self.user).first()
        self.assertEqual(created_quote.quantity, 500)
        self.assertEqual(created_quote.product, self.p500)

        # Verify AgentActionLog recorded as 'executed'
        exec_log = AgentActionLog.objects.filter(user=self.user, action_type='create_quote_request', status='executed').first()
        self.assertIsNotNone(exec_log)
        self.assertTrue(exec_log.confirmed_by_user)

    def test_tool_create_quote_request_moq_validation(self):
        result = create_quote_request(
            user=self.user,
            product_identifier=self.p500.id,
            quantity=20,  # Below MOQ of 100
            confirmed=False,
        )
        self.assertFalse(result['success'])
        self.assertIn('Minimum Order Quantity (MOQ)', result['error'])

    def test_tool_prepare_order_request_proposal_and_confirmation(self):
        items = [{'product_id': self.p500.id, 'quantity': 1000}]

        # Step 1: Proposal (confirmed=False)
        proposal = prepare_order_request(
            user=self.user,
            items=items,
            shipping_address='Plot 15, IDA Nacharam, Hyderabad',
            payment_method='cod',
            confirmed=False,
        )
        self.assertTrue(proposal['success'])
        self.assertTrue(proposal['is_proposal'])
        self.assertTrue(proposal['requires_confirmation'])
        self.assertIn('Advance payable', proposal['explanation'])
        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)

        # Step 2: Confirmed Execution (confirmed=True)
        execution = prepare_order_request(
            user=self.user,
            items=items,
            shipping_address='Plot 15, IDA Nacharam, Hyderabad',
            payment_method='cod',
            confirmed=True,
        )
        self.assertTrue(execution['success'])
        self.assertFalse(execution['is_proposal'])
        self.assertIn('order_number', execution)

        # Verify Order and OrderItems created in database
        order = Order.objects.filter(user=self.user).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_amount, Decimal('4500.00'))

    def test_tool_prepare_order_request_insufficient_stock(self):
        # Request more than available stock (10,000 in stock)
        items = [{'product_id': self.p500.id, 'quantity': 50000}]
        result = prepare_order_request(
            user=self.user,
            items=items,
            shipping_address='Plot 15, IDA Nacharam',
            confirmed=False,
        )
        self.assertFalse(result['success'])
        self.assertIn('Insufficient stock', result['error'])

    def test_tool_check_delivery_preference(self):
        with patch('dispatch.tools.recall_customer_memory', return_value=[{'content': 'Forklift unloading available'}]):
            res = check_delivery_preference(user=self.user)
            self.assertEqual(res['buyer_id'], 'DIST-55001')
            self.assertEqual(res['city'], 'Hyderabad')
            self.assertEqual(len(res['logistics_memories']), 1)

    def test_tool_summarize_customer_requirements(self):
        with patch('dispatch.tools.recall_customer_memory', return_value=[]):
            res = summarize_customer_requirements(user=self.user)
            self.assertEqual(res['buyer_id'], 'DIST-55001')
            self.assertEqual(res['company_name'], 'Deccan Beverages')
            self.assertIn('orders_summary', res)
            self.assertIn('quotes_summary', res)


class DispatchDashboardInterfaceTestCase(TestCase):
    """
    Validates that the professional DispatchAI chat interface is properly
    embedded inside the B2B Dashboard and contains all required title,
    prompts, indicators, and access restrictions.
    """

    def setUp(self):
        self.client = Client()

        # B2B Distributor User
        self.b2b_user = User.objects.create_user(
            username='dashboard_distributor',
            email='dist@hyderabadwaters.com',
            password='Password123!',
        )
        self.b2b_profile = UserProfile.objects.create(
            user=self.b2b_user,
            account_type='b2b',
            role='distributor',
            company_name='Hyderabad Water Distributors Ltd',
            buyer_id='DIST-88001',
            city='Hyderabad',
            state='Telangana',
        )

        # B2C Consumer User
        self.b2c_user = User.objects.create_user(
            username='dashboard_consumer',
            email='shopper@gmail.com',
            password='Password123!',
        )
        self.b2c_profile = UserProfile.objects.create(
            user=self.b2c_user,
            account_type='b2c',
            role='customer',
        )

    def test_b2b_dashboard_renders_dispatch_ai_console(self):
        self.client.force_login(self.b2b_user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        html = response.content.decode('utf-8')

        # 1. DispatchAI title and explanation
        self.assertIn('DispatchAI', html)
        self.assertIn('B2B Supply &amp; Distribution Assistant', html)
        self.assertIn('dispatch-dashboard-chat', html)

        # 2. Suggested business prompts
        self.assertIn('Show my recent order history.', html)
        self.assertIn('Do you remember my delivery preference?', html)
        self.assertIn('I need my usual order again.', html)
        self.assertIn('What products are available?', html)
        self.assertIn('Prepare a quote for my next order.', html)

        # 3. Floating panel & launcher
        self.assertIn('dispatch-panel', html)
        self.assertIn('dispatch-launcher', html)

        # 4. CSS and JS inclusions
        self.assertIn('dispatch_chat.css', html)
        self.assertIn('dispatch_chat.js', html)

    def test_b2c_dashboard_does_not_render_dispatch_ai_widget(self):
        self.client.force_login(self.b2c_user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        html = response.content.decode('utf-8')
        # B2C regular dashboard must not include the B2B distributor assistant
        self.assertNotIn('dispatch-dashboard-chat', html)
        self.assertNotIn('id="dispatch-panel"', html)

    def test_agent_chat_api_flags_drive_ui_indicators(self):
        self.client.force_login(self.b2b_user)

        # Test case A: With memory recalled -> memory_used is True
        mock_groq = {
            'content': 'I remember your warehouse receives deliveries after 4 PM.',
            'model': 'llama-3.3-70b-versatile',
            'tokens_used': 60,
            'latency_ms': 150,
            'finish_reason': 'stop',
        }
        mock_memories = [
            {'content': 'Warehouse cannot receive deliveries before 4 PM', 'id': 'mem-1'}
        ]

        with patch('dispatch.groq_client.chat', return_value=mock_groq), \
             patch('dispatch.services.dispatch_ai_service.recall_customer_memory', return_value=mock_memories), \
             patch('dispatch.services.dispatch_ai_service.retain_customer_memory', return_value=[]):

            response = self.client.post(
                '/api/agent/chat',
                data={'message': 'Do you remember my delivery preference?'},
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            # memory_used must be True to trigger "Memory used" badge in UI
            self.assertTrue(data['memory_used'])
            self.assertIn('Recalled 1 customer preference', data['memory_summary'])
            # sources must contain database and memory
            self.assertIn('Cheers the Pure Authoritative Database Catalog', data['sources'])
            self.assertIn('Hindsight Persistent Memory (cheersthepure-b2b)', data['sources'])

        # Test case B: Without memory recalled -> memory_used is False (no fake indicator)
        with patch('dispatch.groq_client.chat', return_value=mock_groq), \
             patch('dispatch.services.dispatch_ai_service.recall_customer_memory', return_value=[]), \
             patch('dispatch.services.dispatch_ai_service.retain_customer_memory', return_value=[]):

            response = self.client.post(
                '/api/agent/chat',
                data={'message': 'What products are available?'},
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertFalse(data['memory_used'])
            self.assertNotIn('Hindsight Persistent Memory (cheersthepure-b2b)', data['sources'])
            self.assertIn('Cheers the Pure Authoritative Database Catalog', data['sources'])


class MemoryDemonstrationTestCase(TestCase):
    """
    Validates the controlled 'Memory Demonstration' feature for DispatchAI:
    - Customer: Sri Balaji Supermarket (DIST-BALAJI-01)
    - Session 1: Storing delivery constraint in Hindsight
    - New Session Transition: Memory is preserved across sessions
    - Session 2: Recalling previous delivery preference when ordering cases
    - Technical Panel: Telemetry fields and zero secret leakage
    """

    def setUp(self):
        self.client = Client()
        from dispatch.demo_service import get_or_create_demo_customer, reset_demo_data
        self.user = get_or_create_demo_customer()
        reset_demo_data()

    def test_demo_customer_profile_initialized(self):
        from dispatch.demo_service import DEMO_BUYER_ID, DEMO_COMPANY
        self.assertEqual(self.user.profile.buyer_id, DEMO_BUYER_ID)
        self.assertEqual(self.user.profile.company_name, DEMO_COMPANY)
        self.assertEqual(self.user.profile.account_type, 'b2b')

    def test_demo_view_renders_properly(self):
        response = self.client.get('/demo/memory/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Sri Balaji Supermarket', html)
        self.assertIn('DIST-BALAJI-01', html)
        self.assertIn('Step 1: Session 1 (Create Memory)', html)
        self.assertIn('Start New Session', html)
        self.assertIn('Step 2: Session 2 (Recall Memory)', html)
        self.assertIn('Live Evaluation Telemetry', html)

    def test_complete_two_session_memory_workflow(self):
        # ── SESSION 1: Express delivery constraint ────────────────────────────
        session_1_msg = "We usually need delivery after 4 PM because our shop is busy before that."

        resp1 = self.client.post(
            '/api/demo/memory/chat/',
            data={
                'message': session_1_msg,
                'session_number': 1,
            },
            content_type='application/json',
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()

        self.assertTrue(data1['success'])
        self.assertEqual(data1['buyer_id'], 'DIST-BALAJI-01')
        self.assertEqual(data1['session_number'], 1)
        # Memory created in Hindsight
        self.assertTrue(data1['memory_created'])
        self.assertGreaterEqual(len(data1['memory_retained']), 1)
        self.assertIn('after 4', str(data1['memory_retained']))

        # ── TRANSITION: Create fresh session ID (Simulating "Start New Session") ──
        old_session_id = data1['session_id']
        new_session_id = f"sess_demo_fresh_{int(time.time())}"
        self.assertNotEqual(old_session_id, new_session_id)

        # ── SESSION 2: Inquire about bulk order in new session ────────────────
        session_2_msg = "I need 150 cases this time."

        resp2 = self.client.post(
            '/api/demo/memory/chat/',
            data={
                'message': session_2_msg,
                'session_id': new_session_id,
                'session_number': 2,
            },
            content_type='application/json',
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()

        self.assertTrue(data2['success'])
        self.assertEqual(data2['session_number'], 2)
        # Memory recalled from Hindsight
        self.assertTrue(data2['memory_used'])
        self.assertGreaterEqual(data2['memory_recalled_count'], 1)
        self.assertIn('after 4', str(data2['memory_recalled']))
        # Agent response incorporates the recalled delivery constraint
        self.assertIn('150', data2['reply'])
        self.assertIn('4', data2['reply'])

    def test_technical_panel_telemetry_security(self):
        response = self.client.post(
            '/api/demo/memory/chat/',
            data={
                'message': 'What products do you offer?',
                'session_number': 1,
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check required telemetry keys
        self.assertIn('buyer_id', data)
        self.assertIn('session_id', data)
        self.assertIn('memory_recalled', data)
        self.assertIn('memory_retained', data)
        self.assertIn('database_used', data)

        # Confirm zero secret leakage
        raw_json_str = str(data)
        self.assertNotIn('HINDSIGHT_API_KEY', raw_json_str)
        self.assertNotIn('GROQ_API_KEY', raw_json_str)
        self.assertNotIn('sk-', raw_json_str)
        self.assertNotIn('gsk_', raw_json_str)







