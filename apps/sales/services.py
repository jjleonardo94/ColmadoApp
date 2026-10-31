import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
import uuid
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

from apps.catalog.models import Product, SaleType
from apps.core.models import BusinessSettings, AuditLog
from apps.customers.models import Customer, CreditTransaction, CreditTransactionType
from apps.customers.services import CustomerCreditService
from apps.cash.models import CashShift, CashMovement, CashMovementType
from apps.inventory.services import InventoryService
from apps.inventory.models import MovementType
from apps.sales.models import (
    Sale, SaleItem, Payment, SaleStatus, PaymentMethodChoices,
    DeliveryPerson, DeliveryOrder, DeliveryStatus
)


class ReceiptImageGenerator:
    """
    Genera una imagen PNG nítida estilo ticket térmico (80mm) con la información
    oficial del colmado activo, lista para enviarse por WhatsApp.
    """
    @staticmethod
    def get_font(size, bold=False):
        paths = []
        if bold:
            paths = [
                'C:/Windows/Fonts/consolab.ttf',
                'C:/Windows/Fonts/courbd.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf'
            ]
        else:
            paths = [
                'C:/Windows/Fonts/consola.ttf',
                'C:/Windows/Fonts/cour.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf'
            ]
        for p in paths:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    @classmethod
    def generate_receipt_image(cls, sale) -> str:
        branch = sale.branch
        b_settings = BusinessSettings.get_settings()
        
        colmado_name = (branch.name if branch else b_settings.name) or 'COLMADO'
        rnc = (branch.rnc if branch else b_settings.rnc) or '1-31-00745-2'
        phone = (branch.phone if branch else b_settings.phone) or ''
        address = (branch.address if branch else b_settings.address) or ''
        
        now_str = timezone.localtime(sale.created_at).strftime('%d/%m/%Y %I:%M %p')
        cajero = sale.cashier.get_full_name() or sale.cashier.username if sale.cashier else 'Cajero'
        cliente = sale.customer.name if sale.customer else None

        f_title = cls.get_font(20, bold=True)
        f_header = cls.get_font(13, bold=False)
        f_body = cls.get_font(13, bold=False)
        f_body_bold = cls.get_font(13, bold=True)
        f_small = cls.get_font(11, bold=False)
        f_total = cls.get_font(17, bold=True)
        f_sep = cls.get_font(12, bold=False)

        width = 460
        y = 25
        y += 28 # Title
        if rnc: y += 18
        if phone: y += 18
        if address:
            addr_lines = textwrap.wrap(address, width=38)
            y += len(addr_lines) * 16
        y += 15
        y += 18 # Separator
        y += 18 # TICKET
        y += 18 # FECHA
        y += 18 # CAJERO
        if cliente: y += 18 # CLIENTE
        y += 15 # Separator
        y += 20 # Header CANT. ARTICULO
        y += 10 # Dotted line

        items = list(sale.items.select_related('product').all())
        for it in items:
            y += 20
            y += 16
            if it.discount > Decimal('0.00'):
                y += 16
            y += 6

        y += 15 # Separator
        y += 18 # SUBTOTAL
        if sale.discount > Decimal('0.00'):
            y += 18
        y += 28 # TOTAL A PAGAR
        y += 15 # Separator

        payments = list(sale.payments.all())
        for p in payments:
            y += 18
            y += 18
        if not payments:
            y += 18
            y += 18

        y += 20 # CAMBIO
        y += 15 # Separator
        y += 24 # Gracias por comprar en...
        y += 20 # *** GRACIAS POR PREFERIRNOS ***
        y += 35 # Bottom padding

        height = y

        img = Image.new('RGB', (width, height), color='#FFFFFF')
        draw = ImageDraw.Draw(img)
        draw.rectangle([(2, 2), (width - 3, height - 3)], outline='#E2E8F0', width=1)

        cur_y = 25
        draw.text((width / 2, cur_y), colmado_name.upper(), fill='#0F172A', font=f_title, anchor='mm')
        cur_y += 22

        if rnc:
            draw.text((width / 2, cur_y), f"RNC: {rnc}", fill='#334155', font=f_header, anchor='mm')
            cur_y += 18

        if phone:
            draw.text((width / 2, cur_y), f"Tel: {phone}", fill='#334155', font=f_header, anchor='mm')
            cur_y += 18

        if address:
            for line in textwrap.wrap(address, width=38):
                draw.text((width / 2, cur_y), line, fill='#475569', font=f_small, anchor='mm')
                cur_y += 15
            cur_y += 4

        sep_line = "- " * 27
        draw.text((width / 2, cur_y), sep_line, fill='#94A3B8', font=f_sep, anchor='mm')
        cur_y += 14

        margin_l = 28
        margin_r = width - 28

        draw.text((margin_l, cur_y), "TICKET:", fill='#334155', font=f_body)
        draw.text((margin_r, cur_y), sale.ticket_number, fill='#0F172A', font=f_body_bold, anchor='ra')
        cur_y += 18

        draw.text((margin_l, cur_y), "FECHA:", fill='#334155', font=f_body)
        draw.text((margin_r, cur_y), now_str, fill='#0F172A', font=f_body, anchor='ra')
        cur_y += 18

        draw.text((margin_l, cur_y), "CAJERO:", fill='#334155', font=f_body)
        draw.text((margin_r, cur_y), cajero, fill='#0F172A', font=f_body, anchor='ra')
        cur_y += 18

        if cliente:
            draw.text((margin_l, cur_y), "CLIENTE:", fill='#334155', font=f_body_bold)
            draw.text((margin_r, cur_y), cliente, fill='#0F172A', font=f_body_bold, anchor='ra')
            cur_y += 18

        draw.text((width / 2, cur_y), sep_line, fill='#94A3B8', font=f_sep, anchor='mm')
        cur_y += 14

        draw.text((margin_l, cur_y), "CANT. ARTICULO", fill='#0F172A', font=f_body_bold)
        draw.text((margin_r, cur_y), "IMPORTE", fill='#0F172A', font=f_body_bold, anchor='ra')
        cur_y += 18

        draw.text((width / 2, cur_y), ". " * 27, fill='#CBD5E1', font=f_sep, anchor='mm')
        cur_y += 10

        for it in items:
            p_name = it.product.name
            if len(p_name) > 24:
                p_name = p_name[:23] + '…'
            draw.text((margin_l, cur_y), p_name, fill='#0F172A', font=f_body_bold)
            draw.text((margin_r, cur_y), f"RD$ {it.subtotal:,.2f}", fill='#0F172A', font=f_body_bold, anchor='ra')
            cur_y += 16

            detail = f"{it.quantity:g} x RD$ {it.unit_price:,.2f}"
            draw.text((margin_l + 8, cur_y), detail, fill='#64748B', font=f_small)
            cur_y += 16

            if it.discount > Decimal('0.00'):
                draw.text((margin_r, cur_y - 16), f"-Desc: RD$ {it.discount:,.2f}", fill='#E11D48', font=f_small, anchor='ra')

            cur_y += 4

        draw.text((width / 2, cur_y), sep_line, fill='#94A3B8', font=f_sep, anchor='mm')
        cur_y += 14

        draw.text((margin_l, cur_y), "SUBTOTAL:", fill='#334155', font=f_body)
        draw.text((margin_r, cur_y), f"RD$ {sale.subtotal:,.2f}", fill='#0F172A', font=f_body, anchor='ra')
        cur_y += 18

        if sale.discount > Decimal('0.00'):
            draw.text((margin_l, cur_y), "DESCUENTO:", fill='#E11D48', font=f_body)
            draw.text((margin_r, cur_y), f"-RD$ {sale.discount:,.2f}", fill='#E11D48', font=f_body, anchor='ra')
            cur_y += 18

        draw.text((margin_l, cur_y), "TOTAL A PAGAR:", fill='#0F172A', font=f_total)
        draw.text((margin_r, cur_y), f"RD$ {sale.total:,.2f}", fill='#0F172A', font=f_total, anchor='ra')
        cur_y += 24

        draw.text((width / 2, cur_y), sep_line, fill='#94A3B8', font=f_sep, anchor='mm')
        cur_y += 14

        if payments:
            for p in payments:
                draw.text((margin_l, cur_y), "FORMA DE PAGO:", fill='#334155', font=f_body)
                draw.text((margin_r, cur_y), p.get_payment_method_display(), fill='#0F172A', font=f_body_bold, anchor='ra')
                cur_y += 18

                draw.text((margin_l, cur_y), "MONTO ABONADO:", fill='#334155', font=f_body)
                draw.text((margin_r, cur_y), f"RD$ {p.amount:,.2f}", fill='#0F172A', font=f_body, anchor='ra')
                cur_y += 18
        else:
            draw.text((margin_l, cur_y), "FORMA DE PAGO:", fill='#334155', font=f_body)
            draw.text((margin_r, cur_y), sale.get_payment_method_display(), fill='#0F172A', font=f_body_bold, anchor='ra')
            cur_y += 18

            draw.text((margin_l, cur_y), "MONTO ABONADO:", fill='#334155', font=f_body)
            draw.text((margin_r, cur_y), f"RD$ {sale.total:,.2f}", fill='#0F172A', font=f_body, anchor='ra')
            cur_y += 18

        draw.text((margin_l, cur_y), "CAMBIO / DEVUELTA:", fill='#0F172A', font=f_body_bold)
        draw.text((margin_r, cur_y), f"RD$ {sale.change_given:,.2f}", fill='#0F172A', font=f_body_bold, anchor='ra')
        cur_y += 20

        draw.text((width / 2, cur_y), sep_line, fill='#94A3B8', font=f_sep, anchor='mm')
        cur_y += 16

        draw.text((width / 2, cur_y), f"Gracias por comprar en {colmado_name}", fill='#334155', font=f_body, anchor='mm')
        cur_y += 18
        draw.text((width / 2, cur_y), "*** GRACIAS POR PREFERIRNOS ***", fill='#64748B', font=f_small, anchor='mm')

        media_dir = os.path.join(settings.MEDIA_ROOT, 'receipts')
        os.makedirs(media_dir, exist_ok=True)
        filename = f"{sale.ticket_number}.png"
        filepath = os.path.join(media_dir, filename)
        img.save(filepath, 'PNG')
        return f"receipts/{filename}"


