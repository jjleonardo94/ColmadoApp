from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class CashRegister(models.Model):
    name = models.CharField('Nombre de la Caja', max_length=100, default='Caja Principal')
    code = models.CharField('Código Interno', max_length=30, unique=True, default='CAJA-01')
    is_active = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Caja Física'
        verbose_name_plural = 'Cajas Físicas'

    def __str__(self):
        return f"{self.name} ({self.code})"


class CashDenominationType(models.TextChoices):
    BILLETE = 'BILLETE', 'Billete'
    MONEDA = 'MONEDA', 'Moneda'


class CashDenomination(models.Model):
    name = models.CharField('Denominación', max_length=50)
    value = models.DecimalField('Valor Facial (RD$)', max_digits=10, decimal_places=2)
    denomination_type = models.CharField('Tipo', max_length=10, choices=CashDenominationType.choices)
    is_active = models.BooleanField('Vigente en Catálogo', default=True)
    sort_order = models.PositiveIntegerField('Orden de Presentación', default=0)

    class Meta:
        verbose_name = 'Denominación Monetaria RD$'
        verbose_name_plural = 'Catálogo de Denominaciones RD$'
        ordering = ['-value']
        unique_together = ('value', 'denomination_type')

    def __str__(self):
        return f"RD$ {self.value:,.0f} ({self.get_denomination_type_display()})"


class CashShiftStatus(models.TextChoices):
    ABIERTO = 'ABIERTO', 'Turno Abierto'
    CERRADO = 'CERRADO', 'Turno Cerrado'


