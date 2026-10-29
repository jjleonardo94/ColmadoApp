# ColmadoPOS - Sistema Integral de Gestión para Colmados y Minimarkets

ColmadoPOS es una aplicación web full-stack de punto de venta (POS), inventario Kardex, libreta de fiados (cuentas por cobrar), control de turnos y arqueo de caja física por denominaciones dominicanas, compras a suplidores, reportes de rentabilidad basados en costos históricos reales e integración oficial con la API en la nube de WhatsApp Business (Meta Cloud API).

Desarrollada con **Django 5**, **PostgreSQL 17**, **Tailwind CSS**, **Lucide Icons** y **JavaScript (Fetch API)**, adaptada a la dinámica comercial de la República Dominicana.

---

## 🚀 Características Principales

### 1. Punto de Venta Rápido (POS)
- Búsqueda en tiempo real por nombre, código interno o código de barras (lector USB / escáner).
- Soporte para **Ventas por Unidad** y **Ventas Fraccionadas** (libras, kilos, onzas).
- **Venta por Monto**: permite vender un importe en dinero calculando automáticamente la cantidad decimal correspondiente.
- **Pagos Mixtos y Múltiples**: combinación de Efectivo, Tarjeta, Transferencia y Fiado en una misma venta.
- **Multimoneda**: peso dominicano (DOP/RD$), dólar estadounidense (USD) y euro (EUR) con conversión automática y registro de tasa histórica.
- **Atajos de Teclado**:
  - `F1`: Efectivo rápido.
  - `F2`: Venta a Crédito / Fiado.
  - `F3`: Foco en barra de búsqueda de productos.
  - `F4`: Selector de cliente.
  - `Esc`: Cerrar modales.
- **Recibos Térmicos**: formato estándar para impresoras térmicas de 58 mm y 80 mm (compatibles con ESC/POS mediante impresión de navegador).
- **Anulaciones y Devoluciones**: autorización restringida por permisos y registro inmutable en auditoría.

### 2. Libreta de Fiados (Cuentas por Cobrar)
- Control de límite de crédito por cliente con bloqueo automático si la deuda excede el límite.
- Cálculo dinámico del saldo en tiempo real (`Cargos - Abonos`) para evitar manipulación manual arbitraria.
- Registro de abonos parciales o liquidaciones totales: al recibir un abono en efectivo, el dinero se ingresa automáticamente al turno de caja abierto para mantener el cuadre exacto.
- Generador de extractos de cuenta formateados para envío por WhatsApp.

### 3. Caja, Turnos y Arqueo Físico de Denominaciones
- Control por cajero y caja física.
- Formulario de arqueo físico con denominaciones de la República Dominicana:
  - **Monedas**: RD$ 2, RD$ 5, RD$ 10, RD$ 25, RD$ 50.
  - **Billetes**: RD$ 50, RD$ 100, RD$ 200, RD$ 500, RD$ 1,000, RD$ 2,000.
- Cálculo automático de efectivo esperado (`Fondo Inicial + Entradas - Salidas`) y cálculo de diferencias (sobrante o faltante).
- Si existe diferencia de caja, el sistema exige obligatoriamente una justificación detallada antes de cerrar el turno.
- Los turnos cerrados quedan sellados e inmutables.

### 4. Inventario Kardex y Alertas de Stock
- Trazabilidad completa: entradas por compras, salidas por ventas, ajustes manuales y devoluciones.
- Bloqueo de existencias pesimista (`select_for_update`) a nivel de base de datos para evitar doble gasto o existencias inconsistentes.
- Política de inventario negativo desactivada por defecto.
- Alertas en tiempo real de productos bajo el stock mínimo y productos agotados.

### 5. Compras y Suplidores
- Registro de suplidores comerciales (RNC, teléfono, vendedor).
- Facturas de compra con múltiples renglones.
- **Idempotencia de Recepción**: la confirmación de mercancía recibida actualiza el stock una sola vez, protegiendo el inventario ante reintentos.

### 6. Gastos Operativos
- Clasificación por rubros: alquiler, electricidad (Edeeste/Edesur), agua, transporte, sueldos, mantenimiento.
- Los gastos pagados en efectivo se vinculan al turno de caja activo, reduciendo el efectivo esperado en gaveta.

