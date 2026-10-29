from django.db import models
from decimal import Decimal

class Category(models.Model):
    name = models.CharField('Nombre de la Categoría', max_length=100, unique=True)
    description = models.TextField('Descripción', blank=True)
    is_active = models.BooleanField('Activa', default=True)
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['name']

    def __str__(self):
        return self.name


class UnitOfMeasure(models.TextChoices):
    UNIDAD = 'UND', 'Unidad (und)'
    LIBRA = 'LB', 'Libra (lb)'
    KILOGRAMO = 'KG', 'Kilogramo (kg)'
    LITRO = 'LT', 'Litro (lt)'
    ONZA = 'OZ', 'Onza (oz)'
    PAQUETE = 'PQ', 'Paquete (pq)'
    CAJA = 'CJ', 'Caja (cj)'


class SaleType(models.TextChoices):
    UNIT = 'UNIT', 'Por Unidad (Entero)'
    FRACTION = 'FRACTION', 'Fraccionado / Por Peso o Volumen'


class Product(models.Model):
    name = models.CharField('Nombre del Producto', max_length=200)
    internal_code = models.CharField('Código Interno', max_length=50, unique=True)
    barcode = models.CharField('Código de Barras', max_length=80, blank=True, null=True, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products', verbose_name='Categoría')
    description = models.TextField('Descripción / Notas', blank=True)
    
    unit_of_measure = models.CharField('Unidad de Medida', max_length=10, choices=UnitOfMeasure.choices, default=UnitOfMeasure.UNIDAD)
    sale_type = models.CharField('Tipo de Venta', max_length=15, choices=SaleType.choices, default=SaleType.UNIT)
    
    cost_price = models.DecimalField('Costo de Compra (RD$)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sale_price = models.DecimalField('Precio de Venta (RD$)', max_digits=12, decimal_places=2)
    wholesale_price = models.DecimalField('Precio Mayorista / Alternativo (RD$)', max_digits=12, decimal_places=2, null=True, blank=True)
    
    current_stock = models.DecimalField('Existencia Actual', max_digits=12, decimal_places=3, default=Decimal('0.000'))
    min_stock = models.DecimalField('Stock Mínimo (Alerta)', max_digits=12, decimal_places=3, default=Decimal('5.000'))
    max_stock = models.DecimalField('Stock Máximo', max_digits=12, decimal_places=3, null=True, blank=True)
    
    supplier = models.ForeignKey('purchasing.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name='Suplidor Habitual')
    expiry_date = models.DateField('Fecha de Vencimiento', null=True, blank=True)
    
    is_active = models.BooleanField('Activo', default=True)
    image = models.ImageField('Imagen del Producto', upload_to='products/', null=True, blank=True)
    
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)
    updated_at = models.DateTimeField('Última Modificación', auto_now=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['name']
        indexes = [
            models.Index(fields=['internal_code']),
            models.Index(fields=['barcode']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.internal_code})"

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock and self.current_stock > Decimal('0.000')

    @property
    def is_out_of_stock(self):
        return self.current_stock <= Decimal('0.000')

    @property
    def allows_decimals(self):
        return self.sale_type == SaleType.FRACTION

    def calculate_quantity_from_amount(self, amount: Decimal) -> Decimal:
        """Calcula la cantidad equivalente dada una cantidad de dinero en pesos dominicanos."""
        if self.sale_price <= Decimal('0.00'):
            return Decimal('0.000')
        qty = amount / self.sale_price
        return Decimal(round(qty, 3))
