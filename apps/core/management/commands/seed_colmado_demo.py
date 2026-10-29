from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from apps.core.models import BusinessSettings
from apps.accounts.models import UserProfile, UserRole
from apps.catalog.models import Category, Product, UnitOfMeasure, SaleType
from apps.cash.models import CashRegister, CashDenomination, CashShift, CashShiftStatus, CashMovement, CashMovementType
from apps.purchasing.models import Supplier
from apps.customers.models import Customer
from apps.expenses.models import ExpenseCategory

class Command(BaseCommand):
    help = 'Inicializa la base de datos de ColmadoPOS con datos realistas para la República Dominicana'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("==> Iniciando carga de datos demostrativos de ColmadoPOS..."))

        # 1. Configuración del Colmado
        settings = BusinessSettings.get_settings()
        settings.name = "Colmado El Progreso"
        settings.rnc = "1-31-89745-2"
        settings.phone = "(809) 555-0199"
        settings.address = "Calle Francisco del Rosario Sánchez #45, Ensanche La Fe, Santo Domingo, D.N."
        settings.slogan = "¡Calidad, frescura y la mejor atención en el barrio!"
        settings.receipt_footer = "¡Gracias por su compra en Colmado El Progreso!\nConserve este recibo para reclamos.\nDios bendiga su hogar."
        settings.usd_rate = Decimal('59.50')
        settings.eur_rate = Decimal('64.00')
        settings.low_stock_threshold = 5
        settings.allow_negative_stock = False
        settings.printer_width = '80mm'
        settings.save()
        self.stdout.write(self.style.SUCCESS("[OK] Configuracion de Colmado El Progreso actualizada"))

        # 2. Denominaciones Dominicanas Oficiales
        denominations_data = [
            # Monedas
            {"name": "Moneda RD$ 2", "value": Decimal('2.00'), "type": "MONEDA", "order": 1},
            {"name": "Moneda RD$ 5", "value": Decimal('5.00'), "type": "MONEDA", "order": 2},
            {"name": "Moneda RD$ 10", "value": Decimal('10.00'), "type": "MONEDA", "order": 3},
            {"name": "Moneda RD$ 25", "value": Decimal('25.00'), "type": "MONEDA", "order": 4},
            {"name": "Moneda RD$ 50", "value": Decimal('50.00'), "type": "MONEDA", "order": 5},
            # Billetes
            {"name": "Billete RD$ 50", "value": Decimal('50.00'), "type": "BILLETE", "order": 6},
            {"name": "Billete RD$ 100", "value": Decimal('100.00'), "type": "BILLETE", "order": 7},
            {"name": "Billete RD$ 200", "value": Decimal('200.00'), "type": "BILLETE", "order": 8},
            {"name": "Billete RD$ 500", "value": Decimal('500.00'), "type": "BILLETE", "order": 9},
            {"name": "Billete RD$ 1,000", "value": Decimal('1000.00'), "type": "BILLETE", "order": 10},
            {"name": "Billete RD$ 2,000", "value": Decimal('2000.00'), "type": "BILLETE", "order": 11},
        ]
        for item in denominations_data:
            CashDenomination.objects.update_or_create(
                value=item['value'],
                denomination_type=item['type'],
                defaults={'name': item['name'], 'is_active': True, 'sort_order': item['order']}
            )
        self.stdout.write(self.style.SUCCESS("[OK] Catalogo de billetes y monedas dominicanas configurado"))

        # 3. Categorias de Gastos
        expense_cats = [
            "Alquiler del Local",
            "Electricidad (Edesur / Edeeste)",
            "Agua Potable (CAASD)",
            "Transporte y Flete de Mercancia",
            "Salarios y Jornales de Dependientes",
            "Mantenimiento de Freezers y Planta",
            "Bolsas Plasticas, Papel y Suministros",
            "Alimentacion del Personal",
            "Otros Gastos Menores",
        ]
        for name in expense_cats:
            ExpenseCategory.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("[OK] Categorias de gastos operativos registradas"))

        # 4. Usuarios del Sistema
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'first_name': 'Ramon', 'last_name': 'Perez (Dueno)', 'email': 'admin@colmadopos.do', 'is_staff': True, 'is_superuser': True}
        )
        admin_user.set_password('admin123')
        admin_user.save()
        if hasattr(admin_user, 'profile'):
            admin_user.profile.role = UserRole.ADMIN
            admin_user.profile.save()

        cajero_user, _ = User.objects.get_or_create(
            username='cajero',
            defaults={'first_name': 'Juan', 'last_name': 'Santana', 'email': 'cajero@colmadopos.do', 'is_staff': False, 'is_superuser': False}
        )
        cajero_user.set_password('cajero123')
        cajero_user.save()
        if hasattr(cajero_user, 'profile'):
            cajero_user.profile.role = UserRole.CAJERO
            cajero_user.profile.save()

        encargado_user, _ = User.objects.get_or_create(
            username='encargado',
            defaults={'first_name': 'Carlos', 'last_name': 'Jimenez', 'email': 'encargado@colmadopos.do', 'is_staff': True, 'is_superuser': False}
        )
        encargado_user.set_password('encargado123')
        encargado_user.save()
        if hasattr(encargado_user, 'profile'):
            encargado_user.profile.role = UserRole.ENCARGADO
            encargado_user.profile.save()

        self.stdout.write(self.style.SUCCESS("[OK] Usuarios de prueba creados (admin, cajero, encargado)"))

        # 5. Suplidores
        suppliers_data = [
            {"name": "Cerveceria Nacional Dominicana", "tax_id": "1-01-00012-3", "phone": "809-487-2000", "contact": "Alonso Diaz"},
            {"name": "MercaSID Dominicana", "tax_id": "1-01-00234-5", "phone": "809-565-2121", "contact": "Marcos Pena"},
            {"name": "Molinos del Ozama / Molinos Modernos", "tax_id": "1-01-00567-8", "phone": "809-221-5000", "contact": "Elena Suero"},
            {"name": "Induveca S.A.", "tax_id": "1-01-00987-1", "phone": "809-573-2000", "contact": "Roberto Gomez"},
            {"name": "Pasteurizadora Rica", "tax_id": "1-01-00444-9", "phone": "809-566-4141", "contact": "Sonia Rosario"},
        ]
        sup_dict = {}
        for s in suppliers_data:
            obj, _ = Supplier.objects.get_or_create(
                name=s['name'],
                defaults={'tax_id': s['tax_id'], 'phone': s['phone'], 'contact_person': s['contact']}
            )
            sup_dict[s['name']] = obj
        self.stdout.write(self.style.SUCCESS("[OK] Suplidores comerciales creados"))

        # 6. Categorias y Productos
        cat_bebidas, _ = Category.objects.get_or_create(name="Bebidas y Licores")
        cat_granos, _ = Category.objects.get_or_create(name="Arroz y Granos")
        cat_aceites, _ = Category.objects.get_or_create(name="Aceites y Condimentos")
        cat_enlatados, _ = Category.objects.get_or_create(name="Enlatados")
        cat_embutidos, _ = Category.objects.get_or_create(name="Lacteos y Embutidos")
        cat_viveres, _ = Category.objects.get_or_create(name="Panaderia y Viveres")
        cat_limpieza, _ = Category.objects.get_or_create(name="Limpieza del Hogar")
        cat_higiene, _ = Category.objects.get_or_create(name="Higiene Personal")
        cat_snacks, _ = Category.objects.get_or_create(name="Snacks y Golosinas")

        products_data = [
            # Bebidas (Unidad)
            {
                "name": "Cerveza Presidente Regular 650ml (Grande)",
                "code": "BEB-001",
                "barcode": "7461001001",
                "category": cat_bebidas,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('170.00'),
                "price": Decimal('225.00'),
                "stock": Decimal('48.000'),
                "min": Decimal('12.000'),
                "supplier": sup_dict.get("Cerveceria Nacional Dominicana"),
            },
            {
                "name": "Cerveza Presidente Light 355ml (Pequena)",
                "code": "BEB-002",
                "barcode": "7461001002",
                "category": cat_bebidas,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('115.00'),
                "price": Decimal('150.00'),
                "stock": Decimal('72.000'),
                "min": Decimal('24.000'),
                "supplier": sup_dict.get("Cerveceria Nacional Dominicana"),
            },
            {
                "name": "Ron Brugal Extra Viejo 700ml",
                "code": "BEB-003",
                "barcode": "7461001003",
                "category": cat_bebidas,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('590.00'),
                "price": Decimal('750.00'),
                "stock": Decimal('15.000'),
                "min": Decimal('4.000'),
                "supplier": sup_dict.get("Cerveceria Nacional Dominicana"),
            },
            {
                "name": "Refresco Country Club Frambuesa 2 Litros",
                "code": "BEB-004",
                "barcode": "7461001004",
                "category": cat_bebidas,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('75.00'),
                "price": Decimal('100.00'),
                "stock": Decimal('30.000'),
                "min": Decimal('8.000'),
                "supplier": sup_dict.get("Cerveceria Nacional Dominicana"),
            },
            {
                "name": "Botellon de Agua Dasani 5 Galones",
                "code": "BEB-005",
                "barcode": "7461001005",
                "category": cat_bebidas,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('65.00'),
                "price": Decimal('90.00'),
                "stock": Decimal('25.000'),
                "min": Decimal('6.000'),
                "supplier": sup_dict.get("Cerveceria Nacional Dominicana"),
            },
            # Embutidos y Lacteos (Fraccionados / Por Peso)
            {
                "name": "Queso Geo Holandes (por Libra)",
                "code": "EMB-001",
                "barcode": "7462001001",
                "category": cat_embutidos,
                "unit": UnitOfMeasure.LIBRA,
                "sale_type": SaleType.FRACTION,
                "cost": Decimal('230.00'),
                "price": Decimal('320.00'),
                "stock": Decimal('45.500'),
                "min": Decimal('10.000'),
                "supplier": sup_dict.get("Pasteurizadora Rica"),
            },
            {
                "name": "Salami Especial Induveca Mallita (por Libra)",
                "code": "EMB-002",
                "barcode": "7462001002",
                "category": cat_embutidos,
                "unit": UnitOfMeasure.LIBRA,
                "sale_type": SaleType.FRACTION,
                "cost": Decimal('110.00'),
                "price": Decimal('160.00'),
                "stock": Decimal('60.250'),
                "min": Decimal('15.000'),
                "supplier": sup_dict.get("Induveca S.A."),
            },
            {
                "name": "Leche Evaporada Carnation 315g",
                "code": "EMB-003",
                "barcode": "7462001003",
                "category": cat_embutidos,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('62.00'),
                "price": Decimal('80.00'),
                "stock": Decimal('48.000'),
                "min": Decimal('12.000'),
                "supplier": sup_dict.get("Pasteurizadora Rica"),
            },
            # Granos y Despensa
            {
                "name": "Arroz Selecto Campos 5 lbs",
                "code": "GRA-001",
                "barcode": "7463001001",
                "category": cat_granos,
                "unit": UnitOfMeasure.PAQUETE,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('195.00'),
                "price": Decimal('240.00'),
                "stock": Decimal('40.000'),
                "min": Decimal('10.000'),
                "supplier": sup_dict.get("Molinos del Ozama / Molinos Modernos"),
            },
            {
                "name": "Habichuelas Rojas Goya 15.5 oz",
                "code": "GRA-002",
                "barcode": "7463001002",
                "category": cat_granos,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('68.00'),
                "price": Decimal('90.00'),
                "stock": Decimal('36.000'),
                "min": Decimal('8.000'),
                "supplier": sup_dict.get("MercaSID Dominicana"),
            },
            {
                "name": "Aceite Crisol de Soya 64 oz (Medio Galon)",
                "code": "ACE-001",
                "barcode": "7464001001",
                "category": cat_aceites,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('275.00'),
                "price": Decimal('340.00'),
                "stock": Decimal('24.000'),
                "min": Decimal('6.000'),
                "supplier": sup_dict.get("MercaSID Dominicana"),
            },
            # Enlatados
            {
                "name": "Sardinas Paco Fish con Vegetales 155g",
                "code": "ENL-001",
                "barcode": "7465001001",
                "category": cat_enlatados,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('48.00'),
                "price": Decimal('65.00'),
                "stock": Decimal('50.000'),
                "min": Decimal('12.000'),
                "supplier": sup_dict.get("MercaSID Dominicana"),
            },
            # Viveres y Panaderia
            {
                "name": "Platano Verde Barahonero",
                "code": "VIV-001",
                "barcode": "7466001001",
                "category": cat_viveres,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('16.00'),
                "price": Decimal('25.00'),
                "stock": Decimal('120.000'),
                "min": Decimal('30.000'),
            },
            {
                "name": "Pan de Agua Criollo (Funda x 10 und)",
                "code": "VIV-002",
                "barcode": "7466001002",
                "category": cat_viveres,
                "unit": UnitOfMeasure.PAQUETE,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('60.00'),
                "price": Decimal('80.00'),
                "stock": Decimal('20.000'),
                "min": Decimal('5.000'),
            },
            # Limpieza y Hogar
            {
                "name": "Cloro Macier Tradicional 1 Galon",
                "code": "LIM-001",
                "barcode": "7467001001",
                "category": cat_limpieza,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('110.00'),
                "price": Decimal('150.00'),
                "stock": Decimal('18.000'),
                "min": Decimal('4.000'),
            },
            {
                "name": "Jabon de Cuaba La Llave 250g",
                "code": "LIM-002",
                "barcode": "7467001002",
                "category": cat_limpieza,
                "unit": UnitOfMeasure.UNIDAD,
                "sale_type": SaleType.UNIT,
                "cost": Decimal('35.00'),
                "price": Decimal('50.00'),
                "stock": Decimal('40.000'),
                "min": Decimal('10.000'),
            },
        ]

        for p in products_data:
            Product.objects.update_or_create(
                internal_code=p['code'],
                defaults={
                    'name': p['name'],
                    'barcode': p['barcode'],
                    'category': p['category'],
                    'unit_of_measure': p['unit'],
                    'sale_type': p['sale_type'],
                    'cost_price': p['cost'],
                    'sale_price': p['price'],
                    'current_stock': p['stock'],
                    'min_stock': p['min'],
                    'supplier': p.get('supplier'),
                    'is_active': True,
                }
            )
        self.stdout.write(self.style.SUCCESS(f"[OK] {len(products_data)} Productos de colmado dominicano creados"))

        # 7. Clientes de la Libreta de Fiados
        customers_data = [
            {"name": "Dona Carmen Santana", "phone": "8095551020", "id": "001-0897451-2", "address": "Casa #12, Calle 3ra", "limit": Decimal('4000.00')},
            {"name": "Don Ramon Almonte", "phone": "8295553040", "id": "001-1456987-9", "address": "Edif. Los Pinos, Apto 2A", "limit": Decimal('5000.00')},
            {"name": "Lic. Maria Fernandez", "phone": "8495557080", "id": "001-0523147-8", "address": "Residencial Las Palmas #4B", "limit": Decimal('6000.00')},
            {"name": "Pedro Martinez (El Taller)", "phone": "8095559090", "id": "001-1897456-3", "address": "Callejon La Fe #8", "limit": Decimal('2500.00')},
        ]
        for c in customers_data:
            Customer.objects.update_or_create(
                phone=c['phone'],
                defaults={
                    'name': c['name'],
                    'identification': c['id'],
                    'address': c['address'],
                    'credit_limit': c['limit'],
                    'is_active': True,
                }
            )
        self.stdout.write(self.style.SUCCESS("[OK] Clientes de libreta de fiados creados"))

        # 8. Caja Fisica y Turno Activo de Apertura
        caja_princ, _ = CashRegister.objects.get_or_create(
            code='CAJA-01',
            defaults={'name': 'Caja Principal - Mostrador', 'is_active': True}
        )

        open_shift = CashShift.objects.filter(register=caja_princ, status=CashShiftStatus.ABIERTO).first()
        if not open_shift:
            open_shift = CashShift.objects.create(
                register=caja_princ,
                cashier=admin_user,
                initial_cash=Decimal('2500.00'),
                status=CashShiftStatus.ABIERTO,
                initial_notes="Fondo inicial de apertura demostrativa RD$ 2,500 en menudo",
            )
            CashMovement.objects.create(
                shift=open_shift,
                movement_type=CashMovementType.INGRESO,
                category='FONDO_INICIAL',
                amount=Decimal('2500.00'),
                description="Fondo de cambio inicial",
                user=admin_user,
            )
            self.stdout.write(self.style.SUCCESS(f"[OK] Turno de caja #{open_shift.id} abierto con fondo RD$ 2,500"))
        else:
            self.stdout.write(self.style.NOTICE(f"[INFO] Ya existe un turno activo (#{open_shift.id})"))

        self.stdout.write(self.style.SUCCESS("\n==> Datos demostrativos de ColmadoPOS instalados con exito!"))
        self.stdout.write(self.style.SUCCESS("Credenciales de acceso:"))
        self.stdout.write("  - Administrador: admin / admin123")
        self.stdout.write("  - Cajero:        cajero / cajero123")
        self.stdout.write("  - Encargado:     encargado / encargado123")

