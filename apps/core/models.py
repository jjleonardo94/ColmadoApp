from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class BusinessSettings(models.Model):
    PRINTER_WIDTH_CHOICES = [
        ('58mm', 'Térmica 58 mm'),
        ('80mm', 'Térmica 80 mm'),
    ]

    name = models.CharField('Nombre del Colmado / Negocio', max_length=150, default='Colmado El Progreso')
    rnc = models.CharField('RNC / Identificación Fiscal', max_length=25, blank=True, default='1-31-89745-2')
    phone = models.CharField('Teléfono / WhatsApp', max_length=30, blank=True, default='(809) 555-0199')
    address = models.TextField('Dirección', blank=True, default='Calle Principal #45, Ensanche La Fe, Santo Domingo, R.D.')
    slogan = models.CharField('Eslogan / Encabezado', max_length=200, blank=True, default='¡Lo mejor para el hogar con la mejor atención!')
    receipt_footer = models.TextField('Pie de Recibo', blank=True, default='¡Gracias por preferirnos!\nConserve este recibo para cualquier reclamación.')
    
    # Monedas
    base_currency = models.CharField('Moneda Base', max_length=10, default='DOP')
    usd_rate = models.DecimalField('Tasa Dólar (USD a DOP)', max_digits=10, decimal_places=4, default=Decimal('59.5000'))
    eur_rate = models.DecimalField('Tasa Euro (EUR a DOP)', max_digits=10, decimal_places=4, default=Decimal('64.0000'))
    
    # Políticas operativas
    low_stock_threshold = models.PositiveIntegerField('Alerta Stock Mínimo por Defecto', default=5)
    allow_negative_stock = models.BooleanField('Permitir Inventario Negativo (Requiere Admin)', default=False)
    printer_width = models.CharField('Ancho de Impresora Térmica', max_length=10, choices=PRINTER_WIDTH_CHOICES, default='80mm')
    
    # Configuración de Caja (Fondo inicial y permanencia al cierre)
    default_initial_cash = models.DecimalField('Fondo Inicial Habitual (RD$)', max_digits=12, decimal_places=2, default=Decimal('2500.00'))
    default_closing_cash_fund = models.DecimalField('Importe Fijo que Debe Permanecer en Caja al Cierre (RD$)', max_digits=12, decimal_places=2, default=Decimal('2500.00'))

    # Plantilla de Delivery por WhatsApp
    delivery_notification_template = models.TextField(
        'Plantilla de Mensaje de Salida de Delivery',
        blank=True,
        default="Hola {cliente}, tu pedido #{ticket} ya está preparado y ha salido para entrega{delivery_info}. Total: RD$ {total} ({metodo_pago}). ¡Gracias por preferirnos!"
    )
    
    updated_at = models.DateTimeField('Última Actualización', auto_now=True)

    class Meta:
        verbose_name = 'Configuración del Negocio'
        verbose_name_plural = 'Configuraciones del Negocio'

    def __str__(self):
        return self.name

    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Usuario')
    action = models.CharField('Acción Realizada', max_length=60)
    target_model = models.CharField('Módulo / Entidad', max_length=60, blank=True)
    target_id = models.CharField('ID del Registro', max_length=60, blank=True)
    details = models.TextField('Detalles y Observaciones', blank=True)
    ip_address = models.GenericIPAddressField('Dirección IP', null=True, blank=True)
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Bitácora de Auditoría'
        verbose_name_plural = 'Bitácoras de Auditoría'
        ordering = ['-created_at']

    def __str__(self):
        user_name = self.user.username if self.user else 'Sistema'
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M')} | {user_name} | {self.action}"


class ColmadoBranch(models.Model):
    name = models.CharField('Nombre del Colmado / Sucursal', max_length=150)
    code = models.CharField('Código o Siglas', max_length=20, unique=True, default='SUC-01')
    phone = models.CharField('Teléfono / WhatsApp', max_length=30, blank=True)
    rnc = models.CharField('RNC o Cédula', max_length=25, blank=True)
    address = models.CharField('Dirección', max_length=255, blank=True)
    city = models.CharField('Sector / Ciudad', max_length=100, default='Santo Domingo')
    manager_name = models.CharField('Encargado / Administrador', max_length=120, blank=True)
    is_main = models.BooleanField('Sucursal Principal', default=False)
    is_active = models.BooleanField('Activo', default=True)
    slogan = models.CharField('Eslogan / Encabezado', max_length=200, blank=True, default='')
    receipt_footer = models.TextField('Pie de Recibo', blank=True, default='')
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)

    class Meta:
        verbose_name = 'Colmado / Sucursal'
        verbose_name_plural = 'Colmados y Sucursales'
        ordering = ['-is_main', 'name']

    def __str__(self):
        main_tag = " (Principal)" if self.is_main else ""
        return f"{self.name}{main_tag}"

    @classmethod
    def get_default_branch(cls):
        branch = cls.objects.filter(is_active=True, is_main=True).first()
        if not branch:
            branch = cls.objects.filter(is_active=True).first()
        if not branch:
            # Seed from BusinessSettings if empty
            settings_obj = BusinessSettings.get_settings()
            branch = cls.objects.create(
                name=settings_obj.name or "Colmado El Progreso",
                code="SUC-01",
                phone=settings_obj.phone or "(809) 555-0199",
                rnc=settings_obj.rnc or "1-31-89745-2",
                address=settings_obj.address or "Calle Principal #45, Ensanche La Fe",
                city="Santo Domingo",
                manager_name="Administrador",
                is_main=True,
                is_active=True
            )
        return branch
