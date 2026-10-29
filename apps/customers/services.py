from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import BusinessSettings, AuditLog
from apps.cash.models import CashShift, CashMovement, CashMovementType
from apps.customers.models import Customer, CreditTransaction, CreditTransactionType

class CustomerCreditService:
    @classmethod
    @transaction.atomic
    def record_abono(
        cls,
        customer_id: int,
        amount: Decimal,
        payment_method: str,
        user,
        cash_shift_id: int = None,
        notes: str = '',
        reference: str = '',
        **kwargs
    ) -> CreditTransaction:
        """
        Registra un abono o liquidación de deuda de un cliente en su libreta de fiados.
        Si se paga en efectivo, ingresa el dinero al turno de caja abierto para mantener el cuadre exacto.
        """
        if amount <= Decimal('0.00'):
            raise ValidationError("El monto del abono debe ser mayor que cero.")

        customer = Customer.objects.select_for_update().get(pk=customer_id)
        current_bal = customer.current_balance
        
        # Validación de abono: no permitir abonos mayores a la deuda pendiente salvo sobrepago explícito
        allow_overpayment = kwargs.get('allow_overpayment', False)
        if not allow_overpayment and current_bal > Decimal('0.00') and amount > current_bal:
            raise ValidationError(
                f"El monto del abono (RD$ {amount:,.2f}) no puede ser superior al saldo pendiente actual (RD$ {current_bal:,.2f})."
            )

        new_bal = max(Decimal('0.00'), current_bal - amount) if not allow_overpayment else (current_bal - amount)
        shift = None
        if cash_shift_id:
            shift = CashShift.objects.filter(id=cash_shift_id, status='ABIERTO').first()
        if not shift:
            shift = CashShift.objects.filter(cashier=user, status='ABIERTO').first()
        if not shift:
            shift = CashShift.objects.filter(status='ABIERTO').first()

        tx = CreditTransaction.objects.create(
            customer=customer,
            transaction_type=CreditTransactionType.ABONO_PAGO,
            amount=amount,
            balance_after=new_bal,
            payment_method=payment_method,
            cash_shift=shift,
            user=user,
            reference=reference,
            notes=notes or f"Abono a cuenta por RD$ {amount:,.2f}",
        )

        # Si el cobro fue en efectivo, asentar el ingreso en la caja
        if payment_method == 'EFECTIVO' and shift:
            CashMovement.objects.create(
                shift=shift,
                movement_type=CashMovementType.INGRESO,
                category='ABONO_FIADO',
                amount=amount,
                description=f"Abono a crédito cliente {customer.name} (Ref: {tx.id})",
                user=user,
            )

        AuditLog.objects.create(
            user=user,
            action='COBRO_CREDITO',
            target_model='Customer',
            target_id=str(customer.id),
            details=f"Abono por RD$ {amount:,.2f} a {customer.name} vía {payment_method}. Saldo restante: RD$ {new_bal:,.2f}",
        )

        # Enviar notificación automática por WhatsApp
        cls.send_abono_whatsapp_notification(
            customer=customer,
            tx=tx,
            amount=amount,
            previous_balance=current_bal,
            new_balance=new_bal,
            user=user,
        )

        return tx

    @classmethod
    def send_fiado_whatsapp_notification(
        cls,
        customer: Customer,
        sale,
        fiado_amount: Decimal,
        previous_balance: Decimal,
        current_balance: Decimal,
        cashier=None
    ):
        """
        Envía automáticamente un mensaje de WhatsApp al cliente detallando su compra fiada,
        los productos llevados, fecha y hora, deuda anterior, fiado de hoy y monto total que debe.
        """
        if not customer.phone:
            return None

        try:
            from apps.whatsapp.services import WhatsAppService
            settings = BusinessSettings.get_settings()
            now_str = timezone.localtime().strftime('%d/%m/%Y %I:%M %p')

            items_lines = []
            if sale and hasattr(sale, 'items'):
                for it in sale.items.select_related('product').all()[:12]:
                    items_lines.append(f"• {it.quantity:g}x {it.product.name} (RD$ {it.subtotal:,.2f})")
                if sale.items.count() > 12:
                    items_lines.append(f"• ... y {sale.items.count() - 12} artículos más.")

            items_text = "\n".join(items_lines) if items_lines else "• Compra de provisiones del colmado"
            ticket_tag = f"Ticket #{sale.ticket_number}" if sale else "Comprobante de Fiado"

            msg = (
                f"*{settings.name}*\n"
                f"*Comprobante de Fiado* - {ticket_tag}\n"
                f"*Fecha:* {now_str}\n\n"
                f"Hola *{customer.name}*, le confirmamos su compra a crédito registrada en su libreta:\n\n"
                f"*Artículos llevados:*\n"
                f"{items_text}\n\n"
                f"*Detalle de su Cuenta:*\n"
                f"• Deuda anterior: RD$ {previous_balance:,.2f}\n"
                f"• Fiado tomado hoy: RD$ {fiado_amount:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"*Monto total que debe:* RD$ {current_balance:,.2f}\n\n"
                f"¡Gracias por su preferencia!"
            )

            return WhatsAppService.send_text_message(
                phone_number=customer.phone,
                text=msg,
                user=cashier
            )
        except Exception:
            return None

    @classmethod
    def send_abono_whatsapp_notification(
        cls,
        customer: Customer,
        tx: CreditTransaction,
        amount: Decimal,
        previous_balance: Decimal,
        new_balance: Decimal,
        user=None
    ):
        """
        Envía automáticamente un mensaje de WhatsApp al cliente informándole que se ha registrado
        un abono a su deuda, indicando la fecha y hora, deuda anterior, monto abonado y nuevo saldo.
        """
        if not customer.phone:
            return None

        try:
            from apps.whatsapp.services import WhatsAppService
            settings = BusinessSettings.get_settings()
            now_str = timezone.localtime().strftime('%d/%m/%Y %I:%M %p')

            ref_text = f"Ref: {tx.reference}" if tx.reference else f"Comprobante #{tx.id}"
            
            if new_balance <= Decimal('0.00'):
                estado_deuda = "*¡Felicidades! Su cuenta ha quedado totalmente al día (RD$ 0.00).*"
            else:
                estado_deuda = f"*Monto total pendiente que debe:* RD$ {new_balance:,.2f}"

            msg = (
                f"*{settings.name}*\n"
                f"*Recibo de Abono a Cuenta* - {ref_text}\n"
                f"*Fecha:* {now_str}\n\n"
                f"Hola *{customer.name}*, hemos registrado su abono con éxito:\n\n"
                f"*Monto abonado hoy:* RD$ {amount:,.2f}\n"
                f"*Método de pago:* {tx.payment_method}\n\n"
                f"*Estado de su Cuenta:*\n"
                f"• Deuda anterior: RD$ {previous_balance:,.2f}\n"
                f"• Abono recibido hoy: RD$ {amount:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{estado_deuda}\n\n"
                f"¡Muchas gracias por su puntualidad y confianza!"
            )

            return WhatsAppService.send_text_message(
                phone_number=customer.phone,
                text=msg,
                user=user
            )
        except Exception:
            return None

    @staticmethod
    def generate_whatsapp_summary(customer: Customer) -> str:
        """
        Genera un mensaje respetuoso y claro para WhatsApp con el resumen de la cuenta del cliente.
        """
        settings = BusinessSettings.get_settings()
        balance = customer.current_balance
        last_payment = customer.credit_transactions.filter(transaction_type='ABONO_PAGO').order_by('-created_at').first()
        
        last_payment_text = ""
        if last_payment:
            last_payment_text = f"\n*Último abono registrado:* RD$ {last_payment.amount:,.2f} el {last_payment.created_at.strftime('%d/%m/%Y')}."

        msg = (
            f"*Hola {customer.name}* le saluda *{settings.name}*.\n\n"
            f"Le compartimos el resumen de su libreta a la fecha:\n"
            f"*Saldo pendiente:* RD$ {balance:,.2f}\n"
            f"*Límite de crédito disponible:* RD$ {customer.available_credit:,.2f}"
            f"{last_payment_text}\n\n"
            f"Puede realizar sus abonos directamente en el colmado o consultarnos por esta vía si desea hacer una transferencia.\n"
            f"¡Muchas gracias por su preferencia!"
        )
        return msg

    @classmethod
    @transaction.atomic
    def record_cargo(
        cls,
        customer_id: int,
        amount: Decimal,
        user,
        notes: str = '',
        reference: str = ''
    ) -> CreditTransaction:
        """
        Registra un cargo a la deuda / fiado de un cliente en su libreta.
        """
        if amount <= Decimal('0.00'):
            raise ValidationError("El monto del cargo debe ser mayor que cero.")

        customer = Customer.objects.select_for_update().get(pk=customer_id)
        current_bal = customer.current_balance
        new_bal = current_bal + amount

        tx = CreditTransaction.objects.create(
            customer=customer,
            transaction_type=CreditTransactionType.CARGO_FIADO,
            amount=amount,
            balance_after=new_bal,
            user=user,
            reference=reference,
            notes=notes or f"Fiado cargado a cuenta por RD$ {amount:,.2f}",
        )

        AuditLog.objects.create(
            user=user,
            action='CARGO_FIADO',
            target_model='Customer',
            target_id=str(customer.id),
            details=f"Cargo de fiado por RD$ {amount:,.2f} a {customer.name}. Nuevo saldo deudor: RD$ {new_bal:,.2f}",
        )

        # Enviar notificación automática por WhatsApp (sin íconos de IA)
        cls.send_cargo_whatsapp_notification(
            customer=customer,
            tx=tx,
            amount=amount,
            previous_balance=current_bal,
            new_balance=new_bal,
            user=user,
            notes=notes,
        )

        return tx

    @classmethod
    def send_cargo_whatsapp_notification(
        cls,
        customer: Customer,
        tx: CreditTransaction,
        amount: Decimal,
        previous_balance: Decimal,
        new_balance: Decimal,
        user=None,
        notes: str = ''
    ):
        """
        Envía automáticamente un mensaje de WhatsApp al cliente confirmando el nuevo cargo fiado.
        """
        if not customer.phone:
            return None

        try:
            from apps.whatsapp.services import WhatsAppService
            settings = BusinessSettings.get_settings()
            now_str = timezone.localtime().strftime('%d/%m/%Y %I:%M %p')
            ref_text = f"Ref: {tx.reference}" if tx.reference else f"Comprobante #{tx.id}"
            detalle = f"• *Concepto:* {notes}\n" if notes else ""

            msg = (
                f"*{settings.name}*\n"
                f"*Comprobante de Fiado* - {ref_text}\n"
                f"*Fecha:* {now_str}\n\n"
                f"Hola *{customer.name}*, le confirmamos que se ha registrado un nuevo cargo a su libreta:\n\n"
                f"• *Monto tomado hoy:* RD$ {amount:,.2f}\n"
                f"{detalle}"
                f"• *Deuda anterior:* RD$ {previous_balance:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Monto total que debe:* RD$ {new_balance:,.2f}\n\n"
                f"¡Gracias por su preferencia!"
            )

            return WhatsAppService.send_text_message(
                phone_number=customer.phone,
                text=msg,
                user=user
            )
        except Exception:
            return None

    @classmethod
    def auto_register_customer_from_contact(cls, contact_id: int, user=None) -> Customer:
        """
        Auto-registra y vincula un nuevo cliente a partir de un contacto de WhatsApp existente.
        Permite fiar o abonar inmediatamente sin salir del chat.
        """
        from apps.whatsapp.models import WhatsAppContact
        from apps.core.models import ColmadoBranch

        contact = WhatsAppContact.objects.get(pk=contact_id)
        if contact.customer:
            return contact.customer

        branch = ColmadoBranch.get_default_branch()
        name = contact.display_name.strip() if contact.display_name else ''
        if not name or name.startswith('Contacto '):
            name = f"Cliente {contact.phone[-8:]}"

        customer = Customer.objects.create(
            branch=branch,
            name=name,
            phone=contact.phone,
            credit_limit=Decimal('3000.00'),
            is_active=True
        )
        contact.customer = customer
        contact.is_verified = True
        contact.display_name = customer.name
        contact.save(update_fields=['customer', 'is_verified', 'display_name'])

        AuditLog.objects.create(
            user=user,
            action='AUTO_REGISTRO_WHATSAPP',
            target_model='Customer',
            target_id=str(customer.id),
            details=f"Cliente {customer.name} ({customer.phone}) registrado automáticamente desde el chat de WhatsApp.",
        )
        return customer

    @classmethod
    @transaction.atomic
    def register_or_link_whatsapp_customer(
        cls,
        contact_id: int,
        name: str,
        phone: str = None,
        alias: str = '',
        address: str = '',
        notes: str = '',
        credit_limit: Decimal = Decimal('3000.00'),
        user = None,
    ) -> Customer:
        """
        Registra formalmente un cliente desde WhatsApp o lo vincula con uno existente evitando duplicados.
        Normaliza el número telefónico y actualiza el contacto de WhatsApp.
        """
        import re
        from apps.whatsapp.models import WhatsAppContact
        from apps.core.models import ColmadoBranch

        contact = WhatsAppContact.objects.select_for_update().get(pk=contact_id)
        raw_phone = (phone or contact.phone or '').strip()
        clean_phone = re.sub(r'[^\d+]', '', raw_phone)
        if clean_phone.startswith('00'):
            clean_phone = '+' + clean_phone[2:]
        elif not clean_phone.startswith('+'):
            if len(clean_phone) == 10:
                clean_phone = '+1' + clean_phone
            elif len(clean_phone) == 11 and clean_phone.startswith('1'):
                clean_phone = '+' + clean_phone

        # Buscar cliente existente para evitar duplicados
        existing_customer = None
        if clean_phone:
            # Buscar coincidencia por teléfono normalizado o terminación de 10 dígitos
            phone_suffix = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
            existing_customer = Customer.objects.filter(phone__icontains=phone_suffix).first()

        if not existing_customer and name.strip():
            existing_customer = Customer.objects.filter(name__iexact=name.strip()).first()

        branch = ColmadoBranch.get_default_branch()

        if existing_customer:
            customer = existing_customer
            # Actualizar datos si se proporcionaron nuevos
            updated_fields = []
            if name.strip() and customer.name != name.strip():
                customer.name = name.strip()
                updated_fields.append('name')
            if clean_phone and not customer.phone:
                customer.phone = clean_phone
                updated_fields.append('phone')
            if alias.strip() and not customer.alias:
                customer.alias = alias.strip()
                updated_fields.append('alias')
            if address.strip() and not customer.address:
                customer.address = address.strip()
                updated_fields.append('address')
            if notes.strip():
                customer.notes = f"{customer.notes}\n{notes.strip()}".strip()
                updated_fields.append('notes')
            if updated_fields:
                customer.save(update_fields=updated_fields)
        else:
            customer = Customer.objects.create(
                branch=branch,
                name=name.strip() or f"Cliente {clean_phone[-8:]}",
                phone=clean_phone,
                alias=alias.strip(),
                address=address.strip(),
                notes=notes.strip(),
                credit_limit=credit_limit,
                is_active=True
            )

        # Vincular contacto de WhatsApp
        contact.customer = customer
        contact.display_name = customer.name
        contact.is_verified = True
        if clean_phone and contact.phone != clean_phone:
            contact.phone = clean_phone
            contact.save(update_fields=['customer', 'display_name', 'is_verified', 'phone'])
        else:
            contact.save(update_fields=['customer', 'display_name', 'is_verified'])

        AuditLog.objects.create(
            user=user,
            action='REGISTRAR_CLIENTE_WHATSAPP',
            target_model='Customer',
            target_id=str(customer.id),
            details=f"Cliente {customer.name} ({customer.phone}) asignado/registrado formalmente desde WhatsApp.",
        )
        return customer