### 7. Reportes Financieros y Ganancias Reales
- **Ganancia Bruta Real**: calculada restando el costo unitario histórico que tenía el producto al momento de emitirse cada ticket, no el costo actual si este sube posteriormente.
- **Ganancia Operativa Neta Estimada**: Ganancia Bruta menos Gastos Operativos pagados en el período.
- Desglose por categorías, métodos de pago y productos de mayor rotación.
- Exportación directa a formatos **CSV** y **Excel (.xlsx)**.

### 8. Integración Oficial con WhatsApp Business API
- Webhook público con validación del apretón de manos oficial de Meta (`hub.mode`, `hub.verify_token`, `hub.challenge`).
- Validación opcional de firma SHA-256 (`X-Hub-Signature-256`) con secreto de app (`WHATSAPP_APP_SECRET`).
- Deduplicación estricta de mensajes entrantes mediante el identificador único `wamid` de Meta.
- Bandeja de entrada integrada con chat bidireccional y estados de entrega (`sent`, `delivered`, `read`).
- **Automatización Segura de Intenciones**:
  - Detección de mensajes como *"¿Cuánto debo?"* o *"Mi saldo"*: responde automáticamente con el estado de cuenta si el número de WhatsApp está verificado y vinculado a un cliente.
  - Detección de avisos de pago (*"Ya pagué"*, *"Hice la transferencia"*): notifica al cajero y cambia la conversación a pendiente de atención humana. Nunca confirma un pago de forma autónoma sin verificación física.
  - Detección de solicitud de encargado (*"Encargado"*, *"Ayuda"*).

### 9. Seguridad, Roles y Auditoría
- Roles predefinidos: **ADMIN**, **ENCARGADO**, **CAJERO**, **INVENTARIO**, **COMPRAS**, **CONSULTA**.
- Permisos granulares verificados en el servidor para descuentos, ventas fiadas, anulaciones, ajustes de inventario y configuración.
- Bitácora de auditoría inmutable que registra usuario, acción, entidad, fecha/hora y dirección IP.

---

## 🛠️ Requisitos Previos en Windows

1. **Python 3.12+** instalado y agregado al PATH de Windows (`python --version`).
2. **PostgreSQL 17+** instalado y corriendo como servicio en Windows (`localhost:5432`).
3. **pgAdmin 4** (incluido habitualmente en la instalación oficial de PostgreSQL).

---

## 📦 Guía de Instalación Paso a Paso en Windows

### Paso 1: Clonar o Situarse en el Directorio del Proyecto
Abra PowerShell o CMD en la carpeta del proyecto:
```powershell
cd C:\Users\jleonardo\.gemini\antigravity-ide\scratch\colmadopos
```

### Paso 2: Crear la Base de Datos en PostgreSQL
Puede crearla desde la línea de comandos con `psql`:
```powershell
psql -U postgres -h localhost -c "CREATE DATABASE colmadopos_db ENCODING 'UTF8';"
```
*(O créela gráficamente en pgAdmin 4: clic derecho en `Databases` > `Create` > `Database...` > Nombre: `colmadopos_db`).*

### Paso 3: Configurar el Archivo de Variables de Entorno (`.env`)
Copie el archivo de ejemplo:
```powershell
copy .env.example .env
```
Abra `.env` y verifique sus credenciales locales de PostgreSQL:
```ini
DEBUG=True
SECRET_KEY=colmadopos-produccion-local-super-secreta-2026-rd-pos
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=colmadopos_db
DB_USER=postgres
DB_PASSWORD=SuPasswordDePostgres
DB_HOST=localhost
DB_PORT=5432

# WhatsApp Business API (Meta Cloud API)
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=colmadopos_secret_verify_token_2026
WHATSAPP_APP_SECRET=
```

### Paso 4: Instalar las Dependencias de Python
```powershell
pip install -r requirements.txt
```

### Paso 5: Ejecutar las Migraciones de la Base de Datos
```powershell
python manage.py migrate
```

### Paso 6: Cargar Datos de Demostración del Colmado
Ejecute el comando de inicialización de prueba:
```powershell
python manage.py seed_colmado_demo
```
Este comando cargará automáticamente:
- Configuración de negocio: *Colmado El Progreso* (RNC 1-31-89745-2).
- Catálogo de 11 denominaciones dominicanas (monedas y billetes).
- 9 categorías de gastos operativos.
- 5 suplidores dominicanos (Cervecería Nacional, MercaSID, Molinos del Ozama, Induveca, Rica).
- 16 productos típicos dominicanos con stock inicial y costos reales.
- 4 clientes de prueba con líneas de crédito.
- 3 usuarios operativos listos para usar.
- Turno #1 abierto en Caja 1 con RD$ 2,500 de fondo inicial.

