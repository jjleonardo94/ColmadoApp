import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError

from apps.core.models import BusinessSettings, AuditLog, ColmadoBranch
from apps.accounts.models import UserProfile, UserRole, CustomRole
from apps.catalog.models import Category, Product, UnitOfMeasure, SaleType
from apps.inventory.models import InventoryMovement, MovementType
from apps.inventory.services import InventoryService
from apps.sales.models import Sale, SaleItem, Payment, SaleStatus, PaymentMethodChoices
from apps.sales.services import SaleService
from apps.customers.models import Customer, CreditTransaction, CreditTransactionType
from apps.customers.services import CustomerCreditService
from apps.cash.models import CashRegister, CashShift, CashDenomination, CashShiftStatus
from apps.cash.services import CashService
from unittest.mock import patch, MagicMock
from apps.purchasing.models import Supplier, Purchase, PurchaseItem, PurchaseStatus
from apps.purchasing.services import PurchaseService
from apps.expenses.models import ExpenseCategory, Expense
from apps.whatsapp.models import WhatsAppContact, WhatsAppConversation, WhatsAppMessage
from apps.whatsapp.services import WhatsAppService, WAHAService


class ColmadoPOSTestSuite(TestCase):
    """
    Suite Integral de Pruebas Automatizadas de ColmadoPOS
    Verifica las reglas de negocio, integridad transaccional, contabilidad de caja,
    inventario y webhooks de WhatsApp.
    """

    def setUp(self):
        # 1. Configuración del Colmado
        self.settings = BusinessSettings.get_settings()
        self.settings.name = "Colmado Test"
        self.settings.allow_negative_stock = False
        self.settings.save()

        # 2. Usuarios y Roles
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='Password123!',
            is_staff=True,
            is_superuser=True
        )
        self.admin_user.profile.role = UserRole.ADMIN
        self.admin_user.profile.can_void_sales = True
        self.admin_user.profile.can_adjust_inventory = True
        self.admin_user.profile.save()

        self.cajero_user = User.objects.create_user(
            username='cajero_test',
            password='Password123!'
        )
        self.cajero_user.profile.role = UserRole.CAJERO
        self.cajero_user.profile.can_authorize_credit = True
        self.cajero_user.profile.save()

        # 3. Denominaciones Dominicanas
        self.denom_1000 = CashDenomination.objects.create(name='RD$ 1000', value=Decimal('1000.00'), denomination_type='BILLETE')
        self.denom_500 = CashDenomination.objects.create(name='RD$ 500', value=Decimal('500.00'), denomination_type='BILLETE')
        self.denom_100 = CashDenomination.objects.create(name='RD$ 100', value=Decimal('100.00'), denomination_type='BILLETE')
        self.denom_25 = CashDenomination.objects.create(name='RD$ 25', value=Decimal('25.00'), denomination_type='MONEDA')

        # 4. Caja Registradora y Turno Abierto
        self.register = CashRegister.objects.create(name="Caja 1", code="CAJA-01")
        self.shift = CashService.open_shift(
            register_id=self.register.id,
            cashier=self.cajero_user,
            initial_cash=Decimal('1500.00'),
            initial_notes="Fondo inicial de prueba"
        )

        # 5. Categoría y Productos
        self.categoria_bebidas = Category.objects.create(name="Bebidas", description="Cervezas y refrescos")
        self.categoria_viveres = Category.objects.create(name="Víveres y Granos", description="Arroz, habichuelas y víveres")

        # Producto por unidad (Cerveza Presidente)
        self.prod_presidente = Product.objects.create(
            name="Cerveza Presidente 650ml",
            internal_code="PRES-650",
            category=self.categoria_bebidas,
            unit_of_measure=UnitOfMeasure.UNIDAD,
            sale_type=SaleType.UNIT,
            cost_price=Decimal('140.00'),
            sale_price=Decimal('185.00'),
            current_stock=Decimal('24.00'),
            min_stock=Decimal('6.00')
        )

        # Producto fraccionado por libra (Arroz Campos)
        self.prod_arroz = Product.objects.create(
            name="Arroz Selecto Campos",
            internal_code="ARR-CAMPOS",
            category=self.categoria_viveres,
            unit_of_measure=UnitOfMeasure.LIBRA,
            sale_type=SaleType.FRACTION,
            cost_price=Decimal('35.00'),
            sale_price=Decimal('45.00'),
            current_stock=Decimal('100.00'),
            min_stock=Decimal('20.00')
        )

        # 6. Cliente con crédito de RD$ 2,000
        self.cliente = Customer.objects.create(
            name="Juan de la Cruz",
            phone="8095551234",
            credit_limit=Decimal('2000.00'),
            is_active=True
        )

        # 7. Cliente de prueba HTTP
        self.client = Client()

    # --- 1. Autenticación y Permisos ---
    def test_login_and_role_permissions(self):
        """Verifica inicio de sesión y restricciones de rol"""
        login_success = self.client.login(username='cajero_test', password='Password123!')
        self.assertTrue(login_success, "El cajero debe poder iniciar sesión")

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        # Un cajero no debe poder acceder a la configuración del negocio (restringido a ADMIN)
        response_settings = self.client.get(reverse('business_settings'))
        # Debe redirigir con mensaje de error
        self.assertEqual(response_settings.status_code, 302)

    # --- 2. Creación y Validación de Productos ---
    def test_product_unit_vs_fractional_sale(self):
        """Verifica que un producto por unidad prohíba cantidades decimales"""
        self.assertEqual(self.prod_presidente.sale_type, SaleType.UNIT)
        self.assertEqual(self.prod_arroz.sale_type, SaleType.FRACTION)

        # Venta de producto por unidad con decimal debe ser rechazada
        items_invalido = [{
            'product_id': self.prod_presidente.id,
            'quantity': Decimal('1.5'),
        }]
        payments = [{
            'payment_method': PaymentMethodChoices.EFECTIVO,
            'amount': Decimal('277.50'),
            'received_amount': Decimal('277.50'),
            'change_amount': Decimal('0.00')
        }]

        with self.assertRaises(ValidationError) as ctx:
            SaleService.create_sale(
                cashier=self.cajero_user,
                items_data=items_invalido,
                payments_data=payments,
                cash_shift_id=self.shift.id
            )
        self.assertIn("no admite decimales", str(ctx.exception))

    # --- 3. Registro de Venta y Descuento Automático de Inventario ---
    def test_sale_creation_and_inventory_deduction(self):
        """Una venta exitosa debe descontar inventario y registrar movimiento Kardex"""
        stock_inicial = self.prod_presidente.current_stock
        cantidad_vender = Decimal('4.00')

        items = [{
            'product_id': self.prod_presidente.id,
            'quantity': cantidad_vender,
        }]
        payments = [{
            'payment_method': PaymentMethodChoices.EFECTIVO,
            'amount': Decimal('740.00'),
            'received_amount': Decimal('1000.00'),
            'change_amount': Decimal('260.00')
        }]

        sale = SaleService.create_sale(
            cashier=self.cajero_user,
            items_data=items,
            payments_data=payments,
            cash_shift_id=self.shift.id
        )

        self.assertIsNotNone(sale.id)
        self.assertEqual(sale.total, Decimal('740.00'))
        self.assertEqual(sale.status, SaleStatus.COMPLETADA)

        # Verificar descuento en producto
        self.prod_presidente.refresh_from_db()
        self.assertEqual(self.prod_presidente.current_stock, stock_inicial - cantidad_vender)

        # Verificar movimiento Kardex
        kardex = InventoryMovement.objects.filter(product=self.prod_presidente, reference_doc__icontains=sale.ticket_number).first()
        self.assertIsNotNone(kardex)
        self.assertEqual(kardex.movement_type, MovementType.VENTA)
        self.assertEqual(kardex.quantity, cantidad_vender)
        self.assertEqual(kardex.previous_stock, stock_inicial)
        self.assertEqual(kardex.new_stock, stock_inicial - cantidad_vender)

    # --- 4. Prevención de Inventario Negativo ---
    def test_prevent_negative_inventory_when_disabled(self):
        """Si allow_negative_stock es False, se debe rechazar la venta si excede existencias"""
        self.settings.allow_negative_stock = False
        self.settings.save()

        items_excesivos = [{
            'product_id': self.prod_presidente.id,
            'quantity': Decimal('50.00'), # Solo hay 24
        }]
        payments = [{
            'payment_method': PaymentMethodChoices.EFECTIVO,
            'amount': Decimal('9250.00'),
            'received_amount': Decimal('9250.00'),
            'change_amount': Decimal('0.00')
        }]

        with self.assertRaises(ValidationError) as ctx:
            SaleService.create_sale(
                cashier=self.cajero_user,
                items_data=items_excesivos,
                payments_data=payments,
                cash_shift_id=self.shift.id
            )
        self.assertIn("Stock insuficiente", str(ctx.exception))

    # --- 5. Pagos Combinados (Efectivo + Transferencia) ---
    def test_combined_multi_payment(self):
        """Permite pagar una venta con múltiples métodos combinados"""
        items = [{
            'product_id': self.prod_arroz.id,
            'quantity': Decimal('10.00'),
        }] # 10 * 45 = 450.00 RD$

        payments = [
            {
                'payment_method': PaymentMethodChoices.EFECTIVO,
                'amount': Decimal('250.00'),
                'received_amount': Decimal('250.00'),
                'change_amount': Decimal('0.00')
            },
            {
                'payment_method': PaymentMethodChoices.TRANSFERENCIA,
                'amount': Decimal('200.00'),
                'received_amount': Decimal('200.00'),
                'change_amount': Decimal('0.00'),
                'reference': 'TRANS-9874'
            }
        ]

        sale = SaleService.create_sale(
            cashier=self.cajero_user,
            items_data=items,
            payments_data=payments,
            cash_shift_id=self.shift.id
        )

        self.assertEqual(sale.total, Decimal('450.00'))
        self.assertEqual(sale.payments.count(), 2)
        total_pagado = sum(p.amount for p in sale.payments.all())
        self.assertEqual(total_pagado, Decimal('450.00'))

    # --- 6. Venta Fiada y Límite de Crédito del Cliente ---
    def test_fiado_sale_and_credit_limit_enforcement(self):
        """Verifica que no se permita superar el límite de fiado del cliente"""
        # Cliente tiene límite de 2,000 RD$
        items = [{
            'product_id': self.prod_presidente.id,
            'quantity': Decimal('5.00'),
        }] # 5 * 185 = 925.00 RD$

        payments = [{
            'payment_method': PaymentMethodChoices.FIADO,
            'amount': Decimal('925.00'),
            'received_amount': Decimal('0.00'),
            'change_amount': Decimal('0.00')
        }]

        sale = SaleService.create_sale(
            cashier=self.cajero_user,
            items_data=items,
            payments_data=payments,
            customer_id=self.cliente.id,
            cash_shift_id=self.shift.id
        )

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.current_balance, Decimal('925.00'))
        self.assertEqual(self.cliente.available_credit, Decimal('1075.00'))

        # Intentar una segunda venta fiada por 1,500 RD$ (Superaría el límite de 2,000 RD$)
        items_exceso = [{
            'product_id': self.prod_arroz.id,
            'quantity': Decimal('30.00'),
        }] # 30 * 45 = 1,350 RD$ + 925 = 2,275 RD$ > 2,000 RD$

        payments_exceso = [{
            'payment_method': PaymentMethodChoices.FIADO,
            'amount': Decimal('1350.00'),
            'received_amount': Decimal('0.00'),
            'change_amount': Decimal('0.00')
        }]

        with self.assertRaises(ValidationError) as ctx:
            SaleService.create_sale(
                cashier=self.cajero_user,
                items_data=items_exceso,
                payments_data=payments_exceso,
                customer_id=self.cliente.id,
                cash_shift_id=self.shift.id
            )
        self.assertIn("límite de crédito", str(ctx.exception).lower())

    # --- 7. Registro de Abono y Reducción del Saldo de Fiado ---
    def test_customer_abono_registration_and_cash_shift_impact(self):
        """Un abono a fiado debe reducir la deuda del cliente e ingresar efectivo a la caja activa"""
        # Crear deuda de 1000 RD$
        CreditTransaction.objects.create(
            customer=self.cliente,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=Decimal('1000.00'),
            balance_after=Decimal('1000.00'),
            user=self.cajero_user,
            notes="Deuda inicial de prueba"
        )
        self.assertEqual(self.cliente.current_balance, Decimal('1000.00'))

        # Registrar abono de 600 RD$ en efectivo
        tx = CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('600.00'),
            payment_method='EFECTIVO',
            user=self.cajero_user,
            cash_shift_id=self.shift.id,
            notes="Abono parcial en efectivo"
        )

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.current_balance, Decimal('400.00'))
        self.assertEqual(tx.balance_after, Decimal('400.00'))

        # Verificar que el abono se registró como movimiento en el turno de caja abierto
        cash_mov = self.shift.movements.filter(description__icontains=self.cliente.name).first()
        self.assertIsNotNone(cash_mov, "El abono debe registrar una entrada en el turno de caja")
        self.assertEqual(cash_mov.amount, Decimal('600.00'))

    # --- 8. Apertura, Conteo de Denominaciones y Cierre de Caja ---
    def test_cash_shift_closing_and_difference_calculation(self):
        """Verifica conteo físico de billetes y monedas, cálculo de diferencias y cierre inmutable"""
        # Fondo inicial: 1500 RD$
        # Agregar una venta en efectivo de 450 RD$
        items = [{
            'product_id': self.prod_arroz.id,
            'quantity': Decimal('10.00'),
        }] # 450.00 RD$
        payments = [{
            'payment_method': PaymentMethodChoices.EFECTIVO,
            'amount': Decimal('450.00'),
            'received_amount': Decimal('450.00'),
            'change_amount': Decimal('0.00')
        }]
        SaleService.create_sale(
            cashier=self.cajero_user,
            items_data=items,
            payments_data=payments,
            cash_shift_id=self.shift.id
        )

        # Efectivo esperado = 1500 + 450 = 1950 RD$
        self.assertEqual(self.shift.calculate_current_expected_cash(), Decimal('1950.00'))

        # Simular conteo físico exacto: 1 billete de 1,000 + 1 billete de 500 + 4 billetes de 100 + 2 monedas de 25 = 1950 RD$
        denominations_data = {
            self.denom_1000.id: 1, # 1000
            self.denom_500.id: 1,  # 500
            self.denom_100.id: 4,  # 400
            self.denom_25.id: 2,   # 50
        }

        closed_shift = CashService.close_shift(
            shift_id=self.shift.id,
            user=self.cajero_user,
            denomination_counts=denominations_data,
            closing_notes="Cierre cuadradito exacto"
        )

        self.assertEqual(closed_shift.status, CashShiftStatus.CERRADO)
        self.assertEqual(closed_shift.difference, Decimal('0.00'))
        self.assertIsNotNone(closed_shift.closed_at)

        # No se debe permitir cerrar un turno ya cerrado
        with self.assertRaises(ValidationError):
            CashService.close_shift(
                shift_id=closed_shift.id,
                user=self.cajero_user,
                denomination_counts=denominations_data
            )

    # --- 9. Gastos Operativos Vinculados a Caja ---
    def test_operational_expense_linked_to_shift(self):
        """Un gasto pagado en efectivo debe vincularse al turno de caja y reflejarse en salidas"""
        cat_luz = ExpenseCategory.objects.create(name="Electricidad Edeeste", description="Factura eléctrica")
        
        gasto = Expense.objects.create(
            category=cat_luz,
            description="Pago de factura de luz del colmado",
            amount=Decimal('450.00'),
            payment_method='EFECTIVO',
            cash_shift=self.shift,
            is_paid=True,
            user=self.cajero_user,
            date=timezone.localdate()
        )

        self.assertEqual(gasto.amount, Decimal('450.00'))
        # El gasto debe reducir el efectivo esperado en el turno
        self.assertEqual(self.shift.total_expenses, Decimal('450.00'))

    # --- 10. Cálculo de Ganancia Real con Costo Histórico ---
    def test_real_profit_calculation_using_historical_cost(self):
        """Verifica que la ganancia se calcule con el costo al momento de venta aun si el producto cambia de costo después"""
        costo_original = Decimal('140.00')
        precio_venta = Decimal('185.00')
        self.prod_presidente.cost_price = costo_original
        self.prod_presidente.sale_price = precio_venta
        self.prod_presidente.save()

        items = [{
            'product_id': self.prod_presidente.id,
            'quantity': Decimal('2.00'),
        }]
        payments = [{
            'payment_method': PaymentMethodChoices.EFECTIVO,
            'amount': Decimal('370.00'),
            'received_amount': Decimal('370.00'),
            'change_amount': Decimal('0.00')
        }]

        sale = SaleService.create_sale(
            cashier=self.cajero_user,
            items_data=items,
            payments_data=payments,
            cash_shift_id=self.shift.id
        )

        sale_item = sale.items.first()
        self.assertEqual(sale_item.unit_cost, costo_original)
        # Ganancia bruta = (185 - 140) * 2 = 90 RD$
        self.assertEqual(sale_item.get_profit(), Decimal('90.00'))

        # Ahora el proveedor aumenta el costo a 170 RD$
        self.prod_presidente.cost_price = Decimal('170.00')
        self.prod_presidente.save()

        # El costo histórico de la venta anterior debe mantenerse intacto
        sale_item.refresh_from_db()
        self.assertEqual(sale_item.unit_cost, costo_original)
        self.assertEqual(sale_item.get_profit(), Decimal('90.00'), "La ganancia histórica de la venta no debe alterarse")

    # --- 11. Recepción de Compras e Idempotencia ---
    def test_purchase_reception_idempotency(self):
        """Verifica que recibir una compra aumente existencias una sola vez (idempotente)"""
        suplidor = Supplier.objects.create(name="Cervecería Nacional", phone="8095559999")
        compra = Purchase.objects.create(
            supplier=suplidor,
            invoice_number="FAC-00123",
            purchase_date=timezone.localdate(),
            created_by=self.admin_user
        )
        PurchaseItem.objects.create(
            purchase=compra,
            product=self.prod_presidente,
            quantity=Decimal('10.00'),
            unit_cost=Decimal('140.00'),
            subtotal=Decimal('1400.00')
        )
        compra.total = Decimal('1400.00')
        compra.save()

        stock_antes = self.prod_presidente.current_stock

        # Primera recepción: debe sumar 10 unidades
        PurchaseService.receive_purchase(compra.id, self.admin_user)
        self.prod_presidente.refresh_from_db()
        self.assertEqual(self.prod_presidente.current_stock, stock_antes + Decimal('10.00'))
        
        compra.refresh_from_db()
        self.assertEqual(compra.status, PurchaseStatus.RECIBIDA)

        # Segunda recepción: debe rechazar porque ya fue recibida (idempotente)
        with self.assertRaises(ValidationError):
            PurchaseService.receive_purchase(compra.id, self.admin_user)
        self.prod_presidente.refresh_from_db()
        self.assertEqual(self.prod_presidente.current_stock, stock_antes + Decimal('10.00'))

    # --- 12. WhatsApp Webhook: Verificación, Deduplicación e Intenciones ---
    def test_whatsapp_webhook_verification(self):
        """Verifica el handshake GET oficial de Meta con hub.mode, hub.verify_token y hub.challenge"""
        url = reverse('whatsapp_webhook')
        from django.conf import settings
        expected_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '')
        response = self.client.get(url, {
            'hub.mode': 'subscribe',
            'hub.verify_token': expected_token,
            'hub.challenge': '123456789'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), '123456789')

        # Con token incorrecto debe responder 403
        response_bad = self.client.get(url, {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'token_falso',
            'hub.challenge': '123456789'
        })
        self.assertEqual(response_bad.status_code, 403)

    def test_whatsapp_message_deduplication_and_intent(self):
        """Verifica deduplicación de mensaje por wamid y reconocimiento de intención de saldo"""
        # Vincular contacto de WhatsApp con cliente de prueba
        contact = WhatsAppContact.objects.create(
            phone="18095551234",
            display_name="Juan de la Cruz",
            customer=self.cliente,
            is_verified=True
        )
        CreditTransaction.objects.create(
            customer=self.cliente,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=Decimal('850.00'),
            balance_after=Decimal('850.00'),
            user=self.admin_user,
            notes="Deuda registrada"
        )

        mock_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "10001",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "1555025", "phone_number_id": "10002"},
                        "contacts": [{"profile": {"name": "Juan de la Cruz"}, "wa_id": "8095551234"}],
                        "messages": [{
                            "from": "8095551234",
                            "id": "wamid.HBgLMTAwMDI=",
                            "timestamp": "1700000000",
                            "text": {"body": "Buenas tardes, ¿cuánto debo en el colmado?"},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        # Procesar primer mensaje
        WhatsAppService.process_incoming_webhook(mock_payload)

        # Debe haberse registrado 1 mensaje entrante
        mensajes_recibidos = WhatsAppMessage.objects.filter(wamid="wamid.HBgLMTAwMDI=")
        self.assertEqual(mensajes_recibidos.count(), 1)
        
        # Debe haberse generado una respuesta automática de saldo sugerido
        respuestas = WhatsAppMessage.objects.filter(direction='OUTBOUND')
        self.assertTrue(respuestas.exists(), "Debe enviar respuesta con balance del cliente")
        self.assertIn("RD$ 850.00", respuestas.first().text_content)

        # Repetir el mismo payload (simulando reintento de Meta)
        WhatsAppService.process_incoming_webhook(mock_payload)

        # El conteo de mensajes no debe duplicarse gracias a deduplicación por wamid
        self.assertEqual(WhatsAppMessage.objects.filter(wamid="wamid.HBgLMTAwMDI=").count(), 1)

    # --- 13. WAHA (WhatsApp HTTP API) Webhook & Anti-Ban Testing ---
    def test_waha_webhook_message_processing_and_customer_matching(self):
        """Verifica que un webhook entrante de WAHA registre el mensaje, cree la conversación y vincule al cliente"""
        contact = WhatsAppContact.objects.create(
            phone="18095551234",
            display_name="Juan de la Cruz",
            customer=self.cliente,
            is_verified=True
        )
        CreditTransaction.objects.create(
            customer=self.cliente,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=Decimal('420.00'),
            balance_after=Decimal('420.00'),
            user=self.admin_user,
            notes="Fiado inicial"
        )

        waha_payload = {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "waha_true_18095551234@c.us_3EB01",
                "timestamp": 1700000000,
                "from": "18095551234@c.us",
                "to": "18095550000@c.us",
                "body": "Hola, ¿cuánto debo en el colmado?",
                "fromMe": False,
                "hasMedia": False
            }
        }

        with patch('apps.whatsapp.services.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'id': 'waha_reply_999'}
            
            # Llamar webhook a través de la vista POST
            url = reverse('whatsapp_webhook')
            response = self.client.post(url, data=json.dumps(waha_payload), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get('status'), 'WAHA_EVENT_RECEIVED')

            # Verificar que se registró el mensaje entrante
            inbound_msg = WhatsAppMessage.objects.filter(wamid="waha_true_18095551234@c.us_3EB01").first()
            self.assertIsNotNone(inbound_msg)
            self.assertEqual(inbound_msg.direction, 'INBOUND')
            self.assertEqual(inbound_msg.content, "Hola, ¿cuánto debo en el colmado?")

            # Verificar que la conversación existe y vinculó al cliente
            conv = inbound_msg.conversation
            self.assertEqual(conv.contact.phone, "18095551234")
            self.assertEqual(conv.contact.customer, self.cliente)

            # Verificar que se generó la respuesta automática con el balance pendiente
            outbound_msg = WhatsAppMessage.objects.filter(conversation=conv, direction='OUTBOUND').first()
            self.assertIsNotNone(outbound_msg, "Debe enviar respuesta con balance del cliente")
            self.assertIn("RD$ 420.00", outbound_msg.content)
            self.assertEqual(conv.last_message_text, outbound_msg.content)

    def test_waha_webhook_deduplication(self):
        """Verifica que mensajes repetidos de WAHA no se dupliquen en base de datos"""
        waha_payload = {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "waha_unique_id_555",
                "timestamp": 1700000001,
                "from": "18095559999@c.us",
                "body": "Mensaje de prueba",
                "fromMe": False
            }
        }
        with patch('apps.whatsapp.services.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            WhatsAppService.process_waha_webhook(waha_payload)
            self.assertEqual(WhatsAppMessage.objects.filter(wamid="waha_unique_id_555").count(), 1)

            # Repetir el mismo evento
            WhatsAppService.process_waha_webhook(waha_payload)
            self.assertEqual(WhatsAppMessage.objects.filter(wamid="waha_unique_id_555").count(), 1)

    def test_waha_anti_ban_typing_simulation_and_sending(self):
        """Verifica que el servicio WAHA invoque sendSeen, startTyping, stopTyping y sendText"""
        with patch('apps.whatsapp.services.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'id': 'waha_msg_sent_777'}

            result = WAHAService.send_text_message(
                phone_number="8095551234",
                text="Su balance actual es RD$ 500.00",
                simulate_typing=True
            )
            self.assertTrue(result['success'])
            self.assertEqual(result['message_id'], 'waha_msg_sent_777')

            # Verificar que se llamaron los endpoints anti-baneo
            called_urls = [call[0][0] for call in mock_post.call_args_list]
            self.assertTrue(any('sendSeen' in u for u in called_urls), "Debe enviar sendSeen")
            self.assertTrue(any('startTyping' in u for u in called_urls), "Debe activar startTyping")
            self.assertTrue(any('stopTyping' in u for u in called_urls), "Debe llamar stopTyping")
            self.assertTrue(any('sendText' in u for u in called_urls), "Debe enviar sendText")

    def test_waha_status_ajax_view(self):
        """Verifica que el endpoint AJAX devuelva el estado de WAHA correctamente"""
        self.client.login(username='admin_test', password='Password123!')
        url = reverse('whatsapp_waha_status')
        with patch('apps.whatsapp.services.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = [
                {'name': 'default', 'status': 'WORKING'}
            ]
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['online'])
            self.assertEqual(data['status'], 'WORKING')

    # --- 14. Multi-Colmado y Gestión de Sucursales ---
    def test_multi_branch_creation_and_switching(self):
        """Verifica la creación de múltiples colmados y el cambio de sucursal activa en sesión"""
        ColmadoBranch.objects.all().delete()
        branch_1 = ColmadoBranch.objects.create(
            name="Colmado El Progreso Central",
            code="SUC-01",
            phone="8095550101",
            is_main=True,
            is_active=True
        )
        branch_2 = ColmadoBranch.objects.create(
            name="Colmado El Progreso #2 Villa Juana",
            code="SUC-02",
            phone="8095550202",
            is_main=False,
            is_active=True
        )

        self.assertEqual(ColmadoBranch.objects.filter(is_active=True).count(), 2)

        # Probar switch endpoint
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('branch_switch', kwargs={'pk': branch_2.id}))
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertEqual(session.get('active_branch_id'), branch_2.id)

    # --- 15. Notificaciones Automáticas de WhatsApp en Fiado y Abono ---
    def test_whatsapp_fiado_and_abono_notifications(self):
        """Verifica la generación y registro del mensaje de WhatsApp al fiar y abonar"""
        cliente_wa = Customer.objects.create(
            name="Doña Altagracia",
            phone="8295558899",
            credit_limit=Decimal('5000.00'),
            is_active=True
        )

        # 1. Crear una venta fiada
        sale = SaleService.create_sale(
            cashier=self.admin_user,
            items_data=[{'product_id': self.prod_arroz.id, 'quantity': Decimal('2.00')}],
            payments_data=[{'payment_method': PaymentMethodChoices.FIADO, 'amount': Decimal('90.00')}],
            customer_id=cliente_wa.id,
            cash_shift_id=self.shift.id
        )

        # Verificar mensaje saliente de WhatsApp para el fiado
        fiado_msg = WhatsAppMessage.objects.filter(conversation__contact__phone__icontains="8295558899").first()
        self.assertIsNotNone(fiado_msg)
        self.assertIn("Comprobante de Fiado", fiado_msg.content)
        self.assertIn("Monto total que debe", fiado_msg.content)

        # 2. Registrar un abono
        tx = CustomerCreditService.record_abono(
            customer_id=cliente_wa.id,
            amount=Decimal('50.00'),
            payment_method='EFECTIVO',
            user=self.admin_user
        )

        # Verificar mensaje saliente de WhatsApp para el abono
        abono_msgs = WhatsAppMessage.objects.filter(
            conversation__contact__phone__icontains="8295558899",
            content__icontains="Recibo de Abono"
        )
        self.assertTrue(abono_msgs.exists())
        self.assertIn("Monto abonado hoy", abono_msgs.first().content)

    # --- 16. Roles Personalizados y Permisos Granulares ---
    def test_custom_role_creation_and_inheritance(self):
        """Verifica la creación de un perfil personalizado y la herencia de permisos en el usuario"""
        role_cajero_noche = CustomRole.objects.create(
            name="Cajero Turno Noche Test",
            description="Cajero de mostrador sin permiso de descuentos ni anulación",
            can_access_pos=True,
            can_apply_discounts=False,
            can_void_sales=False,
            can_record_abono=True,
            can_view_reports=False
        )

        user = User.objects.create_user(username="cajero_noche", password="password123")
        profile = user.profile
        profile.custom_role = role_cajero_noche
        profile.save()

        # Comprobar herencia dinámica
        self.assertTrue(profile.has_perm('can_access_pos'))
        self.assertTrue(profile.has_perm('can_record_abono'))
        self.assertFalse(profile.has_perm('can_apply_discounts'))
        self.assertFalse(profile.has_perm('can_void_sales'))
        self.assertFalse(profile.has_perm('can_view_reports'))

    def test_user_individual_permission_override(self):
        """Verifica que un usuario pueda tener permisos personalizados que sobrescriben su rol"""
        role = CustomRole.objects.create(
            name="Cajero Base Test",
            can_access_pos=True,
            can_apply_discounts=False
        )
        user = User.objects.create_user(username="cajero_especial", password="password123")
        profile = user.profile
        profile.custom_role = role
        profile.override_role_permissions = True
        profile.can_apply_discounts = True  # Otorgado individualmente a esta persona
        profile.save()

        self.assertTrue(profile.has_perm('can_access_pos'))
        self.assertTrue(profile.has_perm('can_apply_discounts'))

    # --- 17. Aislamiento Multi-Colmado por Usuario ---
    def test_multi_branch_isolation_and_permission_protection(self):
        """Verifica que un usuario de un colmado NO pueda ver ni cambiarse al colmado de los demás"""
        ColmadoBranch.objects.all().delete()
        branch_a = ColmadoBranch.objects.create(name="Colmado A", code="SUC-A", is_main=True, is_active=True)
        branch_b = ColmadoBranch.objects.create(name="Colmado B", code="SUC-B", is_main=False, is_active=True)

        # Usuario normal asignado únicamente a Colmado A
        user_a = User.objects.create_user(username="empleado_a", password="password123")
        profile_a = user_a.profile
        profile_a.all_branches_access = False
        profile_a.assigned_branches.add(branch_a)
        profile_a.save()

        # Comprobación de acceso por método
        self.assertTrue(profile_a.can_access_branch(branch_a.id))
        self.assertFalse(profile_a.can_access_branch(branch_b.id))
        self.assertEqual(list(profile_a.get_allowed_branches()), [branch_a])

        # Intentar cambiarse a Colmado B por HTTP request debe ser bloqueado
        self.client.force_login(user_a)
        response = self.client.get(reverse('branch_switch', kwargs={'pk': branch_b.id}))
        # Redirige con error
        self.assertEqual(response.status_code, 302)
        # La sucursal en sesión NO debe ser branch_b
        self.assertNotEqual(self.client.session.get('active_branch_id'), branch_b.id)

        # Superadministrador sí puede cambiar a Colmado B
        self.client.force_login(self.admin_user)
        response_admin = self.client.get(reverse('branch_switch', kwargs={'pk': branch_b.id}))
        self.assertEqual(response_admin.status_code, 302)
        self.assertEqual(self.client.session.get('active_branch_id'), branch_b.id)

    # --- 18. Comandos Conversacionales y Acciones Rápidas de Libreta en WhatsApp ---
    def test_operator_credit_command_parser(self):
        """Verifica que el analizador de comandos de WhatsApp reconozca abonos y fiados con precisión"""
        # Abonos
        cmd_abono1 = WhatsAppService.parse_operator_credit_command("Abonar 500")
        self.assertIsNotNone(cmd_abono1)
        self.assertEqual(cmd_abono1['type'], 'ABONO')
        self.assertEqual(cmd_abono1['amount'], Decimal('500'))
        self.assertEqual(cmd_abono1['payment_method'], 'EFECTIVO')

        cmd_abono2 = WhatsAppService.parse_operator_credit_command("/abono 1000 transferencia ref 83748")
        self.assertIsNotNone(cmd_abono2)
        self.assertEqual(cmd_abono2['type'], 'ABONO')
        self.assertEqual(cmd_abono2['amount'], Decimal('1000'))
        self.assertEqual(cmd_abono2['payment_method'], 'TRANSFERENCIA')

        cmd_abono3 = WhatsAppService.parse_operator_credit_command("Pagar RD$ 350.50 en efectivo")
        self.assertIsNotNone(cmd_abono3)
        self.assertEqual(cmd_abono3['type'], 'ABONO')
        self.assertEqual(cmd_abono3['amount'], Decimal('350.50'))

        # Fiados / Cargos
        cmd_cargo1 = WhatsAppService.parse_operator_credit_command("Fiar 150 arroz y 3 sopitas")
        self.assertIsNotNone(cmd_cargo1)
        self.assertEqual(cmd_cargo1['type'], 'CARGO')
        self.assertEqual(cmd_cargo1['amount'], Decimal('150'))
        self.assertEqual(cmd_cargo1['notes'], 'arroz y 3 sopitas')

        cmd_cargo2 = WhatsAppService.parse_operator_credit_command("Añadir en la cuenta que debe 300 platanos maduros")
        self.assertIsNotNone(cmd_cargo2)
        self.assertEqual(cmd_cargo2['type'], 'CARGO')
        self.assertEqual(cmd_cargo2['amount'], Decimal('300'))
        self.assertEqual(cmd_cargo2['notes'], 'platanos maduros')

        cmd_cargo3 = WhatsAppService.parse_operator_credit_command("Debe 450")
        self.assertIsNotNone(cmd_cargo3)
        self.assertEqual(cmd_cargo3['type'], 'CARGO')
        self.assertEqual(cmd_cargo3['amount'], Decimal('450'))

        # Mensajes normales no deben disparar comandos
        self.assertIsNone(WhatsAppService.parse_operator_credit_command("Hola don Ramón, buenas tardes"))
        self.assertIsNone(WhatsAppService.parse_operator_credit_command("¿Tiene pan sobado disponible?"))

    def test_whatsapp_credit_action_modal_and_auto_registration(self):
        """Verifica que el modal registre abonos y cargos con auto-registro de clientes no registrados"""
        # Contacto no registrado en libreta
        contact = WhatsAppContact.objects.create(
            phone="18095551234",
            display_name="Doña Carmen Pérez"
        )
        conv = WhatsAppConversation.objects.create(contact=contact)

        self.client.force_login(self.admin_user)

        # 1. Cargar fiado a través de la acción rápida (auto-registra al cliente)
        url = reverse('whatsapp_credit_action', kwargs={'pk': conv.id})
        res = self.client.post(url, {
            'action_type': 'CARGO',
            'amount': '350.00',
            'notes': '2 libras de arroz y aceite',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['auto_registered'])
        self.assertEqual(Decimal(str(data['new_balance'])), Decimal('350.00'))

        contact.refresh_from_db()
        self.assertIsNotNone(contact.customer)
        self.assertEqual(contact.customer.current_balance, Decimal('350.00'))

        # 2. Abonar dinero a la cuenta del cliente recién creado
        res_abono = self.client.post(url, {
            'action_type': 'ABONO',
            'amount': '200.00',
            'payment_method': 'EFECTIVO',
            'notes': 'Abono en mostrador',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(res_abono.status_code, 200)
        data_abono = res_abono.json()
        self.assertTrue(data_abono['success'])
        self.assertEqual(Decimal(str(data_abono['new_balance'])), Decimal('150.00'))
        contact.customer.refresh_from_db()
        self.assertEqual(contact.customer.current_balance, Decimal('150.00'))

    def test_conversational_credit_command_via_chat_view(self):
        """Verifica que escribir 'Fiar 250' o 'Abonar 100' en el chat ejecute la libreta automáticamente"""
        contact = WhatsAppContact.objects.create(
            phone="18095559876",
            display_name="Juan El Vecino"
        )
        conv = WhatsAppConversation.objects.create(contact=contact)

        self.client.force_login(self.admin_user)
        send_url = reverse('whatsapp_send_message', kwargs={'pk': conv.id})

        # Escribir comando conversacional de fiado
        res_cargo = self.client.post(send_url, {
            'message_text': 'Fiar 400 salami y queso'
        })
        self.assertEqual(res_cargo.status_code, 302)
        contact.refresh_from_db()
        self.assertIsNotNone(contact.customer)
        self.assertEqual(contact.customer.current_balance, Decimal('400.00'))

        # Escribir comando conversacional de abono
        res_abono = self.client.post(send_url, {
            'message_text': 'Abonar 150 efectivo'
        })
        self.assertEqual(res_abono.status_code, 302)
        contact.customer.refresh_from_db()
        self.assertEqual(contact.customer.current_balance, Decimal('250.00'))

    def test_no_ai_icons_in_notifications_or_messages(self):
        """Verifica estrictamente que ningún mensaje o comprobante contenga íconos de IA (✨ o 🤖)"""
        customer = Customer.objects.create(
            name="Cliente Prueba Limpia",
            phone="18291112233",
            credit_limit=Decimal('5000.00')
        )
        summary = CustomerCreditService.generate_whatsapp_summary(customer)
        self.assertNotIn('✨', summary)
        self.assertNotIn('🤖', summary)
        self.assertNotIn('IA', summary)

    def test_shift_accounting_sales_reconciliation(self):
        """
        Verificación contable senior:
        Ventas Contado + Ventas Fiadas = Venta Total Bruta.
        Arqueo de Gaveta: Fondo Inicial + Ventas Efectivo + Abonos Efectivo - Gastos.
        """
        # 1. Venta de contado en efectivo por RD$ 370
        sale_contado = SaleService.create_sale(
            cashier=self.cajero_user,
            items_data=[{'product_id': self.prod_presidente.id, 'quantity': Decimal('2.00')}],
            payments_data=[{'payment_method': PaymentMethodChoices.EFECTIVO, 'amount': Decimal('370.00')}],
            cash_shift_id=self.shift.id
        )

        # 2. Venta fiada por RD$ 185
        sale_fiado = SaleService.create_sale(
            cashier=self.cajero_user,
            customer_id=self.cliente.id,
            items_data=[{'product_id': self.prod_presidente.id, 'quantity': Decimal('1.00')}],
            payments_data=[{'payment_method': PaymentMethodChoices.FIADO, 'amount': Decimal('185.00')}],
            cash_shift_id=self.shift.id
        )

        # 3. Abono de fiado en efectivo por RD$ 100
        CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('100.00'),
            payment_method='EFECTIVO',
            user=self.cajero_user,
            cash_shift_id=self.shift.id
        )

        # 4. Auditoría de conciliación
        audit = self.shift.get_sales_audit_summary()
        self.assertEqual(audit['cash_sales'], Decimal('370.00'))
        self.assertEqual(audit['fiado_sales'], Decimal('185.00'))
        self.assertEqual(audit['total_gross_sales'], Decimal('555.00'))
        # Ecuación dorada de venta: Contado + Fiado == Venta Total
        self.assertEqual(audit['contado_sales'] + audit['fiado_sales'], audit['total_gross_sales'])
        self.assertEqual(self.shift.total_sales, Decimal('555.00'))
        self.assertEqual(self.shift.fiado_sales, Decimal('185.00'))
        self.assertEqual(self.shift.contado_sales, Decimal('370.00'))

        # 5. Flujo de Gaveta: Fondo inicial (1,500) + Ventas Efectivo (370) + Abono (100) = 1,970
        self.assertEqual(audit['abonos_cash'], Decimal('100.00'))
        self.assertEqual(self.shift.calculate_current_expected_cash(), Decimal('1970.00'))

        # 6. Render de vistas de detalle y cierre
        self.client.force_login(self.admin_user)
        detail_url = reverse('cash_shift_detail', kwargs={'pk': self.shift.id})
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, 'Conciliación de Ventas del Turno')
        self.assertContains(res_detail, '555')
        self.assertContains(res_detail, '185')
        self.assertContains(res_detail, '370')


