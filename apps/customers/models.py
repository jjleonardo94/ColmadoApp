from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Customer(models.Model):
    branch = models.ForeignKey('core.ColmadoBranch', on_delete=models.SET_NULL, null=True, blank=True, related_name='customers', verbose_name='Colmado / Sucursal')
    name = models.CharField('Nombre Completo / Apodo', max_length=150)
    alias = models.CharField('Alias o Nombre Comercial', max_length=100, blank=True)
    phone = models.CharField('Teléfono / WhatsApp', max_length=30, blank=True)
    identification = models.CharField('Cédula / RNC', max_length=25, blank=True)
    address = models.TextField('Dirección / Ubicación', blank=True)
    credit_limit = models.DecimalField('Límite de Crédito (RD$)', max_digits=12, decimal_places=2, default=Decimal('3000.00'))
    notes = models.TextField('Notas / Referencias', blank=True)
    is_active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField('Fecha de Registro', auto_now_add=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['name']
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        alias_phone = f" - {self.phone}" if self.phone else ""
        return f"{self.name}{alias_phone}"

    @property
    def current_balance(self) -> Decimal:
        """
        Calcula el saldo pendiente en tiempo real sumando cargos y restando abonos.
        Nunca se almacena como número arbitrario editable a mano.
        """
        txs = self.credit_transactions.all()
        charges = sum(t.amount for t in txs if t.transaction_type in ['CARGO_FIADO', 'AJUSTE_CARGO'])
        payments = sum(t.amount for t in txs if t.transaction_type in ['ABONO_PAGO', 'AJUSTE_ABONO'])
        return Decimal(charges - payments)

    @property
    def available_credit(self) -> Decimal:
        avail = self.credit_limit - self.current_balance
        return max(Decimal('0.00'), avail)

    def can_receive_credit(self, amount: Decimal) -> bool:
        if not self.is_active:
            return False
        # Si el límite es 0.00 se considera crédito abierto (sin tope fijado)
        if self.credit_limit <= Decimal('0.00'):
            return True
        return (self.current_balance + amount) <= self.credit_limit


class CreditTransactionType(models.TextChoices):
    CARGO_FIADO = 'CARGO_FIADO', 'Cargo a Crédito'
    ABONO_PAGO = 'ABONO_PAGO', 'Abono a Crédito'
    AJUSTE_CARGO = 'AJUSTE_CARGO', 'Ajuste Cargo'
    AJUSTE_ABONO = 'AJUSTE_ABONO', 'Ajuste Abono'


class CreditTransaction(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='credit_transactions', verbose_name='Cliente')
    sale = models.ForeignKey('sales.Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_transactions', verbose_name='Venta Relacionada')
    transaction_type = models.CharField('Tipo de Operación', max_length=25, choices=CreditTransactionType.choices)
    amount = models.DecimalField('Importe (RD$)', max_digits=12, decimal_places=2)
    balance_after = models.DecimalField('Saldo Resultante (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_method = models.CharField('Método de Cobro', max_length=25, blank=True, default='EFECTIVO')
    cash_shift = models.ForeignKey('cash.CashShift', on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_payments', verbose_name='Turno de Caja')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Usuario que Registró')
    reference = models.CharField('Referencia / Comprobante', max_length=100, blank=True)
    notes = models.TextField('Observaciones', blank=True)
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Transacción de Crédito'
        verbose_name_plural = 'Cuentas por Cobrar y Créditos'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M')} | {self.customer.name} | {self.get_transaction_type_display()}: RD$ {self.amount}"
