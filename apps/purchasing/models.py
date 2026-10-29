from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Supplier(models.Model):
    name = models.CharField('Razón Social / Nombre Comercial', max_length=150)
    tax_id = models.CharField('RNC / Cédula', max_length=30, blank=True)
    phone = models.CharField('Teléfono', max_length=30, blank=True)
    email = models.EmailField('Correo Electrónico', blank=True)
    address = models.TextField('Dirección', blank=True)
    contact_person = models.CharField('Persona de Contacto / Vendedor', max_length=100, blank=True)
    notes = models.TextField('Observaciones', blank=True)
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Fecha de Registro', auto_now_add=True)

    class Meta:
        verbose_name = 'Suplidor / Proveedor'
        verbose_name_plural = 'Suplidores / Proveedores'
        ordering = ['name']

    def __str__(self):
        return self.name


class PurchaseStatus(models.TextChoices):
    BORRADOR = 'BORRADOR', 'Borrador / Registrada'
    RECIBIDA = 'RECIBIDA', 'Mercancía Recibida (Afectó Stock)'
    ANULADA = 'ANULADA', 'Anulada'


class PurchasePaymentStatus(models.TextChoices):
    PAGADA = 'PAGADA', 'Pagada Completa'
    PENDIENTE = 'PENDIENTE', 'Pendiente de Pago'
    PARCIAL = 'PARCIAL', 'Abonada Parcialmente'


class Purchase(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchases', verbose_name='Suplidor')
    invoice_number = models.CharField('No. Factura del Proveedor', max_length=60, blank=True)
    purchase_date = models.DateField('Fecha de Compra')
    status = models.CharField('Estado de Recepción', max_length=20, choices=PurchaseStatus.choices, default=PurchaseStatus.BORRADOR)
    payment_status = models.CharField('Estado de Pago', max_length=20, choices=PurchasePaymentStatus.choices, default=PurchasePaymentStatus.PAGADA)
    
    subtotal = models.DecimalField('Subtotal (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField('ITBIS / Impuesto (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount = models.DecimalField('Descuento (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField('Total Factura (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    notes = models.TextField('Notas', blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_purchases', verbose_name='Registrada Por')
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_purchases', verbose_name='Recibida Por')
    received_at = models.DateTimeField('Fecha y Hora de Recepción', null=True, blank=True)
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)

    class Meta:
        verbose_name = 'Compra de Mercancía'
        verbose_name_plural = 'Compras y Cuentas por Pagar'
        ordering = ['-purchase_date', '-created_at']

    def __str__(self):
        prov = self.supplier.name
        inv = f" #{self.invoice_number}" if self.invoice_number else ""
        return f"Compra #{self.id}{inv} | {prov} | RD$ {self.total:,.2f}"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items', verbose_name='Compra')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='purchase_items', verbose_name='Producto')
    quantity = models.DecimalField('Cantidad Comprada', max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField('Costo Unitario (RD$)', max_digits=12, decimal_places=2)
    subtotal = models.DecimalField('Subtotal (RD$)', max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Artículo de Compra'
        verbose_name_plural = 'Artículos de Compras'

    def save(self, *args, **kwargs):
        self.subtotal = Decimal(self.quantity) * self.unit_cost
        super().save(*args, **kwargs)