class CashShift(models.Model):
    branch = models.ForeignKey('core.ColmadoBranch', on_delete=models.SET_NULL, null=True, blank=True, related_name='shifts', verbose_name='Colmado / Sucursal')
    register = models.ForeignKey(CashRegister, on_delete=models.PROTECT, related_name='shifts', verbose_name='Caja Física')
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cashier_shifts', verbose_name='Cajero')
    opened_at = models.DateTimeField('Apertura', auto_now_add=True)
    closed_at = models.DateTimeField('Cierre', null=True, blank=True)
    
    initial_cash = models.DecimalField('Fondo Inicial de Caja (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField('Estado del Turno', max_length=15, choices=CashShiftStatus.choices, default=CashShiftStatus.ABIERTO)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_shifts', verbose_name='Cerrado Por')
    
    # Cifras de Cierre (Calculadas e Inmutables tras cierre)
    expected_cash = models.DecimalField('Efectivo Esperado en Gaveta (RD$)', max_digits=12, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField('Efectivo Contado Físicamente (RD$)', max_digits=12, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField('Diferencia (Sobrante / Faltante)', max_digits=12, decimal_places=2, null=True, blank=True)
    difference_explanation = models.TextField('Explicación Obligatoria de Diferencia', blank=True)
    difference_authorized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='authorized_shift_differences', verbose_name='Diferencia Autorizada Por')
    
    # Fondos al Cierre y Retiros
    cash_to_remain = models.DecimalField('Fondo Fijo que Permanece en Caja (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    amount_withdrawn = models.DecimalField('Importe Retirado de Caja (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    is_snapshot_sealed = models.BooleanField('Cierre Sellado Histórico Inmutable', default=False)
    
    # Snapshot Histórico Congelado de Operaciones
    snapshot_credit_sales = models.DecimalField('Snapshot Venta Crédito (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_transfer_sales = models.DecimalField('Snapshot Ventas Transferencia (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_card_sales = models.DecimalField('Snapshot Ventas Tarjeta (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_cash_sales = models.DecimalField('Snapshot Ventas Efectivo (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_cash_abonos = models.DecimalField('Snapshot Abonos Efectivo (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_transfer_abonos = models.DecimalField('Snapshot Abonos Transferencia (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_card_abonos = models.DecimalField('Snapshot Abonos Tarjeta (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    snapshot_expenses = models.DecimalField('Snapshot Gastos Efectivo (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    initial_notes = models.TextField('Observaciones de Apertura', blank=True)
    closing_notes = models.TextField('Observaciones de Cierre', blank=True)

    class Meta:
        verbose_name = 'Cierre de Caja'
        verbose_name_plural = 'Cierres de Caja'
        ordering = ['-opened_at']

    def __str__(self):
        status_lbl = self.get_status_display()
        return f"Turno #{self.id} | {self.cashier.username} | {self.opened_at.strftime('%d/%m/%Y %H:%M')} [{status_lbl}]"

    def calculate_current_expected_cash(self) -> Decimal:
        """
        Calcula el efectivo que debería haber en gaveta en tiempo real:
        Fondo Inicial + Ventas en Efectivo + Abonos de Fiados en Efectivo - Gastos Pagados en Efectivo - Devoluciones en Efectivo
        """
        movements = self.cash_movements.all()
        incomes = sum(m.amount for m in movements if m.movement_type == 'INGRESO' and m.category != 'FONDO_INICIAL')
        expenses = sum(m.amount for m in movements if m.movement_type == 'EGRESO')
        return Decimal(self.initial_cash + incomes - expenses)

    @property
    def total_expenses(self) -> Decimal:
        return sum(e.amount for e in self.shift_expenses.all())

    @property
    def movements(self):
        return self.cash_movements

    @property
    def difference_abs(self) -> Decimal:
        if self.difference is not None:
            return abs(self.difference)
        return Decimal('0.00')

    def get_sales_audit_summary(self):
        """
        Retorna la conciliación contable integral del turno:
        - Ventas Contado (Efectivo, Tarjeta, Transferencia)
        - Ventas Fiadas (Crédito en libreta)
        - Total Ventas Brutas (Contado + Fiado)
        - Cobros y Abonos en Efectivo
        - Salidas / Gastos en Efectivo
        - Movimiento Neto de Cartera de Fiados
        """
        completed_sales = self.shift_sales.filter(status='COMPLETADA').prefetch_related('payments')
        
        breakdown = {
            'EFECTIVO': Decimal('0.00'),
            'TARJETA': Decimal('0.00'),
            'TRANSFERENCIA': Decimal('0.00'),
            'FIADO': Decimal('0.00'),
            'OTRO': Decimal('0.00'),
        }
        
        total_gross = Decimal('0.00')
        total_discount = Decimal('0.00')
        sales_count = 0

        for sale in completed_sales:
            sales_count += 1
            total_gross += sale.total
            total_discount += sale.discount
            
            if sale.payments.exists():
                for p in sale.payments.all():
                    method = p.payment_method
                    if method in breakdown:
                        breakdown[method] += p.amount
                    else:
                        breakdown['OTRO'] += p.amount
            else:
                method = sale.payment_method
                if method in breakdown:
                    breakdown[method] += sale.total
                else:
                    breakdown['OTRO'] += sale.total

        cash_sales = breakdown['EFECTIVO']
        card_sales = breakdown['TARJETA']
        transfer_sales = breakdown['TRANSFERENCIA']
        fiado_sales = breakdown['FIADO']
        electronic_sales = card_sales + transfer_sales
        contado_sales = cash_sales + electronic_sales + breakdown['OTRO']

        # Abonos de crédito recibidos en el turno
        credit_abonos = self.credit_payments.filter(transaction_type='ABONO_PAGO')
        abonos_cash = sum(
            (tx.amount for tx in credit_abonos if tx.payment_method == 'EFECTIVO'),
            Decimal('0.00')
        )
        abonos_transfer = sum(
            (tx.amount for tx in credit_abonos if tx.payment_method == 'TRANSFERENCIA'),
            Decimal('0.00')
        )
        abonos_card = sum(
            (tx.amount for tx in credit_abonos if tx.payment_method == 'TARJETA'),
            Decimal('0.00')
        )
        abonos_other = sum(
            (tx.amount for tx in credit_abonos if tx.payment_method not in ['EFECTIVO', 'TRANSFERENCIA', 'TARJETA']),
            Decimal('0.00')
        )
        total_abonos = abonos_cash + abonos_transfer + abonos_card + abonos_other

        # Gastos / Salidas en Efectivo
        cash_expenses = sum(
            (m.amount for m in self.cash_movements.filter(movement_type='EGRESO')),
            Decimal('0.00')
        )

        initial_cash = self.initial_cash or Decimal('0.00')
        expected_cash = initial_cash + cash_sales + abonos_cash - cash_expenses
        net_credit_change = fiado_sales - total_abonos

        # Si el turno ya fue sellado, priorizar snapshot inmutable
        if self.is_snapshot_sealed:
            credit_s = self.snapshot_credit_sales
            transfer_s = self.snapshot_transfer_sales
            card_s = self.snapshot_card_sales
            cash_s = self.snapshot_cash_sales
            cash_ab = self.snapshot_cash_abonos
            transfer_ab = self.snapshot_transfer_abonos
            card_ab = self.snapshot_card_abonos
            exp = self.snapshot_expenses
        else:
            credit_s = fiado_sales
            transfer_s = transfer_sales
            card_s = card_sales
            cash_s = cash_sales
            cash_ab = abonos_cash
            transfer_ab = abonos_transfer
            card_ab = abonos_card
            exp = cash_expenses

        return {
            'sales_count': sales_count,
            'cash_sales': cash_s,
            'card_sales': card_s,
            'transfer_sales': transfer_s,
            'electronic_sales': card_s + transfer_s,
            'fiado_sales': credit_s,
            'credit_sales': credit_s,
            'other_sales': breakdown['OTRO'],
            'contado_sales': cash_s + card_s + transfer_s + breakdown['OTRO'],
            'total_gross_sales': total_gross,
            'total_discount': total_discount,
            'net_sales': total_gross - total_discount,
            'abonos_cash': cash_ab,
            'abonos_transfer': transfer_ab,
            'abonos_card': card_ab,
            'abonos_other': abonos_other,
            'total_abonos': cash_ab + transfer_ab + card_ab + abonos_other,
            'total_transfers': transfer_s + transfer_ab,
            'total_cards': card_s + card_ab,
            'total_cash_inflow': cash_s + cash_ab,
            'cash_expenses': exp,
            'initial_cash': initial_cash,
            'expected_cash': self.expected_cash if self.expected_cash is not None else expected_cash,
            'net_credit_change': net_credit_change,
        }

    def get_credit_sales_detail(self):
        """Detalle de ventas a crédito para desglose en modal/cierre"""
        sales = self.shift_sales.filter(
            status='COMPLETADA'
        ).filter(
            models.Q(payment_method='FIADO') | models.Q(payments__payment_method='FIADO')
        ).distinct().select_related('customer', 'cashier').prefetch_related('items__product')
        
        detail = []
        for s in sales:
            credit_amount = sum(
                p.amount for p in s.payments.filter(payment_method='FIADO')
            ) if s.payments.exists() else s.total
            detail.append({
                'sale_id': s.id,
                'ticket_number': s.ticket_number,
                'created_at': s.created_at,
                'customer_name': s.customer.name if s.customer else 'Consumidor Final',
                'customer_phone': s.customer.phone if s.customer else '',
                'customer_balance': s.customer.current_balance if s.customer else Decimal('0.00'),
                'credit_amount': credit_amount,
                'total_sale': s.total,
                'cashier': s.cashier.username,
                'items_summary': ", ".join([f"{it.quantity:g}x {it.product.name}" for it in s.items.all()]),
                'items_count': s.items.count(),
            })
        return detail

    def get_transfer_operations_detail(self):
        """Detalle de operaciones por transferencia: ventas y abonos claramente separados"""
        detail = []
        # Ventas por transferencia
        sales = self.shift_sales.filter(
            status='COMPLETADA'
        ).filter(
            models.Q(payment_method='TRANSFERENCIA') | models.Q(payments__payment_method='TRANSFERENCIA')
        ).distinct().select_related('customer', 'cashier').prefetch_related('payments')
        for s in sales:
            ref = ""
            amount = Decimal('0.00')
            if s.payments.exists():
                for p in s.payments.filter(payment_method='TRANSFERENCIA'):
                    amount += p.amount
                    if p.reference:
                        ref = p.reference
            else:
                amount = s.total
            detail.append({
                'type': 'VENTA',
                'type_label': 'Venta Contado',
                'ticket': s.ticket_number,
                'client': s.customer.name if s.customer else 'Consumidor Final',
                'amount': amount,
                'reference': ref or 'N/A',
                'user': s.cashier.username,
                'created_at': s.created_at,
            })
        # Abonos por transferencia
        abonos = self.credit_payments.filter(
            transaction_type='ABONO_PAGO',
            payment_method='TRANSFERENCIA'
        ).select_related('customer', 'user', 'sale')
        for ab in abonos:
            detail.append({
                'type': 'ABONO',
                'type_label': 'Abono CxC',
                'ticket': ab.sale.ticket_number if ab.sale else f"Abono #{ab.id}",
                'client': ab.customer.name,
                'amount': ab.amount,
                'reference': ab.reference or 'N/A',
                'user': ab.user.username if ab.user else 'Sistema',
                'created_at': ab.created_at,
            })
        detail.sort(key=lambda x: x['created_at'], reverse=True)
        return detail

    def get_cash_operations_detail(self):
        """Detalle de operaciones en efectivo: ventas y abonos claramente separados"""
        detail = []
        # Ventas en efectivo
        sales = self.shift_sales.filter(
            status='COMPLETADA'
        ).filter(
            models.Q(payment_method='EFECTIVO') | models.Q(payments__payment_method='EFECTIVO')
        ).distinct().select_related('customer', 'cashier').prefetch_related('payments')
        for s in sales:
            amount = Decimal('0.00')
            if s.payments.exists():
                for p in s.payments.filter(payment_method='EFECTIVO'):
                    amount += p.amount
            else:
                amount = s.total
            detail.append({
                'type': 'VENTA',
                'type_label': 'Venta Efectivo',
                'ticket': s.ticket_number,
                'client': s.customer.name if s.customer else 'Consumidor Final',
                'amount': amount,
                'user': s.cashier.username,
                'created_at': s.created_at,
            })
        # Abonos en efectivo
        abonos = self.credit_payments.filter(
            transaction_type='ABONO_PAGO',
            payment_method='EFECTIVO'
        ).select_related('customer', 'user', 'sale')
        for ab in abonos:
            detail.append({
                'type': 'ABONO',
                'type_label': 'Abono CxC Efectivo',
                'ticket': ab.sale.ticket_number if ab.sale else f"Abono #{ab.id}",
                'client': ab.customer.name,
                'amount': ab.amount,
                'user': ab.user.username if ab.user else 'Sistema',
                'created_at': ab.created_at,
            })
        detail.sort(key=lambda x: x['created_at'], reverse=True)
        return detail

    def get_card_operations_detail(self):
        """Detalle de operaciones con tarjeta: ventas y abonos"""
        detail = []
        sales = self.shift_sales.filter(
            status='COMPLETADA'
        ).filter(
            models.Q(payment_method='TARJETA') | models.Q(payments__payment_method='TARJETA')
        ).distinct().select_related('customer', 'cashier').prefetch_related('payments')
        for s in sales:
            ref = ""
            amount = Decimal('0.00')
            if s.payments.exists():
                for p in s.payments.filter(payment_method='TARJETA'):
                    amount += p.amount
                    if p.reference:
                        ref = p.reference
            else:
                amount = s.total
            detail.append({
                'type': 'VENTA',
                'type_label': 'Venta con Tarjeta',
                'ticket': s.ticket_number,
                'client': s.customer.name if s.customer else 'Consumidor Final',
                'amount': amount,
                'reference': ref or 'N/A',
                'user': s.cashier.username,
                'created_at': s.created_at,
            })
        abonos = self.credit_payments.filter(
            transaction_type='ABONO_PAGO',
            payment_method='TARJETA'
        ).select_related('customer', 'user', 'sale')
        for ab in abonos:
            detail.append({
                'type': 'ABONO',
                'type_label': 'Abono CxC con Tarjeta',
                'ticket': ab.sale.ticket_number if ab.sale else f"Abono #{ab.id}",
                'client': ab.customer.name,
                'amount': ab.amount,
                'reference': ab.reference or 'N/A',
                'user': ab.user.username if ab.user else 'Sistema',
                'created_at': ab.created_at,
            })
        detail.sort(key=lambda x: x['created_at'], reverse=True)
        return detail

    def get_abonos_detail(self):
        """Detalle de todos los abonos a CxC en el turno"""
        abonos = self.credit_payments.filter(
            transaction_type='ABONO_PAGO'
        ).select_related('customer', 'user', 'sale').order_by('-created_at')
        detail = []
        for ab in abonos:
            balance_before = ab.balance_after + ab.amount
            detail.append({
                'id': ab.id,
                'client': ab.customer.name,
                'phone': ab.customer.phone,
                'account': ab.sale.ticket_number if ab.sale else 'Cuenta Abierta',
                'created_at': ab.created_at,
                'amount': ab.amount,
                'payment_method': ab.payment_method,
                'balance_before': balance_before,
                'balance_after': ab.balance_after,
                'reference': ab.reference or 'N/A',
                'user': ab.user.username if ab.user else 'Sistema',
            })
        return detail

    @property
    def total_sales(self) -> Decimal:
        return self.get_sales_audit_summary()['total_gross_sales']

    @property
    def fiado_sales(self) -> Decimal:
        return self.get_sales_audit_summary()['fiado_sales']

    @property
    def credit_sales(self) -> Decimal:
        return self.get_sales_audit_summary()['credit_sales']

    @property
    def contado_sales(self) -> Decimal:
        return self.get_sales_audit_summary()['contado_sales']

    @property
    def cash_sales(self) -> Decimal:
        return self.get_sales_audit_summary()['cash_sales']

    @property
    def electronic_sales(self) -> Decimal:
        return self.get_sales_audit_summary()['electronic_sales']

    @property
    def total_abonos(self) -> Decimal:
        return self.get_sales_audit_summary()['total_abonos']

    @property
    def abonos_cash(self) -> Decimal:
        return self.get_sales_audit_summary()['abonos_cash']
    @property
    def net_credit_change(self) -> Decimal:
        return self.get_sales_audit_summary()['net_credit_change']


class CashMovementType(models.TextChoices):
    INGRESO = 'INGRESO', 'Entrada de Efectivo'
    EGRESO = 'EGRESO', 'Salida de Efectivo'


class CashMovement(models.Model):
    shift = models.ForeignKey(CashShift, on_delete=models.CASCADE, related_name='cash_movements', verbose_name='Turno')
    movement_type = models.CharField('Tipo', max_length=10, choices=CashMovementType.choices)
    category = models.CharField('Concepto', max_length=50) # VENTA_EFECTIVO, ABONO_FIADO, GASTO_CAJA, DEVOLUCION, etc.
    amount = models.DecimalField('Monto (RD$)', max_digits=12, decimal_places=2)
    description = models.CharField('Descripción / Referencia', max_length=255, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Usuario')
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Movimiento de Caja'
        verbose_name_plural = 'Movimientos de Caja'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_movement_type_display()} | RD$ {self.amount} ({self.category})"


class CashShiftDenominationCount(models.Model):
    shift = models.ForeignKey(CashShift, on_delete=models.CASCADE, related_name='denomination_counts', verbose_name='Turno')
    denomination = models.ForeignKey(CashDenomination, on_delete=models.PROTECT, verbose_name='Denominación')
    quantity = models.PositiveIntegerField('Cantidad Contada', default=0)
    subtotal = models.DecimalField('Subtotal (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Conteo de Denominación'
        verbose_name_plural = 'Conteos de Denominación en Cierre'
        unique_together = ('shift', 'denomination')

    def save(self, *args, **kwargs):
        self.subtotal = Decimal(self.quantity) * self.denomination.value
        super().save(*args, **kwargs)
