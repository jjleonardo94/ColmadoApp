import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError

from apps.core.models import BusinessSettings, AuditLog
from apps.accounts.models import UserProfile, UserRole, CustomRole
from apps.catalog.models import Category, Product, UnitOfMeasure, SaleType
from apps.sales.models import (
    Sale, SaleItem, Payment, SaleStatus, PaymentMethodChoices,
    DeliveryPerson, DeliveryOrder, DeliveryStatus
)
from apps.sales.services import SaleService, DeliveryService
from apps.customers.models import Customer, CreditTransaction, CreditTransactionType
from apps.customers.services import CustomerCreditService
from apps.cash.models import CashRegister, CashShift, CashShiftStatus, CashMovement, CashDenomination
from apps.cash.services import CashService
from apps.whatsapp.models import WhatsAppContact, WhatsAppConversation, WhatsAppMessage
from apps.expenses.models import Expense, ExpenseCategory


class MasterUpgradeTestScenarios(TestCase):
    """
    Verificación estricta de los 10 escenarios obligatorios del Prompt Maestro:
    1. Venta de contado en efectivo desde WhatsApp.
    2. Venta por transferencia.
    3. Venta a crédito.
    4. Abonos (Efectivo, Transferencia, Tarjeta).
    5. Cliente sin nombre en WhatsApp.
    6. Delivery Express (Pedidos pendientes, asignación, despacho individual y masivo sin duplicación).
    7. Cierre de caja (Cálculo exacto de efectivo esperado, contado, diferencia y fondo retenido).
    8. Historial de cierres (Preservación inmutable mediante snapshots sellados).
    9. Reportes (Diferenciación estricta entre ventas y abonos).
    10. Seguridad y Permisos (Protección de configuración de caja y operaciones críticas).
    """

    def setUp(self):
        # 1. Configuración de Negocio
        self.settings = BusinessSettings.get_settings()
        self.settings.default_initial_cash = Decimal('1000.00')
        self.settings.default_closing_cash_fund = Decimal('1000.00')
        self.settings.save()

        # 2. Denominaciones para arqueo físico de caja
        self.denom_1000 = CashDenomination.objects.create(name='Billete 1000', value=Decimal('1000.00'), is_active=True)
        self.denom_500 = CashDenomination.objects.create(name='Billete 500', value=Decimal('500.00'), is_active=True)
        self.denom_100 = CashDenomination.objects.create(name='Billete 100', value=Decimal('100.00'), is_active=True)

        # 3. Usuarios
        self.admin = User.objects.create_user(username='admin_pos', password='Password123!', is_staff=True, is_superuser=True)
        self.admin.profile.role = UserRole.ADMIN
        self.admin.profile.can_manage_cash_settings = True
        self.admin.profile.can_authorize_cash_differences = True
        self.admin.profile.can_manage_deliveries = True
        self.admin.profile.can_authorize_credit = True
        self.admin.profile.save()

        self.cajero = User.objects.create_user(username='cajero_pos', password='Password123!')
        self.cajero.profile.role = UserRole.CAJERO
        self.cajero.profile.can_manage_cash_settings = False
        self.cajero.profile.can_authorize_cash_differences = False
        self.cajero.profile.can_authorize_credit = True
        self.cajero.profile.save()

        # 4. Caja y Turno
        self.register = CashRegister.objects.create(name='Caja Principal', is_active=True)
        self.shift = CashService.open_shift(
            register_id=self.register.id,
            cashier=self.cajero,
            initial_cash=Decimal('1000.00')
        )

        # 5. Catálogo
        self.cat = Category.objects.create(name='Provisiones')
        self.prod_arroz = Product.objects.create(
            name='Arroz Campo',
            internal_code='ARR01',
            category=self.cat,
            cost_price=Decimal('30.00'),
            sale_price=Decimal('40.00'),
            current_stock=Decimal('100.00'),
            sale_type=SaleType.FRACTION,
            unit_of_measure=UnitOfMeasure.LIBRA
        )
        self.prod_aceite = Product.objects.create(
            name='Aceite Crisol',
            internal_code='ACE01',
            category=self.cat,
            cost_price=Decimal('50.00'),
            sale_price=Decimal('75.00'),
            current_stock=Decimal('50.00'),
            sale_type=SaleType.UNIT,
            unit_of_measure=UnitOfMeasure.UNIDAD
        )

        # 6. Clientes (sin campo directo current_balance porque es una propiedad contable en tiempo real)
        self.cliente = Customer.objects.create(
            name='Juan Pérez',
            phone='+18095550101',
            credit_limit=Decimal('5000.00')
        )

        # 7. Repartidores
        self.repartidor = DeliveryPerson.objects.create(name='Carlos Motoconcho', phone='18095550999', is_active=True)

        self.client = Client()

    # ==============================================================
    # PRUEBA 1: Venta de contado en efectivo desde WhatsApp
    # ==============================================================
    @patch('apps.whatsapp.services.WhatsAppService.send_text_message')
    def test_01_venta_contado_efectivo_whatsapp(self, mock_send_wa):
        mock_send_wa.return_value = {'success': True}
        self.client.force_login(self.cajero)

        # Simular contacto y conversación existentes
        contact = WhatsAppContact.objects.create(phone='+18095550101', display_name='Juan Pérez', customer=self.cliente)
        conv = WhatsAppConversation.objects.create(contact=contact)

        # Llamar al endpoint de creación de venta desde el chat
        response = self.client.post(
            reverse('whatsapp_create_sale', args=[conv.id]),
            data=json.dumps({
                'sale_type': 'CONTADO',
                'payment_method': 'EFECTIVO',
                'amount': '150.00',
                'destination_type': 'DIRECTO',
                'notes': '2 lbs de arroz y 1 aceite',
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

        ticket = data.get('ticket_number')
        sale = Sale.objects.get(ticket_number=ticket)
        self.assertEqual(sale.total, Decimal('150.00'))
        self.assertEqual(sale.origin, 'WHATSAPP')
        self.assertEqual(sale.payment_method, PaymentMethodChoices.EFECTIVO)

        # Verificar que solo exista UNA venta registrada
        self.assertEqual(Sale.objects.filter(ticket_number=ticket).count(), 1)

        # Verificar que el efectivo ingresó al turno de caja abierto
        summary = self.shift.get_sales_audit_summary()
        self.assertEqual(summary['cash_sales'], Decimal('150.00'))
        self.assertEqual(summary['expected_cash'], Decimal('1150.00'))  # 1000 inicial + 150 venta

    # ==============================================================
    # PRUEBA 2: Venta por transferencia
    # ==============================================================
    def test_02_venta_por_transferencia_no_aumenta_efectivo_fisico(self):
        items_data = [{'product_id': self.prod_aceite.id, 'quantity': 2, 'unit_price': Decimal('75.00')}]
        payments_data = [{'method': PaymentMethodChoices.TRANSFERENCIA, 'amount': Decimal('150.00'), 'reference': 'TRANS-9988'}]

        sale = SaleService.create_sale(
            cashier=self.cajero,
            items_data=items_data,
            payments_data=payments_data,
            customer_id=self.cliente.id,
            origin='POS'
        )

        self.assertEqual(sale.total, Decimal('150.00'))

        # Comprobar que NO aumentó el efectivo físico esperado en el turno
        summary = self.shift.get_sales_audit_summary()
        self.assertEqual(summary['transfer_sales'], Decimal('150.00'))
        self.assertEqual(summary['cash_sales'], Decimal('0.00'))
        self.assertEqual(summary['expected_cash'], Decimal('1000.00'))  # Sigue en el fondo inicial

    # ==============================================================
    # PRUEBA 3: Venta a crédito
    # ==============================================================
    def test_03_venta_a_credito_actualiza_cxc_sin_aumentar_efectivo(self):
        items_data = [{'product_id': self.prod_arroz.id, 'quantity': 5, 'unit_price': Decimal('40.00')}]
        payments_data = [{'method': PaymentMethodChoices.FIADO, 'amount': Decimal('200.00')}]

        sale = SaleService.create_sale(
            cashier=self.cajero,
            items_data=items_data,
            payments_data=payments_data,
            customer_id=self.cliente.id,
            origin='POS'
        )

        self.assertEqual(sale.total, Decimal('200.00'))

        # Comprobar saldo deudor del cliente actualizado
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.current_balance, Decimal('200.00'))

        # Comprobar que NO aumentó el efectivo físico esperado
        summary = self.shift.get_sales_audit_summary()
        self.assertEqual(summary['credit_sales'], Decimal('200.00'))
        self.assertEqual(summary['cash_sales'], Decimal('0.00'))
        self.assertEqual(summary['expected_cash'], Decimal('1000.00'))

    # ==============================================================
    # PRUEBA 4: Tres abonos (Efectivo, Transferencia, Tarjeta)
    # ==============================================================
    def test_04_tres_abonos_metodos_distintos_y_saldos(self):
        # Crear cargo inicial legítimo de RD$ 1,000 mediante CreditTransaction
        CreditTransaction.objects.create(
            customer=self.cliente,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=Decimal('1000.00'),
            balance_after=Decimal('1000.00'),
            payment_method='FIADO',
            user=self.cajero,
            notes='Cargo a crédito inicial de prueba'
        )
        self.assertEqual(self.cliente.current_balance, Decimal('1000.00'))

        # Abono 1: RD$ 200 en Efectivo
        t1 = CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('200.00'),
            payment_method='EFECTIVO',
            user=self.cajero,
            cash_shift_id=self.shift.id,
            reference='Recibo #1'
        )
        self.assertEqual(self.cliente.current_balance, Decimal('800.00'))

        # Abono 2: RD$ 300 por Transferencia
        t2 = CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('300.00'),
            payment_method='TRANSFERENCIA',
            user=self.cajero,
            cash_shift_id=self.shift.id,
            reference='Transf #7788'
        )
        self.assertEqual(self.cliente.current_balance, Decimal('500.00'))

        # Abono 3: RD$ 150 con Tarjeta
        t3 = CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('150.00'),
            payment_method='TARJETA',
            user=self.cajero,
            cash_shift_id=self.shift.id,
            reference='Autoriz #5412'
        )
        self.assertEqual(self.cliente.current_balance, Decimal('350.00'))

        # Validar impacto en cierre de caja:
        # Solo el abono en efectivo debe incrementar el efectivo de caja
        summary = self.shift.get_sales_audit_summary()
        self.assertEqual(summary['abonos_cash'], Decimal('200.00'))
        self.assertEqual(summary['abonos_transfer'], Decimal('300.00'))
        self.assertEqual(summary['abonos_card'], Decimal('150.00'))
        self.assertEqual(summary['total_abonos'], Decimal('650.00'))
        # Efectivo esperado = 1000 inicial + 200 abono efectivo = 1200
        self.assertEqual(summary['expected_cash'], Decimal('1200.00'))

        # Validar que no permita abonar más de la deuda restante (RD$ 350)
        with self.assertRaises(ValidationError):
            CustomerCreditService.record_abono(
                customer_id=self.cliente.id,
                amount=Decimal('500.00'),
                payment_method='EFECTIVO',
                user=self.cajero
            )

    # ==============================================================
    # PRUEBA 5: Cliente sin nombre en WhatsApp
    # ==============================================================
    def test_05_cliente_sin_nombre_whatsapp_registro(self):
        self.client.force_login(self.cajero)

        # Contacto sin nombre previamente guardado
        contact = WhatsAppContact.objects.create(
            phone='+18299998877',
            display_name='',
            customer=None
        )
        conv = WhatsAppConversation.objects.create(contact=contact)

        # Registrar nombre desde WhatsApp
        response = self.client.post(reverse('whatsapp_register_customer', args=[conv.id]), {
            'name': 'Doña Rosa Almonte',
            'phone': '18299998877',
            'alias': 'Colmado la 40',
            'address': 'Calle 5ta esquina Central'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

        # Verificar persistencia y vínculo
        customer = Customer.objects.get(phone='+18299998877')
        self.assertEqual(customer.name, 'Doña Rosa Almonte')
        contact.refresh_from_db()
        self.assertEqual(contact.customer, customer)
        self.assertEqual(contact.display_name, 'Doña Rosa Almonte')

        # Intentar registrar de nuevo con mismo número no duplica el registro
        cust_again = CustomerCreditService.register_or_link_whatsapp_customer(
            contact_id=contact.id,
            name='Doña Rosa',
            phone='18299998877'
        )
        self.assertEqual(cust_again.id, customer.id)
        self.assertEqual(Customer.objects.filter(phone='+18299998877').count(), 1)

    # ==============================================================
    # PRUEBA 6: Delivery Express (3 pedidos, despacho individual y masivo)
    # ==============================================================
    @patch('apps.whatsapp.services.WhatsAppService.send_text_message')
    def test_06_delivery_express_despacho_individual_y_masivo(self, mock_send_wa):
        mock_send_wa.return_value = {'success': True}
        self.client.force_login(self.cajero)

        # Crear 3 ventas
        sales = []
        for i in range(1, 4):
            s = Sale.objects.create(
                ticket_number=f'TICK-DELIV-{i}',
                cashier=self.cajero,
                customer=self.cliente,
                cash_shift=self.shift,
                origin='DELIVERY',
                total=Decimal(f'{i * 100}.00')
            )
            # Agregar a Delivery Express
            DeliveryService.create_delivery_order(
                sale=s,
                destination_type='EXPRESS',
                delivery_person_id=self.repartidor.id,
                delivery_address=f'Calle {i}',
                user=self.cajero
            )
            sales.append(s)

        # 1. Comprobar que el contador muestra 3 pedidos pendientes
        pending_qs = DeliveryService.get_pending_orders()
        self.assertEqual(pending_qs.count(), 3)

        api_res = self.client.get(reverse('delivery_express_pending'))
        self.assertEqual(api_res.json()['count'], 3)

        # 2. Despachar 1 pedido individualmente
        order_1 = pending_qs.first()
        dispatch_res = self.client.post(reverse('delivery_express_dispatch', args=[order_1.id]))
        self.assertTrue(dispatch_res.json().get('success'))

        order_1.refresh_from_db()
        self.assertEqual(order_1.status, DeliveryStatus.EN_CAMINO)
        self.assertIsNotNone(order_1.dispatched_at)

        # Verificar contador ahora es 2
        self.assertEqual(DeliveryService.get_pending_orders().count(), 2)

        # 3. Despachar todos los pedidos restantes (masivo)
        bulk_res = self.client.post(reverse('delivery_express_dispatch_all'))
        self.assertTrue(bulk_res.json()['success'])
        self.assertEqual(bulk_res.json()['dispatched_count'], 2)

        # Verificar que ya no quedan pedidos pendientes
        self.assertEqual(DeliveryService.get_pending_orders().count(), 0)

        # Verificar que NO se crearon ventas duplicadas (sigue habiendo exactamente 3 ventas)
        self.assertEqual(Sale.objects.filter(ticket_number__startswith='TICK-DELIV-').count(), 3)

    # ==============================================================
    # PRUEBA 7: Cierre de caja (Cálculo exacto, diferencia y fondo retenido)
    # ==============================================================
    def test_07_cierre_de_caja_calculo_y_fondo_retenido(self):
        # 1. Venta de contado efectivo: RD$ 500
        Sale.objects.create(
            ticket_number='TICK-CASH-1',
            cashier=self.cajero,
            cash_shift=self.shift,
            total=Decimal('500.00'),
            payment_method=PaymentMethodChoices.EFECTIVO
        )
        CashMovement.objects.create(shift=self.shift, movement_type='INGRESO', amount=Decimal('500.00'), user=self.cajero)

        # 2. Abono en efectivo: RD$ 200 (primero creamos cargo para tener balance que abonar)
        CreditTransaction.objects.create(
            customer=self.cliente,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=Decimal('500.00'),
            balance_after=Decimal('500.00'),
            payment_method='FIADO',
            user=self.cajero
        )
        CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('200.00'),
            payment_method='EFECTIVO',
            user=self.cajero,
            cash_shift_id=self.shift.id,
            reference='Abono Efectivo'
        )

        # 3. Gasto en efectivo: RD$ 100
        cat_exp = ExpenseCategory.objects.create(name='Limpieza')
        Expense.objects.create(
            category=cat_exp,
            description='Bolsas plásticas',
            amount=Decimal('100.00'),
            date=timezone.localdate(),
            payment_method='EFECTIVO',
            is_paid=True
        )
        CashMovement.objects.create(shift=self.shift, movement_type='EGRESO', amount=Decimal('100.00'), user=self.cajero)

        # Efectivo esperado = 1000 (inicial) + 500 (venta ef) + 200 (abono ef) - 100 (gasto ef) = 1600.00
        summary = self.shift.get_sales_audit_summary()
        self.assertEqual(summary['expected_cash'], Decimal('1600.00'))

        # Si el cajero cuenta físicamente RD$ 1,600 (sin diferencia)
        # y se configuran RD$ 1,000 para permanecer en caja -> importe retirado = 600.00
        closed_shift = CashService.close_shift(
            shift_id=self.shift.id,
            user=self.cajero,
            denomination_counts={
                self.denom_1000.id: 1,
                self.denom_500.id: 1,
                self.denom_100.id: 1,
            },
            closing_notes='Cierre cuadrado perfecto',
            cash_to_remain=Decimal('1000.00')
        )

        self.assertEqual(closed_shift.status, CashShiftStatus.CERRADO)
        self.assertEqual(closed_shift.difference, Decimal('0.00'))
        self.assertEqual(closed_shift.cash_to_remain, Decimal('1000.00'))
        self.assertEqual(closed_shift.amount_withdrawn, Decimal('600.00'))
        self.assertTrue(closed_shift.is_snapshot_sealed)

    # ==============================================================
    # PRUEBA 8: Historial de cierres inmutable
    # ==============================================================
    def test_08_historial_cierres_inmutable_tras_nuevas_operaciones(self):
        # Cerrar el turno actual con snapshot sellado
        closed_shift = CashService.close_shift(
            shift_id=self.shift.id,
            user=self.cajero,
            denomination_counts={self.denom_1000.id: 1},
            closing_notes='Primer Cierre'
        )
        expected_cash_val = closed_shift.expected_cash
        self.assertEqual(expected_cash_val, Decimal('1000.00'))

        # Abrir un nuevo turno
        new_shift = CashService.open_shift(register_id=self.register.id, cashier=self.cajero, initial_cash=Decimal('1000.00'))

        # Registrar nuevas ventas en el nuevo turno
        Sale.objects.create(
            ticket_number='TICK-NEW-SHIFT',
            cashier=self.cajero,
            cash_shift=new_shift,
            total=Decimal('5000.00'),
            payment_method=PaymentMethodChoices.EFECTIVO
        )

        # Comprobar que el cierre anterior NO cambió sus valores guardados
        closed_shift.refresh_from_db()
        self.assertEqual(closed_shift.expected_cash, expected_cash_val)
        self.assertEqual(closed_shift.counted_cash, Decimal('1000.00'))

    # ==============================================================
    # PRUEBA 9: Reportes (Comparación y consistencia real)
    # ==============================================================
    def test_09_reportes_separan_ventas_y_abonos_correctamente(self):
        self.client.force_login(self.cajero)

        # 1 Venta contado efectivo: RD$ 300
        Sale.objects.create(
            ticket_number='TICK-REP-1',
            cashier=self.cajero,
            cash_shift=self.shift,
            total=Decimal('300.00'),
            subtotal=Decimal('300.00'),
            status=SaleStatus.COMPLETADA,
            payment_method=PaymentMethodChoices.EFECTIVO
        )

        # 1 Venta crédito: RD$ 400
        Sale.objects.create(
            ticket_number='TICK-REP-2',
            cashier=self.cajero,
            customer=self.cliente,
            cash_shift=self.shift,
            total=Decimal('400.00'),
            subtotal=Decimal('400.00'),
            status=SaleStatus.COMPLETADA,
            payment_method=PaymentMethodChoices.FIADO
        )

        # 1 Abono CxC: RD$ 250 (primero creamos cargo para tener balance que abonar)
        CreditTransaction.objects.create(
            customer=self.cliente,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=Decimal('500.00'),
            balance_after=Decimal('500.00'),
            payment_method='FIADO',
            user=self.cajero
        )
        CustomerCreditService.record_abono(
            customer_id=self.cliente.id,
            amount=Decimal('250.00'),
            payment_method='EFECTIVO',
            user=self.cajero,
            cash_shift_id=self.shift.id,
            reference='Abono Reporte'
        )

        # Consultar la vista de reporte
        response = self.client.get(reverse('sales_report'))
        self.assertEqual(response.status_code, 200)

        # Validar métricas en el contexto
        ctx = response.context
        self.assertEqual(ctx['total_sold'], Decimal('700.00'))      # 300 + 400
        self.assertEqual(ctx['total_contado'], Decimal('300.00'))   # Solo contado
        self.assertEqual(ctx['total_credito'], Decimal('400.00'))   # Solo crédito
        self.assertEqual(ctx['total_abonos'], Decimal('250.00'))    # Abono separado

        # Verificar que el abono NO fue sumado al total vendido
        self.assertNotEqual(ctx['total_sold'], Decimal('950.00'))

    # ==============================================================
    # PRUEBA 10: Permisos y Seguridad en backend
    # ==============================================================
    def test_10_permisos_usuario_no_autorizado_rechazado(self):
        # 1. El cajero normal NO tiene permiso can_manage_cash_settings
        self.client.force_login(self.cajero)
        response_settings = self.client.post(reverse('business_settings'), {
            'name': 'Colmado Test',
            'usd_rate': '58.50',
            'eur_rate': '63.00',
            'low_stock_threshold': '5',
            'printer_width': '80mm',
            'default_initial_cash': '9999.00',
            'default_closing_cash_fund': '9999.00'
        })
        # Debe ser redirigido con error y la configuración no debe alterarse
        self.settings.refresh_from_db()
        self.assertNotEqual(self.settings.default_initial_cash, Decimal('9999.00'))

        # 2. Con usuario Admin con permiso sí se permite
        self.client.force_login(self.admin)
        response_admin_settings = self.client.post(reverse('business_settings'), {
            'name': 'Colmado Test',
            'usd_rate': '58.50',
            'eur_rate': '63.00',
            'low_stock_threshold': '5',
            'printer_width': '80mm',
            'default_initial_cash': '1500.00',
            'default_closing_cash_fund': '1500.00',
            'delivery_notification_template': 'Hola {cliente}, su pedido {ticket} va en camino.'
        })
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.default_initial_cash, Decimal('1500.00'))
