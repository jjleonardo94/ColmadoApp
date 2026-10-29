from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrador'
    ENCARGADO = 'ENCARGADO', 'Encargado / Supervisor'
    CAJERO = 'CAJERO', 'Cajero / Dependiente'
    INVENTARIO = 'INVENTARIO', 'Encargado de Inventario'
    COMPRAS = 'COMPRAS', 'Encargado de Compras'
    CONSULTA = 'CONSULTA', 'Consulta y Reportes'


class CustomRole(models.Model):
    name = models.CharField('Nombre del Perfil / Rol', max_length=100, unique=True)
    description = models.TextField('Descripción del Perfil', blank=True)
    is_system_default = models.BooleanField('Rol por Defecto del Sistema', default=False)
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)

    # 1. POS / Ventas
    can_access_pos = models.BooleanField('Acceso a Punto de Venta (POS)', default=True)
    can_apply_discounts = models.BooleanField('Puede otorgar descuentos en ventas', default=False)
    can_change_prices = models.BooleanField('Puede modificar precios directamente en venta', default=False)
    can_void_sales = models.BooleanField('Puede anular ventas y tickets', default=False)
    can_view_sales_history = models.BooleanField('Puede ver historial de ventas', default=True)

    # 2. Fiados & Clientes
    can_access_credit = models.BooleanField('Acceso a Libreta de Fiados', default=True)
    can_authorize_credit = models.BooleanField('Puede autorizar ventas a crédito / fiado', default=False)
    can_record_abono = models.BooleanField('Puede registrar abonos a deudas', default=True)
    can_manage_customers = models.BooleanField('Puede crear y editar clientes y límites de crédito', default=False)

    # 3. Inventario & Catálogo
    can_access_catalog = models.BooleanField('Acceso a Productos y Categorías', default=False)
    can_edit_products = models.BooleanField('Puede crear y editar productos y costos', default=False)
    can_adjust_inventory = models.BooleanField('Puede realizar ajustes de stock y mermas', default=False)
    can_access_purchases = models.BooleanField('Acceso a Compras y Suplidores', default=False)

    # 4. Caja & Operaciones
    can_open_close_shifts = models.BooleanField('Puede abrir y cerrar turnos de caja', default=True)
    can_view_cash_history = models.BooleanField('Puede ver historial de turnos y arqueos', default=False)
    can_register_expenses = models.BooleanField('Puede registrar gastos operativos', default=False)
    can_manage_cash_settings = models.BooleanField('Puede modificar la configuración de caja y fondos', default=False)
    can_authorize_cash_differences = models.BooleanField('Puede autorizar diferencias en arqueos de caja', default=False)

    # 5. Reportes & Auditoría
    can_view_reports = models.BooleanField('Puede ver reportes financieros y márgenes', default=False)
    can_export_reports = models.BooleanField('Puede exportar reportes a Excel/CSV', default=False)
    can_view_audit_log = models.BooleanField('Puede ver bitácora de auditoría', default=False)

    # 6. Comunicaciones & Administración
    can_manage_whatsapp = models.BooleanField('Puede gestionar WhatsApp Business API', default=False)
    can_manage_deliveries = models.BooleanField('Puede administrar repartidores y deliverys', default=False)
    can_manage_branches = models.BooleanField('Puede administrar colmados y sucursales', default=False)
    can_manage_users = models.BooleanField('Puede gestionar usuarios y perfiles', default=False)
    can_manage_settings = models.BooleanField('Puede modificar configuraciones del sistema', default=False)

    class Meta:
        verbose_name = 'Perfil / Rol'
        verbose_name_plural = 'Perfiles y Roles'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def permissions_count(self):
        count = 0
        for f in self._meta.fields:
            if isinstance(f, models.BooleanField) and f.name.startswith('can_') and getattr(self, f.name):
                count += 1
        return count


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name='Usuario')
    custom_role = models.ForeignKey(CustomRole, on_delete=models.SET_NULL, null=True, blank=True, related_name='profiles', verbose_name='Perfil / Rol Asignado')
    role = models.CharField('Rol Legado', max_length=20, choices=UserRole.choices, default=UserRole.CAJERO)
    phone = models.CharField('Teléfono / Móvil', max_length=30, blank=True)
    identification = models.CharField('Cédula de Identidad', max_length=20, blank=True)

    # Sucursales / Colmados
    all_branches_access = models.BooleanField('Acceso a todos los colmados (Dueño / Admin General)', default=False)
    assigned_branches = models.ManyToManyField('core.ColmadoBranch', blank=True, related_name='assigned_users', verbose_name='Colmados Asignados')

    # Flag para sobrescribir permisos del perfil por persona
    override_role_permissions = models.BooleanField('Personalizar permisos individuales (Sobrescribir perfil)', default=False)

    # Permisos individuales (por si override_role_permissions es True)
    can_access_pos = models.BooleanField('Acceso a Punto de Venta (POS)', default=True)
    can_apply_discounts = models.BooleanField('Puede otorgar descuentos en ventas', default=False)
    can_change_prices = models.BooleanField('Puede modificar precios directamente en venta', default=False)
    can_void_sales = models.BooleanField('Puede anular ventas y tickets', default=False)
    can_view_sales_history = models.BooleanField('Puede ver historial de ventas', default=True)

    can_access_credit = models.BooleanField('Acceso a Libreta de Fiados', default=True)
    can_authorize_credit = models.BooleanField('Puede autorizar ventas a crédito / fiado', default=False)
    can_record_abono = models.BooleanField('Puede registrar abonos a deudas', default=True)
    can_manage_customers = models.BooleanField('Puede crear y editar clientes y límites de crédito', default=False)

    can_access_catalog = models.BooleanField('Acceso a Productos y Categorías', default=False)
    can_edit_products = models.BooleanField('Puede crear y editar productos y costos', default=False)
    can_adjust_inventory = models.BooleanField('Puede realizar ajustes de stock y mermas', default=False)
    can_access_purchases = models.BooleanField('Acceso a Compras y Suplidores', default=False)

    can_open_close_shifts = models.BooleanField('Puede abrir y cerrar turnos de caja', default=True)
    can_view_cash_history = models.BooleanField('Puede ver historial de turnos y arqueos', default=False)
    can_register_expenses = models.BooleanField('Puede registrar gastos operativos', default=False)
    can_manage_cash_settings = models.BooleanField('Puede modificar la configuración de caja y fondos', default=False)
    can_authorize_cash_differences = models.BooleanField('Puede autorizar diferencias en arqueos de caja', default=False)

    can_view_reports = models.BooleanField('Puede ver reportes financieros y márgenes', default=False)
    can_export_reports = models.BooleanField('Puede exportar reportes a Excel/CSV', default=False)
    can_view_audit_log = models.BooleanField('Puede ver bitácora de auditoría', default=False)

    can_manage_whatsapp = models.BooleanField('Puede gestionar WhatsApp Business API', default=False)
    can_manage_deliveries = models.BooleanField('Puede administrar repartidores y deliverys', default=False)
    can_manage_branches = models.BooleanField('Puede administrar colmados y sucursales', default=False)
    can_manage_users = models.BooleanField('Puede gestionar usuarios y perfiles', default=False)
    can_manage_settings = models.BooleanField('Puede modificar configuraciones del sistema', default=False)

    # Compatibilidad con campos anteriores
    can_process_returns = models.BooleanField('Puede procesar devoluciones', default=False)

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        role_label = self.custom_role.name if self.custom_role else self.get_role_display()
        return f"{self.user.get_full_name() or self.user.username} ({role_label})"

    def has_perm(self, perm_name: str) -> bool:
        if self.user.is_superuser:
            return True
        if self.override_role_permissions:
            return getattr(self, perm_name, False)
        if self.custom_role:
            return getattr(self.custom_role, perm_name, False)
        return getattr(self, perm_name, False)

    def check_permission(self, perm_name: str) -> bool:
        return self.has_perm(perm_name)

    def get_allowed_branches(self):
        from apps.core.models import ColmadoBranch
        if self.user.is_superuser or self.all_branches_access or self.has_perm('can_manage_branches'):
            return ColmadoBranch.objects.filter(is_active=True).order_by('-is_main', 'name')
        branches = self.assigned_branches.filter(is_active=True).order_by('-is_main', 'name')
        if branches.exists():
            return branches
        # Si no tiene asignado nada, retornar la principal como fallback seguro
        main_b = ColmadoBranch.objects.filter(is_active=True, is_main=True).first()
        if main_b:
            return ColmadoBranch.objects.filter(pk=main_b.pk)
        return ColmadoBranch.objects.filter(is_active=True)[:1]

    def can_access_branch(self, branch_id: int) -> bool:
        if self.user.is_superuser or self.all_branches_access or self.has_perm('can_manage_branches'):
            return True
        return self.assigned_branches.filter(id=branch_id, is_active=True).exists()

    @property
    def perms(self):
        """Diccionario para evaluación dinámica de permisos en plantillas HTML."""
        res = {}
        for f in self._meta.fields:
            if isinstance(f, models.BooleanField) and f.name.startswith('can_'):
                res[f.name] = self.has_perm(f.name)
        return res

    def get_role_name(self):
        if self.user.is_superuser:
            return "Superadministrador"
        if self.custom_role:
            return self.custom_role.name
        return self.get_role_display()


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        profile = UserProfile.objects.create(
            user=instance,
            role=UserRole.ADMIN if instance.is_superuser else UserRole.CAJERO,
            all_branches_access=True if instance.is_superuser else False
        )
        if instance.is_superuser:
            admin_role = CustomRole.objects.filter(name__icontains='admin').first()
            if admin_role:
                profile.custom_role = admin_role
                profile.save()
