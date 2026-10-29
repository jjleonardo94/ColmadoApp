from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class MovementType(models.TextChoices):
    COMPRA = 'COMPRA', 'Entrada por Compra'
    VENTA = 'VENTA', 'Salida por Venta'
    ANULACION_VENTA = 'ANULACION_VENTA', 'Reingreso por Anulación de Venta'
    DEVOLUCION_CLIENTE = 'DEVOLUCION_CLIENTE', 'Reingreso por Devolución de Cliente'
    DEVOLUCION_SUPLIDOR = 'DEVOLUCION_SUPLIDOR', 'Salida por Devolución a Suplidor'
    AJUSTE_POSITIVO = 'AJUSTE_POSITIVO', 'Ajuste Manual Positivo'
    AJUSTE_NEGATIVO = 'AJUSTE_NEGATIVO', 'Ajuste Manual Negativo'
    MERMA_DANADO = 'MERMA_DANADO', 'Merma, Dañado o Vencido'


class InventoryMovement(models.Model):
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='inventory_movements', verbose_name='Producto')
    movement_type = models.CharField('Tipo de Movimiento', max_length=25, choices=MovementType.choices)
    quantity = models.DecimalField('Cantidad', max_digits=12, decimal_places=3)
    previous_stock = models.DecimalField('Stock Anterior', max_digits=12, decimal_places=3)
    new_stock = models.DecimalField('Stock Resultante', max_digits=12, decimal_places=3)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Usuario Responsable')
    reason = models.CharField('Motivo / Justificación', max_length=255, blank=True)
    reference_doc = models.CharField('Documento Relacionado', max_length=100, blank=True)
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Movimiento de Inventario'
        verbose_name_plural = 'Movimientos de Inventario'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M')} | {self.product.name} | {self.get_movement_type_display()} ({self.quantity})"
