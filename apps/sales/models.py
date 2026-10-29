from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class SaleStatus(models.TextChoices):
    COMPLETADA = 'COMPLETADA', 'Completada'
    ANULADA = 'ANULADA', 'Anulada'


class PaymentMethodChoices(models.TextChoices):
    EFECTIVO = 'EFECTIVO', 'Efectivo'
    TARJETA = 'TARJETA', 'Tarjeta'
    TRANSFERENCIA = 'TRANSFERENCIA', 'Transferencia'
    FIADO = 'FIADO', 'Crédito'
    MIXTO = 'MIXTO', 'Pago Mixto'

PaymentMethodChoices.CREDITO = PaymentMethodChoices.FIADO


class Sale(models.Model):
    ticket_number = models.CharField('No. de Ticket / Factura', max_length=50, unique=True)
    branch = models.ForeignKey('core.ColmadoBranch', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales', verbose_name='Colmado / Sucursal')
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales', verbose_name='Cliente')
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_handled', verbose_name='Cajero / Dependiente')
    cash_shift = models.ForeignKey('cash.CashShift', on_delete=models.SET_NULL, null=True, blank=True, related_name='shift_sales', verbose_name='Turno de Caja')
    origin = models.CharField('Canal de Venta', max_length=20, default='POS', choices=[('POS', 'Punto de Venta'), ('WHATSAPP', 'WhatsApp'), ('DELIVERY', 'Delivery')])
    whatsapp_conversation = models.ForeignKey('whatsapp.WhatsAppConversation', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales', verbose_name='Conversación de WhatsApp')
    
    status = models.CharField('Estado', max_length=15, choices=SaleStatus.choices, default=SaleStatus.COMPLETADA)
    payment_method = models.CharField('Método Principal', max_length=20, choices=PaymentMethodChoices.choices, default=PaymentMethodChoices.EFECTIVO)
    
    subtotal = models.DecimalField('Subtotal (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount = models.DecimalField('Descuento Total (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField('ITBIS / Impuesto (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField('Total General (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Multimoneda
    currency_received = models.CharField('Moneda Recibida', max_length=10, default='DOP')
    exchange_rate_used = models.DecimalField('Tasa de Cambio Aplicada', max_digits=10, decimal_places=4, default=Decimal('1.0000'))
    amount_received = models.DecimalField('Importe Recibido del Cliente', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    change_given = models.DecimalField('Devuelta / Cambio (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    notes = models.TextField('Notas', blank=True)
    void_reason = models.TextField('Motivo de Anulación', blank=True)
    voided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='voided_sales', verbose_name='Anulado Por')
    voided_at = models.DateTimeField('Fecha de Anulación', null=True, blank=True)
    
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ticket_number']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        client = self.customer.name if self.customer else "Consumidor Final"
        return f"{self.ticket_number} | {client} | RD$ {self.total:,.2f} [{self.get_status_display()}]"

    @property
    def is_voided(self):
        return self.status == SaleStatus.ANULADA

    @property
    def gross_profit(self) -> Decimal:
        """Calcula la ganancia bruta real de la venta utilizando los costos unitarios históricos."""
        if self.is_voided:
            return Decimal('0.00')
        total_revenue = self.total
        total_cost = sum(item.quantity * item.unit_cost for item in self.items.all())
        return Decimal(total_revenue - total_cost)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', verbose_name='Venta')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='sale_items', verbose_name='Producto')
    quantity = models.DecimalField('Cantidad', max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField('Costo Unitario al Vender (RD$)', max_digits=12, decimal_places=2)
    unit_price = models.DecimalField('Precio Unitario de Venta (RD$)', max_digits=12, decimal_places=2)
    discount = models.DecimalField('Descuento de Línea (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    subtotal = models.DecimalField('Importe Neto de Línea (RD$)', max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Línea de Venta'
        verbose_name_plural = 'Líneas de Venta'

    def save(self, *args, **kwargs):
        gross = Decimal(self.quantity) * self.unit_price
        self.subtotal = gross - self.discount
        super().save(*args, **kwargs)

    @property
    def total_cost(self) -> Decimal:
        return Decimal(self.quantity) * self.unit_cost

    def get_total_cost(self) -> Decimal:
        return self.total_cost

    @property
    def profit(self) -> Decimal:
        return self.subtotal - self.total_cost

    def get_profit(self) -> Decimal:
        return self.profit


class Payment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments', verbose_name='Venta')
    payment_method = models.CharField('Método de Pago', max_length=20, choices=PaymentMethodChoices.choices)
    amount = models.DecimalField('Monto Abonado (RD$)', max_digits=12, decimal_places=2)
    reference = models.CharField('Referencia / Aprobación', max_length=100, blank=True)
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Detalle de Pago'
        verbose_name_plural = 'Detalles de Pagos'

    def __str__(self):
        return f"{self.get_payment_method_display()}: RD$ {self.amount:,.2f}"


class SaleReturn(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns', verbose_name='Venta')
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Usuario que Autorizó')
    reason = models.CharField('Motivo de la Devolución', max_length=255)
    total_refunded = models.DecimalField('Total Reembolsado (RD$)', max_digits=12, decimal_places=2)
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Devolución de Venta'
        verbose_name_plural = 'Devoluciones de Ventas'
        ordering = ['-created_at']


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items', verbose_name='Devolución')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, verbose_name='Producto')
    quantity = models.DecimalField('Cantidad Devuelta', max_digits=12, decimal_places=3)
    refund_amount = models.DecimalField('Monto Reembolsado', max_digits=12, decimal_places=2)


class DeliveryPerson(models.Model):
    branch = models.ForeignKey('core.ColmadoBranch', on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_persons', verbose_name='Colmado / Sucursal')
    name = models.CharField('Nombre del Repartidor', max_length=120)
    phone = models.CharField('Teléfono / WhatsApp', max_length=30, blank=True)
    vehicle = models.CharField('Vehículo / Placa', max_length=60, blank=True, default='Motor')
    is_active = models.BooleanField('Activo', default=True)
    notes = models.TextField('Notas', blank=True)
    created_at = models.DateTimeField('Fecha de Registro', auto_now_add=True)

    class Meta:
        verbose_name = 'Repartidor / Delivery'
        verbose_name_plural = 'Repartidores / Deliverys'
        ordering = ['name']

    def __str__(self):
        veh_str = f" ({self.vehicle})" if self.vehicle else ""
        return f"{self.name}{veh_str}"


class DeliveryStatus(models.TextChoices):
    PREPARANDO = 'PREPARANDO', 'En Preparación'
    PENDIENTE_ENVIO = 'PENDIENTE_ENVIO', 'Pendiente de Envío (Delivery Express)'
    EN_CAMINO = 'EN_CAMINO', 'En Camino / Enviado'
    ENTREGADO = 'ENTREGADO', 'Entregado'
    CANCELADO = 'CANCELADO', 'Cancelado'

DeliveryStatus.ENVIADO = DeliveryStatus.EN_CAMINO


class DeliveryOrder(models.Model):
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='delivery_order', verbose_name='Venta Asociada')
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_orders', verbose_name='Cliente')
    delivery_person = models.ForeignKey(DeliveryPerson, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders', verbose_name='Repartidor Asignado')
    status = models.CharField('Estado del Delivery', max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDIENTE_ENVIO)
    destination_type = models.CharField('Destino del Pedido', max_length=20, choices=[('DIRECTO', 'Entrega Directa'), ('EXPRESS', 'Delivery Express')], default='EXPRESS')
    delivery_address = models.CharField('Dirección de Entrega', max_length=255, blank=True)
    notes = models.TextField('Instrucciones de Entrega', blank=True)
    whatsapp_conversation = models.ForeignKey('whatsapp.WhatsAppConversation', on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_orders', verbose_name='Conversación de WhatsApp')
    
    # Notificaciones WhatsApp
    notification_sent = models.BooleanField('Notificación de Salida Enviada', default=False)
    notification_status = models.CharField('Estado Notificación', max_length=20, blank=True, default='') # sent, failed, etc.
    notification_error = models.TextField('Error Notificación', blank=True)
    
    # Auditoría de tiempos
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)
    dispatched_at = models.DateTimeField('Fecha de Salida', null=True, blank=True)
    delivered_at = models.DateTimeField('Fecha de Entrega', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_deliveries', verbose_name='Creado Por')
    dispatched_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='dispatched_deliveries', verbose_name='Despachado Por')

    class Meta:
        verbose_name = 'Pedido de Delivery'
        verbose_name_plural = 'Pedidos de Delivery'
        ordering = ['-created_at']

    def __str__(self):
        c_name = self.customer.name if self.customer else "Cliente General"
        return f"Delivery #{self.id} | {c_name} | {self.sale.ticket_number} [{self.get_status_display()}]"