### Paso 7: Iniciar el Servidor de Desarrollo
```powershell
python manage.py runserver
```
Abra su navegador web e ingrese a:
👉 **http://127.0.0.1:8000**

---

## 👥 Credenciales de Acceso de Demostración

| Usuario | Contraseña | Rol | Acceso y Permisos |
|---|---|---|---|
| **admin** | `admin123` | Administrador / Propietario | Control total, reportes, usuarios, bitácora y configuración. |
| **encargado** | `encargado123` | Encargado de Tienda | Ventas, compras, libreta de fiados, arqueos de caja y anulaciones. |
| **cajero** | `cajero123` | Cajero de Mostrador | Punto de venta (POS), cobros en efectivo/tarjeta y arqueo físico. |

*(Para crear un superusuario personalizado adicional, ejecute `python manage.py createsuperuser`).*

---

## 🗄️ Conexión y Gestión con pgAdmin 4

Para inspeccionar o administrar la base de datos visualmente desde **pgAdmin 4**:
1. Abra **pgAdmin 4** en Windows.
2. Inicie sesión con la contraseña maestra de PostgreSQL.
3. En el árbol izquierdo, expanda `Servers` > `PostgreSQL 17`.
4. Expanda `Databases` > localice `colmadopos_db`.
5. Expanda `Schemas` > `public` > `Tables`.
6. Encontrará las tablas del sistema:
   - `catalog_product`: productos, precios y existencias.
   - `sales_sale` y `sales_saleitem`: transacciones y recibos con costos históricos.
   - `customers_customer` y `customers_credittransaction`: libreta de fiados.
   - `cash_cashshift` y `cash_cashmovement`: turnos de caja y arqueos.
   - `whatsapp_whatsappmessage`: historial de mensajería y webhooks.
   - `core_auditlog`: trazabilidad de operaciones críticas.

---

## 🖨️ Configuración de Impresoras Térmicas (58 mm y 80 mm)

1. En el módulo de **Punto de Venta (POS)**, tras completar una venta o desde la lista de ventas, presione **"Imprimir Ticket"**.
2. Se abrirá la vista optimizada de recibo térmico con tipografía monoespaciada de alta legibilidad.
3. Presione el botón **"Imprimir Ticket"** o `Ctrl + P`.
4. En el cuadro de diálogo de impresión de Windows / navegador:
   - Seleccione su impresora térmica (ej. Xprinter, Epson TM-T20, POS-58 / POS-80).
   - En tamaño de papel, elija **58mm** o **80mm** (según lo configurado en *Ajustes del Negocio*).
   - En Márgenes, seleccione **"Ninguno"** o **"Mínimos"**.
   - Desmarque la casilla *"Encabezados y pies de página"* del navegador.

---

## 💬 Configuración Oficial de Meta WhatsApp Business Cloud API

Para conectar ColmadoPOS con un número oficial de WhatsApp Business:

1. **Crear una App en Meta for Developers**:
   - Ingrese a [developers.facebook.com](https://developers.facebook.com) e inicie sesión con su cuenta de Meta.
   - Cree una nueva App empresarial de tipo **Business**.
   - Agregue el producto **WhatsApp**.

2. **Obtener Credenciales de la API**:
   - En la sección **WhatsApp > API Setup**:
     - Copie el **Phone number ID**.
     - Copie el **WhatsApp Business Account ID (WABA ID)**.
     - Genere un **Permanent System User Access Token** en *Meta Business Settings*.

3. **Configurar el Webhook**:
   - Para exponer su servidor local en Windows a HTTPS público durante el desarrollo, inicie un túnel seguro:
     ```powershell
     # Ejemplo con ngrok o Cloudflare
     ngrok http 8000
     ```
   - En Meta Developers > WhatsApp > Configuration > Webhook:
     - **Callback URL**: `https://su-dominio-o-tunel.ngrok-free.app/whatsapp/webhook/`
     - **Verify Token**: Coloque el valor exacto configurado en su `.env` (por defecto `colmadopos_secret_verify_token_2026`).
     - Haga clic en **Verify and Save**.
     - En Webhook fields, suscríbase a **`messages`**.

4. **Completar el `.env`**:
   - Guarde los valores obtenidos en su archivo `.env` y reinicie el servidor de desarrollo.
   - Desde el módulo **WhatsApp > Configuración** en la app podrá verificar el estado de conexión y consultar los parámetros activos.

---

## 🧪 Ejecución de Pruebas Automatizadas

La aplicación cuenta con una suite completa de pruebas unitarias y de integración que validan todas las reglas de negocio sobre PostgreSQL:
```powershell
python manage.py test tests
```

### Procesos Validados en la Suite:
- `test_login_and_role_permissions`: autenticación, perfiles y control de acceso.
- `test_product_unit_vs_fractional_sale`: prohibición de decimales en productos por unidad.
- `test_sale_creation_and_inventory_deduction`: descuento atómico de stock y generación de Kardex.
- `test_prevent_negative_inventory_when_disabled`: bloqueo transaccional de ventas por falta de existencia.
- `test_combined_multi_payment`: pagos mixtos (efectivo + transferencia bancaria).
- `test_fiado_sale_and_credit_limit_enforcement`: validación estricta de cupo de fiado por cliente.
- `test_customer_abono_registration_and_cash_shift_impact`: reducción de deuda e ingreso a caja.
- `test_cash_shift_closing_and_difference_calculation`: arqueo por billetes/monedas y bloqueo tras cierre.
- `test_operational_expense_linked_to_shift`: gastos pagados desde gaveta.
- `test_real_profit_calculation_using_historical_cost`: cálculo de margen con costo de venta histórico.
- `test_purchase_reception_idempotency`: entrada de compras sin duplicidad.
- `test_whatsapp_webhook_verification`: handshake oficial GET `hub.challenge`.
- `test_whatsapp_message_deduplication_and_intent`: deduplicación por `wamid` y reconocimiento de intención de saldo.

---

## 💾 Respaldo y Restauración de Base de Datos

### Crear una Copia de Seguridad (Backup)
```powershell
pg_dump -U postgres -h localhost -F c -b -v -f "backup_colmadopos_%date:~-4,4%%date:~-7,2%%date:~-10,2%.dump" colmadopos_db
```

### Restaurar una Copia de Seguridad
```powershell
# Crear base de datos limpia si no existe
psql -U postgres -h localhost -c "DROP DATABASE IF EXISTS colmadopos_db;"
psql -U postgres -h localhost -c "CREATE DATABASE colmadopos_db ENCODING 'UTF8';"

# Restaurar datos
pg_restore -U postgres -h localhost -d colmadopos_db -v "backup_colmadopos_YYYYMMDD.dump"
```

---

## 🏛️ Estructura del Proyecto

```
colmadopos/
├── apps/
│   ├── accounts/     # Perfiles, roles dominicanos (Admin, Encargado, Cajero) y permisos
│   ├── audit/        # Bitácora inmutable de eventos sensibles
│   ├── cash/         # Turnos de caja, fondo inicial, arqueo físico y denominaciones RD$
│   ├── catalog/      # Categorías, productos por unidad y fraccionados, códigos de barra
│   ├── core/         # Configuración del negocio, dashboard y comando demo seed
│   ├── customers/    # Clientes, libreta de fiados y extractos para WhatsApp
│   ├── expenses/     # Categorías de gastos y vinculación con caja física
│   ├── inventory/    # Kardex, movimientos transaccionales y alertas de stock
│   ├── purchasing/   # Suplidores, compras e ingreso de mercancía idempotente
│   ├── reports/      # Ganancia bruta histórica, reportes y exportación Excel/CSV
│   ├── sales/        # Motor del POS, pagos combinados, multimoneda y tickets térmicos
│   └── whatsapp/     # Webhooks oficiales de Meta, bandeja y motor de intenciones
├── config/           # Configuración principal Django (settings, urls, wsgi)
├── static/           # Archivos CSS y JavaScript
├── templates/        # Plantillas HTML5 con Tailwind CSS
├── tests/            # Suite de pruebas automatizadas
├── .env.example      # Plantilla de variables de entorno
├── manage.py         # Punto de entrada Django
└── requirements.txt  # Dependencias del proyecto
```

---

## 📜 Licencia y Derechos

Desarrollado para colmados, minimarkets y bodegas en la República Dominicana. Todos los cálculos financieros se manejan con precisión decimal monetaria (`DecimalField`), transacciones atómicas con bloqueo pesimista y cumplimiento de normativas fiscales dominicanas (RNC / Comprobantes).