class SaleService:
    @staticmethod
    def generate_ticket_number() -> str:
        date_str = timezone.now().strftime('%Y%m%d')
        random_suffix = str(uuid.uuid4().hex[:6]).upper()
        count = Sale.objects.filter(created_at__date=timezone.now().date()).count() + 1
        return f"TICK-{date_str}-{count:04d}-{random_suffix}"

    @classmethod
    @transaction.atomic
    def create_sale(
        cls,
        cashier,
        items_data: list,
        payments_data: list,
        customer_id: int = None,
        received_currency: str = 'DOP',
        amount_received: Decimal = Decimal('0.00'),
        notes: str = '',
        cash_shift_id: int = None,
        branch=None,
        branch_id: int = None,
        origin: str = 'POS',
        whatsapp_conversation = None,
    ) -> Sale:
        """
        Crea una venta con validaciones estrictas del lado del servidor,
        bloqueo pesimista de stock, registro en caja, soporte para pagos mixtos y créditos.
        """
        if not items_data:
            raise ValidationError("La venta debe contener al menos un producto.")
        if not payments_data:
            raise ValidationError("Debe especificar al menos un método de pago.")

        settings = BusinessSettings.get_settings()
        from apps.core.models import ColmadoBranch
        
        # 1. Obtener turno de caja abierto
        shift = None
        if cash_shift_id:
            shift = CashShift.objects.filter(id=cash_shift_id, status='ABIERTO').first()
        if not shift:
            shift = CashShift.objects.filter(cashier=cashier, status='ABIERTO').first()
        if not shift:
            shift = CashShift.objects.filter(status='ABIERTO').first()

        # Determinar Sucursal
        branch_obj = None
        if branch_id:
            branch_obj = ColmadoBranch.objects.filter(id=branch_id, is_active=True).first()
        elif branch:
            branch_obj = branch
        elif shift and shift.branch:
            branch_obj = shift.branch
        elif hasattr(cashier, 'profile'):
            allowed = cashier.profile.get_allowed_branches()
            branch_obj = allowed.first() if hasattr(allowed, 'first') else (allowed[0] if allowed else None)
        if not branch_obj:
            branch_obj = ColmadoBranch.get_default_branch()

        # 2. Cliente (si aplica)
        customer = None
        if customer_id:
            try:
                customer = Customer.objects.select_for_update().get(pk=customer_id)
            except Customer.DoesNotExist:
                raise ValidationError("El cliente seleccionado no existe.")

        # 3. Validar y procesar productos (con select_for_update)
        ticket_num = cls.generate_ticket_number()
        total_subtotal = Decimal('0.00')
        total_discount = Decimal('0.00')
        processed_items = []

        for item_data in items_data:
            prod_id = item_data.get('product_id')
            raw_qty = Decimal(str(item_data.get('quantity', '1')))
            item_discount = Decimal(str(item_data.get('discount', '0.00')))

            if raw_qty <= Decimal('0.000'):
                raise ValidationError("La cantidad de cada producto debe ser mayor que cero.")

            # Soporte para artículos genéricos o pedidos manuales de WhatsApp
            if not prod_id or str(prod_id).upper() in ['CUSTOM', 'GENERIC', '0', 'NONE']:
                custom_name = item_data.get('name') or "Pedido WhatsApp / Venta Rápida"
                custom_price = Decimal(str(item_data.get('unit_price') or item_data.get('price') or '0.00'))
                from apps.catalog.models import Category, UnitOfMeasure
                cat_gen, _ = Category.objects.get_or_create(name='General')
                product, _ = Product.objects.get_or_create(
                    internal_code='PROD-GENERICO',
                    defaults={
                        'name': custom_name,
                        'category': cat_gen,
                        'sale_price': custom_price,
                        'cost_price': Decimal('0.00'),
                        'current_stock': Decimal('99999.000'),
                        'sale_type': SaleType.UNIT,
                        'unit_of_measure': UnitOfMeasure.UNIDAD,
                        'is_active': True,
                    }
                )
                unit_price = custom_price if custom_price > Decimal('0.00') else product.sale_price
                unit_cost = product.cost_price
            else:
                try:
                    product = Product.objects.select_for_update().get(pk=prod_id, is_active=True)
                except Product.DoesNotExist:
                    raise ValidationError(f"El producto con ID {prod_id} no existe o está inactivo.")

                # Validación de unidades enteras vs peso/fracción
                if product.sale_type == SaleType.UNIT:
                    if raw_qty % Decimal('1.000') != Decimal('0.000'):
                        raise ValidationError(
                            f"El producto '{product.name}' se vende únicamente por unidad completa, no admite decimales."
                        )

                # Validación de stock
                if not settings.allow_negative_stock and product.current_stock < raw_qty:
                    raise ValidationError(
                        f"Stock insuficiente para '{product.name}'. Disponible: {product.current_stock}, Solicitado: {raw_qty}."
                    )

                unit_price = product.sale_price
                unit_cost = product.cost_price

            line_gross = raw_qty * unit_price
            if item_discount > line_gross:
                raise ValidationError(f"El descuento de '{product.name}' no puede superar el total de la línea.")

            line_net = line_gross - item_discount
            total_subtotal += line_gross
            total_discount += item_discount

            processed_items.append({
                'product': product,
                'quantity': raw_qty,
                'unit_price': unit_price,
                'unit_cost': unit_cost,
                'discount': item_discount,
                'subtotal': line_net,
            })

        sale_total = total_subtotal - total_discount

        # 4. Validar pagos
        total_payments_amount = Decimal('0.00')
        has_cash = False
        cash_paid_amount = Decimal('0.00')
        has_fiado = False
        fiado_amount = Decimal('0.00')
        payment_methods_used = set()

        for p_data in payments_data:
            p_method = p_data.get('method') or p_data.get('payment_method')
            p_amount = Decimal(str(p_data.get('amount', '0.00')))
            p_ref = p_data.get('reference', '')

            if p_amount <= Decimal('0.00'):
                raise ValidationError("Los montos de pago deben ser mayores a cero.")

            payment_methods_used.add(p_method)
            total_payments_amount += p_amount

            if p_method == PaymentMethodChoices.EFECTIVO:
                has_cash = True
                cash_paid_amount += p_amount
            elif p_method == PaymentMethodChoices.FIADO:
                has_fiado = True
                fiado_amount += p_amount

        # Validar cuadre de pagos vs total de la venta
        if abs(total_payments_amount - sale_total) > Decimal('0.05'):
            raise ValidationError(
                f"El total pagado (RD$ {total_payments_amount:,.2f}) no coincide con el total de la venta (RD$ {sale_total:,.2f})."
            )

        # Reglas para venta fiada
        if has_fiado:
            if not customer:
                raise ValidationError("Para registrar una venta a crédito o fiado debe seleccionar un cliente.")
            
            # Verificar permiso del cajero
            if hasattr(cashier, 'profile') and not cashier.profile.check_permission('can_authorize_credit'):
                raise ValidationError("No tiene permisos para autorizar ventas a crédito / fiados.")

            if not customer.can_receive_credit(fiado_amount):
                raise ValidationError(
                    f"El cliente '{customer.name}' excede su límite de crédito de RD$ {customer.credit_limit:,.2f}. "
                    f"Saldo actual: RD$ {customer.current_balance:,.2f}, Fiado solicitado: RD$ {fiado_amount:,.2f}."
                )

        # 5. Multimoneda y Devuelta
        rate_used = Decimal('1.0000')
        amount_rec = amount_received if amount_received > Decimal('0.00') else total_payments_amount
        change_dop = Decimal('0.00')

        if received_currency == 'USD':
            rate_used = settings.usd_rate
            rec_in_dop = amount_rec * rate_used
            if has_cash and rec_in_dop >= cash_paid_amount:
                change_dop = rec_in_dop - cash_paid_amount
        elif received_currency == 'EUR':
            rate_used = settings.eur_rate
            rec_in_dop = amount_rec * rate_used
            if has_cash and rec_in_dop >= cash_paid_amount:
                change_dop = rec_in_dop - cash_paid_amount
        else:
            if has_cash and amount_rec >= cash_paid_amount:
                change_dop = amount_rec - cash_paid_amount

        # Método principal
        if len(payment_methods_used) > 1:
            main_method = PaymentMethodChoices.MIXTO
        elif PaymentMethodChoices.FIADO in payment_methods_used:
            main_method = PaymentMethodChoices.FIADO
        elif PaymentMethodChoices.EFECTIVO in payment_methods_used:
            main_method = PaymentMethodChoices.EFECTIVO
        elif PaymentMethodChoices.TARJETA in payment_methods_used:
            main_method = PaymentMethodChoices.TARJETA
        elif PaymentMethodChoices.TRANSFERENCIA in payment_methods_used:
            main_method = PaymentMethodChoices.TRANSFERENCIA
        else:
            main_method = PaymentMethodChoices.EFECTIVO

        # 6. Crear Venta
        sale = Sale.objects.create(
            ticket_number=ticket_num,
            branch=branch_obj,
            customer=customer,
            cashier=cashier,
            cash_shift=shift,
            status=SaleStatus.COMPLETADA,
            payment_method=main_method,
            subtotal=total_subtotal,
            discount=total_discount,
            tax=Decimal('0.00'),
            total=sale_total,
            currency_received=received_currency,
            exchange_rate_used=rate_used,
            amount_received=amount_rec,
            change_given=change_dop,
            notes=notes,
            origin=origin,
            whatsapp_conversation=whatsapp_conversation,
        )

        # 7. Crear líneas de venta y descontar inventario
        for item in processed_items:
            SaleItem.objects.create(
                sale=sale,
                product=item['product'],
                quantity=item['quantity'],
                unit_cost=item['unit_cost'],
                unit_price=item['unit_price'],
                discount=item['discount'],
                subtotal=item['subtotal'],
            )

            # Descuento atómico de inventario
            InventoryService.process_movement(
                product_id=item['product'].id,
                movement_type=MovementType.VENTA,
                quantity=item['quantity'],
                user=cashier,
                reason=f"Venta en POS Ticket {ticket_num}",
                reference_doc=ticket_num,
            )

        # 8. Registrar pagos
        for p_data in payments_data:
            Payment.objects.create(
                sale=sale,
                payment_method=p_data.get('method') or p_data.get('payment_method'),
                amount=Decimal(str(p_data['amount'])),
                reference=p_data.get('reference', ''),
            )

        # 9. Afectar caja si hubo pago en efectivo
        if has_cash and shift:
            CashMovement.objects.create(
                shift=shift,
                movement_type=CashMovementType.INGRESO,
                category='VENTA_EFECTIVO',
                amount=cash_paid_amount,
                description=f"Venta {ticket_num}",
                user=cashier,
            )

        # 10. Afectar libreta de fiados si hubo crédito
        if has_fiado and customer:
            previous_bal = customer.current_balance
            new_bal = previous_bal + fiado_amount
            CreditTransaction.objects.create(
                customer=customer,
                sale=sale,
                transaction_type=CreditTransactionType.CARGO_FIADO,
                amount=fiado_amount,
                balance_after=new_bal,
                payment_method='FIADO',
                cash_shift=shift,
                user=cashier,
                reference=ticket_num,
                notes=f"Venta a crédito {ticket_num}",
            )
            # Notificación automática de compra fiada por WhatsApp
            CustomerCreditService.send_fiado_whatsapp_notification(
                customer=customer,
                sale=sale,
                fiado_amount=fiado_amount,
                previous_balance=previous_bal,
                current_balance=new_bal,
                cashier=cashier,
            )

        # 11. Auditoría
        AuditLog.objects.create(
            user=cashier,
            action='CREAR_VENTA',
            target_model='Sale',
            target_id=sale.ticket_number,
            details=f"Venta exitosa por RD$ {sale.total:,.2f} con método {sale.payment_method}. Items: {len(processed_items)}",
        )

        return sale

    @classmethod
    def send_sale_whatsapp_receipt(cls, sale: Sale, phone_number: str = None, user=None, request=None) -> dict:
        """
        Envía la foto oficial del ticket de compra por WhatsApp al cliente.
        Si la entrega de imagen falla por alguna razón, recurre a un resumen escrito.
        """
        target_phone = phone_number or (sale.customer.phone if sale.customer else None)
        if not target_phone or not str(target_phone).strip():
            return {
                'success': False,
                'error': 'No se especificó un número de WhatsApp para enviar el comprobante.'
            }

        try:
            from apps.whatsapp.services import WhatsAppService
            settings = BusinessSettings.get_settings()
            branch = sale.branch
            colmado_name = branch.name if branch else settings.name
            now_str = timezone.localtime(sale.created_at).strftime('%d/%m/%Y %I:%M %p')

            # 1. Generar la imagen visual exacta del ticket térmico
            rel_path = ReceiptImageGenerator.generate_receipt_image(sale)
            
            # Construir URL accesible para WAHA (Docker o nube)
            if request:
                image_url = request.build_absolute_uri(f"/media/{rel_path}")
            else:
                image_url = f"http://127.0.0.1:8000/media/{rel_path}"

            # 2. Despachar únicamente la imagen del ticket (sin texto adicional ni pie de mensaje)
            msg_record = WhatsAppService.send_image_message(
                phone_number=target_phone,
                image_url=image_url,
                caption='',
                filename=f"ticket_{sale.ticket_number}.png",
                user=user,
                relative_file_path=rel_path
            )

            AuditLog.objects.create(
                user=user,
                action='ENVIAR_RECIBO_WHATSAPP',
                target_model='Sale',
                target_id=sale.ticket_number,
                details=f"Comprobante en imagen enviado por WhatsApp al {target_phone}."
            )

            return {
                'success': True,
                'phone': target_phone,
                'message': f"Comprobante (foto del ticket) enviado por WhatsApp al {target_phone} exitosamente."
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Error al enviar comprobante por WhatsApp: {str(e)}"
            }

    @classmethod
    @transaction.atomic
    def void_sale(cls, sale_id: int, user, void_reason: str) -> Sale:
        """
        Anula una venta revirtiendo de forma segura el stock, la caja y la deuda del cliente.
        """
        if not void_reason.strip():
            raise ValidationError("Debe proporcionar un motivo justificado para anular la venta.")

        sale = Sale.objects.select_for_update().get(pk=sale_id)
        if sale.status == SaleStatus.ANULADA:
            raise ValidationError("Esta venta ya se encuentra anulada.")

        # Revertir inventario
        for item in sale.items.all():
            InventoryService.process_movement(
                product_id=item.product.id,
                movement_type=MovementType.ANULACION_VENTA,
                quantity=item.quantity,
                user=user,
                reason=f"Reingreso por anulación de ticket {sale.ticket_number}: {void_reason}",
                reference_doc=sale.ticket_number,
            )

        # Revertir pagos en efectivo de caja
        cash_paid = sum(p.amount for p in sale.payments.filter(payment_method=PaymentMethodChoices.EFECTIVO))
        if cash_paid > Decimal('0.00') and sale.cash_shift:
            CashMovement.objects.create(
                shift=sale.cash_shift,
                movement_type=CashMovementType.EGRESO,
                category='ANULACION_VENTA',
                amount=cash_paid,
                description=f"Salida por anulación de Venta {sale.ticket_number}",
                user=user,
            )

        # Revertir fiado si aplica
        fiado_paid = sum(p.amount for p in sale.payments.filter(payment_method=PaymentMethodChoices.FIADO))
        if fiado_paid > Decimal('0.00') and sale.customer:
            CreditTransaction.objects.create(
                customer=sale.customer,
                sale=sale,
                transaction_type=CreditTransactionType.AJUSTE_ABONO,
                amount=fiado_paid,
                balance_after=max(Decimal('0.00'), sale.customer.current_balance - fiado_paid),
                payment_method='ANULACION',
                cash_shift=sale.cash_shift,
                user=user,
                reference=sale.ticket_number,
                notes=f"Cancelación de cargo por anulación de venta {sale.ticket_number}: {void_reason}",
            )

        sale.status = SaleStatus.ANULADA
        sale.void_reason = void_reason
        sale.voided_by = user
        sale.voided_at = timezone.now()
        sale.save(update_fields=['status', 'void_reason', 'voided_by', 'voided_at'])

        AuditLog.objects.create(
            user=user,
            action='ANULAR_VENTA',
            target_model='Sale',
            target_id=sale.ticket_number,
            details=f"Venta anulada por motivo: {void_reason}",
        )

        return sale


