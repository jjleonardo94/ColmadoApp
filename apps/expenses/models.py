from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class ExpenseCategory(models.Model):
    name = models.CharField('Nombre del Rubro de Gasto', max_length=100, unique=True)
    description = models.CharField('Descripción', max_length=200, blank=True)
    is_active = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Categoría de Gasto'
        verbose_name_plural = 'Categorías de Gastos'
        ordering = ['name']

    def __str__(self):
        return self.name


class ExpensePaymentMethod(models.TextChoices):
    EFECTIVO = 'EFECTIVO', 'Efectivo (Sale de Caja)'
    TRANSFERENCIA = 'TRANSFERENCIA', 'Transferencia Bancaria'
    TARJETA = 'TARJETA', 'Tarjeta / Débito'
    OTRO = 'OTRO', 'Otro Método'


class Expense(models.Model):
    branch = models.ForeignKey('core.ColmadoBranch', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses', verbose_name='Colmado / Sucursal')
    date = models.DateField('Fecha del Gasto')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses', verbose_name='Categoría')
    description = models.CharField('Descripción / Concepto', max_length=255)
    amount = models.DecimalField('Monto del Gasto (RD$)', max_digits=12, decimal_places=2)
    payment_method = models.CharField('Método de Pago', max_length=20, choices=ExpensePaymentMethod.choices, default=ExpensePaymentMethod.EFECTIVO)
    is_paid = models.BooleanField('Pagado', default=True)
    
    cash_shift = models.ForeignKey('cash.CashShift', on_delete=models.SET_NULL, null=True, blank=True, related_name='shift_expenses', verbose_name='Turno de Caja (Si fue en Efectivo)')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Registrado Por')
    voucher_image = models.ImageField('Foto Comprobante / Recibo', upload_to='vouchers/', null=True, blank=True)
    
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)
    updated_at = models.DateTimeField('Última Modificación', auto_now=True)

    class Meta:
        verbose_name = 'Gasto Operativo'
        verbose_name_plural = 'Gastos Operativos'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} | {self.category.name}: RD$ {self.amount:,.2f} - {self.description}"