class DeliveryService:
    @classmethod
    @transaction.atomic
    def create_delivery_order(
        cls,
        sale: Sale,
        destination_type: str = 'EXPRESS',
        delivery_person_id: int = None,
        delivery_address: str = '',
        notes: str = '',
        whatsapp_conversation = None,
        user = None,
    ) -> DeliveryOrder:
        """
        Crea o actualiza la orden de delivery vinculada a una venta existente.
        REGLA ESTRICTA: El delivery jamás genera una segunda venta; gestiona la logística de la venta actual.
        """
        order = DeliveryOrder.objects.filter(sale=sale).first()
        delivery_person = None
        if delivery_person_id:
            delivery_person = DeliveryPerson.objects.filter(pk=delivery_person_id, is_active=True).first()

        address = delivery_address.strip()
        if not address and sale.customer and sale.customer.address:
            address = sale.customer.address.strip()

        initial_status = DeliveryStatus.PENDIENTE_ENVIO if destination_type == 'EXPRESS' else DeliveryStatus.EN_CAMINO

        if order:
            order.destination_type = destination_type
            order.status = initial_status
            if delivery_person:
                order.delivery_person = delivery_person
            if address:
                order.delivery_address = address
            if notes:
                order.notes = notes
            order.save()
            return order

        order = DeliveryOrder.objects.create(
            sale=sale,
            customer=sale.customer,
            delivery_person=delivery_person,
            status=initial_status,
            destination_type=destination_type,
            delivery_address=address,
            notes=notes,
            whatsapp_conversation=whatsapp_conversation or sale.whatsapp_conversation,
            created_by=user,
        )

        AuditLog.objects.create(
            user=user,
            action='CREAR_DELIVERY',
            target_model='DeliveryOrder',
            target_id=str(order.id),
            details=f"Pedido Delivery #{order.id} creado para venta {sale.ticket_number} (Destino: {destination_type})",
        )
        return order

    @classmethod
    @transaction.atomic
    def dispatch_delivery_order(cls, delivery_order_id: int, user, delivery_person_id: int = None) -> dict:
        """
        Despacha un pedido individual marcándolo EN_CAMINO y enviando mensaje personalizado de WhatsApp al cliente.
        """
        from apps.whatsapp.services import WhatsAppService
        order = DeliveryOrder.objects.select_for_update().get(pk=delivery_order_id)

        if delivery_person_id:
            dp = DeliveryPerson.objects.filter(pk=delivery_person_id, is_active=True).first()
            if dp:
                order.delivery_person = dp

        order.status = DeliveryStatus.EN_CAMINO
        order.dispatched_at = timezone.now()
        order.dispatched_by = user

        # Formatear mensaje individual de WhatsApp con datos reales (incluyendo el monto de la compra)
        settings = BusinessSettings.get_settings()
        default_tpl = "Hola *{cliente}*, su pedido ({ticket}) por un monto de *{total}* ya ha salido con {repartidor}. ¡Muchas gracias por su compra en {negocio}!"
        template = settings.delivery_notification_template or default_tpl
        if '{total}' not in template:
            template += " Monto a pagar: *{total}*."

        client_name = order.customer.name if order.customer else "estimado cliente"
        ticket_num = order.sale.ticket_number
        total_str = f"RD$ {order.sale.total:,.2f}"
        repartidor_name = order.delivery_person.name if order.delivery_person else "nuestro repartidor"
        address_str = order.delivery_address or (order.customer.address if order.customer else "")

        msg_text = (
            template.replace('{cliente}', client_name)
                    .replace('{ticket}', ticket_num)
                    .replace('{total}', total_str)
                    .replace('{repartidor}', repartidor_name)
                    .replace('{direccion}', address_str)
                    .replace('{negocio}', settings.name)
        )

        dest_phone = None
        if order.customer and order.customer.phone:
            dest_phone = order.customer.phone
        elif order.whatsapp_conversation and order.whatsapp_conversation.contact:
            dest_phone = order.whatsapp_conversation.contact.phone

        notification_status = 'no_phone'
        error_msg = ''

        if dest_phone:
            try:
                w_msg = WhatsAppService.send_text_message(
                    phone_number=dest_phone,
                    text=msg_text,
                    conversation=order.whatsapp_conversation,
                    user=user,
                )
                if w_msg and getattr(w_msg, 'status', '') == 'failed':
                    notification_status = 'failed'
                    error_msg = getattr(w_msg, 'error_message', 'Error enviando mensaje WhatsApp')
                    order.notification_sent = False
                    order.notification_status = 'failed'
                    order.notification_error = error_msg
                else:
                    notification_status = 'sent'
                    order.notification_sent = True
                    order.notification_status = 'sent'
                    order.notification_error = ''
            except Exception as ex:
                notification_status = 'failed'
                error_msg = str(ex)
                order.notification_sent = False
                order.notification_status = 'failed'
                order.notification_error = error_msg

        order.save()

        AuditLog.objects.create(
            user=user,
            action='DESPACHAR_DELIVERY',
            target_model='DeliveryOrder',
            target_id=str(order.id),
            details=f"Delivery #{order.id} despachado con {repartidor_name}. Estado notificación WhatsApp: {notification_status}",
        )

        return {
            'success': True,
            'id': order.id,
            'ticket_number': order.sale.ticket_number,
            'customer_name': client_name,
            'status': 'EN_CAMINO',
            'delivery_person': repartidor_name,
            'notification_status': notification_status,
            'error': error_msg,
        }

    @classmethod
    def dispatch_all_pending(cls, user, delivery_person_id: int = None) -> list:
        """
        Procesa de manera independiente cada pedido pendiente de envío.
        REGLA ESTRICTA: Envía el mensaje individual a cada cliente, jamás un mensaje grupal.
        """
        pending_orders = DeliveryOrder.objects.filter(
            status__in=[DeliveryStatus.PENDIENTE_ENVIO, DeliveryStatus.PREPARANDO]
        ).order_by('created_at')

        results = []
        for order in pending_orders:
            try:
                res = cls.dispatch_delivery_order(
                    delivery_order_id=order.id,
                    user=user,
                    delivery_person_id=delivery_person_id,
                )
                results.append(res)
            except Exception as ex:
                results.append({
                    'success': False,
                    'id': order.id,
                    'ticket_number': order.sale.ticket_number,
                    'customer_name': order.customer.name if order.customer else '',
                    'status': order.status,
                    'notification_status': 'error',
                    'error': str(ex),
                })
        return results

    @classmethod
    def mark_as_delivered(cls, delivery_order_id: int, user) -> DeliveryOrder:
        order = DeliveryOrder.objects.get(pk=delivery_order_id)
        order.status = DeliveryStatus.ENTREGADO
        order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at'])

        AuditLog.objects.create(
            user=user,
            action='DELIVERY_ENTREGADO',
            target_model='DeliveryOrder',
            target_id=str(order.id),
            details=f"Delivery #{order.id} marcado como ENTREGADO.",
        )
        return order

    @classmethod
    def cancel_delivery(cls, delivery_order_id: int, user, reason: str = '') -> DeliveryOrder:
        order = DeliveryOrder.objects.get(pk=delivery_order_id)
        order.status = DeliveryStatus.CANCELADO
        if reason:
            order.notes = f"{order.notes}\nCancelado: {reason}".strip()
        order.save(update_fields=['status', 'notes'])

        AuditLog.objects.create(
            user=user,
            action='CANCELAR_DELIVERY',
            target_model='DeliveryOrder',
            target_id=str(order.id),
            details=f"Delivery #{order.id} CANCELADO. Motivo: {reason}",
        )
        return order

    @classmethod
    def get_pending_orders(cls, branch_id: int = None):
        """
        Retorna los pedidos de delivery que requieren atención logística (Pendientes o en preparación).
        """
        from django.db.models import Q
        qs = DeliveryOrder.objects.filter(
            status__in=[DeliveryStatus.PENDIENTE_ENVIO, DeliveryStatus.PREPARANDO]
        ).select_related('sale', 'customer', 'delivery_person')
        if branch_id:
            qs = qs.filter(Q(sale__branch_id=branch_id) | Q(sale__branch__isnull=True))
        return qs.order_by('created_at')
