import json
import logging
import requests
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.contrib import messages
from django.db.models import Q, Sum

from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.whatsapp.models import (
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppMessage,
    ConversationStatus,
)
from apps.whatsapp.services import WhatsAppService
from apps.customers.models import Customer
from apps.customers.services import CustomerCreditService
from apps.sales.models import DeliveryPerson, DeliveryOrder, DeliveryStatus
from apps.sales.services import SaleService, DeliveryService
from apps.catalog.models import Product
from apps.core.models import BusinessSettings

@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(View):
    """
    Endpoint público unificado para webhooks:
    - WAHA (WhatsApp HTTP API): Eventos 'message', 'message.any', 'session.status'.
    - Meta Cloud API: Verificación handshake GET y recepción de eventos POST con firma SHA-256.
    """
    def get(self, request):
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        # Verificación handshake Meta
        if mode == 'subscribe':
            configured_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '')
            if token == configured_token:
                return HttpResponse(challenge, content_type='text/plain', status=200)
            return HttpResponse('Verificación fallida: token no coincide', status=403)

        # Verificación / comprobación de estado de webhook para WAHA
        return HttpResponse('Endpoint Webhook WhatsApp Activo (WAHA / Meta)', content_type='text/plain', status=200)

    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'error': 'JSON inválido o cuerpo vacío'}, status=400)

        # 1. Detección de Payload de WAHA (WhatsApp HTTP API)
        if 'event' in payload or ('session' in payload and 'payload' in payload):
            try:
                WhatsAppService.process_waha_webhook(payload)
                return JsonResponse({'status': 'WAHA_EVENT_RECEIVED'}, status=200)
            except Exception as ex:
                return JsonResponse({'error': f"Error procesando evento WAHA: {str(ex)}"}, status=400)

        # 2. Detección de Payload oficial de Meta Cloud API
        signature = request.META.get('HTTP_X_HUB_SIGNATURE_256', '')
        if not WhatsAppService.verify_webhook_signature(request.body, signature):
            return HttpResponse('Firma de webhook inválida', status=401)

        try:
            WhatsAppService.process_incoming_webhook(payload)
            return JsonResponse({'status': 'EVENT_RECEIVED'}, status=200)
        except Exception as ex:
            return JsonResponse({'error': f"Error procesando evento Meta: {str(ex)}"}, status=400)


class WhatsAppInboxView(LoginRequiredMixin, View):
    def get(self, request):
        conversations = WhatsAppConversation.objects.select_related('contact__customer').all().order_by('-last_message_at')
        
        q = request.GET.get('q', '').strip()
        status_filter = request.GET.get('estado', '')

        if q:
            conversations = conversations.filter(
                Q(contact__phone__icontains=q) |
                Q(contact__display_name__icontains=q) |
                Q(contact__customer__name__icontains=q)
            )
        if status_filter:
            conversations = conversations.filter(status=status_filter)

        selected_id = request.GET.get('chat')
        selected_conv = None
        if selected_id:
            selected_conv = WhatsAppConversation.objects.filter(id=selected_id).select_related('contact__customer').first()
        elif conversations.exists():
            selected_conv = conversations.first()

        messages_list = []
        if selected_conv:
            selected_conv.unread_count = 0
            selected_conv.save(update_fields=['unread_count'])
            messages_list = selected_conv.messages.select_related('sent_by').all().order_by('created_at')

        active_branch_id = request.session.get('active_branch_id')
        dp_qs = DeliveryPerson.objects.filter(is_active=True).order_by('name')
        if active_branch_id:
            dp_qs = dp_qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))

        popular_products = Product.objects.filter(is_active=True).select_related('category')[:30]
        settings_obj = BusinessSettings.get_settings()

        return render(request, 'whatsapp/inbox.html', {
            'conversations': conversations,
            'selected_conv': selected_conv,
            'messages_list': messages_list,
            'search_query': q,
            'status_filter': status_filter,
            'delivery_persons': dp_qs,
            'popular_products': popular_products,
            'settings': settings_obj,
        })


class SendWhatsAppMessageView(LoginRequiredMixin, View):
    def post(self, request, pk):
        conv = get_object_or_404(WhatsAppConversation, pk=pk)
        text = request.POST.get('message_text', '').strip()
        action = request.POST.get('action', '')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

        if action == 'send_balance' and conv.contact.customer:
            text = CustomerCreditService.generate_whatsapp_summary(conv.contact.customer)

        if text:
            # 1. Verificar si el mensaje es un comando conversacional de libreta (Abono o Fiado)
            cmd = WhatsAppService.parse_operator_credit_command(text)
            if cmd:
                contact = conv.contact
                customer = contact.customer
                # Auto-registrar cliente si el contacto de WhatsApp aún no está en la libreta
                if not customer:
                    customer = CustomerCreditService.auto_register_customer_from_contact(contact.id, request.user)
                    contact.refresh_from_db()

                amount = cmd['amount']
                notes = cmd.get('notes', '')
                payment_method = cmd.get('payment_method', 'EFECTIVO')

                if cmd['type'] == 'ABONO':
                    tx = CustomerCreditService.record_abono(
                        customer_id=customer.id,
                        amount=amount,
                        payment_method=payment_method,
                        user=request.user,
                        notes=notes,
                    )
                    customer.refresh_from_db()
                    flash_msg = f"Abono de RD$ {amount:,.2f} ({payment_method}) registrado exitosamente para {customer.name}. Deuda pendiente: RD$ {customer.current_balance:,.2f}"
                    messages.success(request, flash_msg)
                elif cmd['type'] == 'CARGO':
                    tx = CustomerCreditService.record_cargo(
                        customer_id=customer.id,
                        amount=amount,
                        user=request.user,
                        notes=notes,
                    )
                    customer.refresh_from_db()
                    flash_msg = f"Cargo de fiado por RD$ {amount:,.2f} registrado exitosamente para {customer.name}. Deuda total: RD$ {customer.current_balance:,.2f}"
                    messages.success(request, flash_msg)

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'is_command': True,
                        'command_type': cmd['type'],
                        'amount': float(amount),
                        'customer_name': customer.name,
                        'customer_balance': float(customer.current_balance),
                        'flash_message': flash_msg,
                    })
                return redirect(f"/whatsapp/bandeja/?chat={conv.id}")

            # 2. Despacho ordinario de mensaje conversacional
            msg_obj = WhatsAppService.send_text_message(
                phone_number=conv.contact.phone,
                text=text,
                conversation=conv,
                user=request.user
            )
            if msg_obj.status == 'failed':
                messages.warning(request, f"Mensaje registrado localmente. Nota de entrega: {msg_obj.error_message}")
            else:
                messages.success(request, "Mensaje enviado a través de WhatsApp.")

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'is_command': False,
                    'message': {
                        'id': msg_obj.id,
                        'direction': msg_obj.direction,
                        'content': msg_obj.content,
                        'status': msg_obj.status,
                        'time': timezone.localtime(msg_obj.created_at).strftime('%I:%M %p'),
                        'error_message': msg_obj.error_message,
                    }
                })

        if is_ajax:
            return JsonResponse({'success': False, 'error': 'El mensaje no puede estar vacío.'}, status=400)
        return redirect(f"/whatsapp/bandeja/?chat={conv.id}")


class WhatsAppCreditActionView(LoginRequiredMixin, View):
    """
    Procesa acciones rápidas de crédito desde la bandeja de WhatsApp:
    - ABONO: Registra abono a libreta (efectivo/transferencia) y envía recibo oficial por WhatsApp.
    - CARGO: Carga fiado a cuenta y envía comprobante por WhatsApp.
    - Auto-registro: Si el contacto de WhatsApp no estaba registrado como Customer,
      se auto-crea en la libreta al instante y se asocia al contacto sin fricción.
    """
    def post(self, request, pk):
        conv = get_object_or_404(WhatsAppConversation, pk=pk)
        action_type = request.POST.get('action_type', '').strip().upper()
        amount_raw = request.POST.get('amount', '').strip().replace(',', '.')
        payment_method = request.POST.get('payment_method', 'EFECTIVO').strip().upper()
        notes = request.POST.get('notes', '').strip()
        reference = request.POST.get('reference', '').strip()

        is_ajax = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '') or
            request.content_type == 'application/json'
        )

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal('0.00'):
                raise ValueError("El monto debe ser mayor a 0.")
        except Exception:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Monto numérico inválido o menor a RD$ 0.01.'}, status=400)
            messages.error(request, "Por favor ingrese un monto válido mayor a RD$ 0.00.")
            return redirect(f"/whatsapp/bandeja/?chat={conv.id}")

        contact = conv.contact
        customer = contact.customer
        auto_registered = False
        if not customer:
            customer = CustomerCreditService.auto_register_customer_from_contact(contact.id, request.user)
            contact.refresh_from_db()
            auto_registered = True

        prev_balance = customer.current_balance

        try:
            if action_type == 'ABONO':
                tx = CustomerCreditService.record_abono(
                    customer_id=customer.id,
                    amount=amount,
                    payment_method=payment_method,
                    user=request.user,
                    notes=notes,
                    reference=reference,
                )
                customer.refresh_from_db()
                success_msg = f"Abono de RD$ {amount:,.2f} ({payment_method}) registrado exitosamente para {customer.name}. Nuevo balance pendiente: RD$ {customer.current_balance:,.2f}"
                messages.success(request, success_msg)
            elif action_type in ['CARGO', 'CREDITO']:
                tx = CustomerCreditService.record_cargo(
                    customer_id=customer.id,
                    amount=amount,
                    user=request.user,
                    notes=notes,
                    reference=reference,
                )
                customer.refresh_from_db()
                success_msg = f"Crédito por RD$ {amount:,.2f} registrado exitosamente para {customer.name}. Deuda total: RD$ {customer.current_balance:,.2f}"
                messages.success(request, success_msg)
            else:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': f"Tipo de acción no soportado: {action_type}"}, status=400)
                messages.error(request, f"Acción inválida: {action_type}")
                return redirect(f"/whatsapp/bandeja/?chat={conv.id}")
        except ValidationError as ex:
            err_msg = str(ex.message if hasattr(ex, 'message') else ex)
            if is_ajax:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect(f"/whatsapp/bandeja/?chat={conv.id}")
        except Exception as ex:
            err_msg = f"Error al procesar la operación: {str(ex)}"
            if is_ajax:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect(f"/whatsapp/bandeja/?chat={conv.id}")

        if is_ajax:
            last_msg = conv.messages.filter(direction='OUTBOUND').order_by('-created_at').first()
            receipt_text = last_msg.content if last_msg else success_msg
            msg_time = timezone.localtime(last_msg.created_at).strftime('%I:%M %p') if last_msg else timezone.localtime().strftime('%I:%M %p')

            return JsonResponse({
                'success': True,
                'action_type': action_type,
                'amount': float(amount),
                'payment_method': payment_method,
                'previous_balance': float(prev_balance),
                'new_balance': float(customer.current_balance),
                'customer_id': customer.id,
                'customer_name': customer.name,
                'auto_registered': auto_registered,
                'message': success_msg,
                'receipt_text': receipt_text,
                'msg_time': msg_time,
            })

        return redirect(f"/whatsapp/bandeja/?chat={conv.id}")


class WhatsAppCreateSaleView(LoginRequiredMixin, View):
    """
    Registra ventas directamente desde el flujo de pedidos de WhatsApp:
    - CONTADO: Efectivo, Transferencia o Tarjeta.
    - CREDITO: Venta a crédito cargada a la cuenta por cobrar del cliente.
    - Opciones de Entrega:
      1. Enviar directamente al cliente.
      2. Agregar a Delivery Express (con selector de repartidor).
    REGLA: La venta se registra una sola vez y no se duplica. El delivery se vincula a esta venta.
    """
    def post(self, request, pk):
        conv = get_object_or_404(WhatsAppConversation, pk=pk)

        # Soporta JSON o Form Data
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
        else:
            data = request.POST

        sale_type = data.get('sale_type', 'CONTADO').strip().upper()
        payment_method = data.get('payment_method', 'EFECTIVO').strip().upper()
        amount_raw = str(data.get('amount', '0.00')).strip().replace(',', '.')
        reference = data.get('reference', '').strip()
        destination_type = data.get('destination_type', 'DIRECTO').strip().upper()
        delivery_person_id = data.get('delivery_person_id') or None
        delivery_address = data.get('delivery_address', '').strip()
        notes = data.get('notes', '').strip()
        items_raw = data.get('items', [])

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal('0.00'):
                raise ValueError("El monto de la venta debe ser mayor a RD$ 0.00.")
        except Exception:
            return JsonResponse({'success': False, 'error': 'Monto inválido. Ingrese un valor mayor a RD$ 0.00.'}, status=400)

        # 1. Asegurar cliente identificado
        contact = conv.contact
        customer = contact.customer
        if not customer:
            customer = CustomerCreditService.auto_register_customer_from_contact(contact.id, request.user)
            contact.refresh_from_db()

        # Si el cliente no tiene dirección y se especificó una, guardarla
        if delivery_address and not customer.address:
            customer.address = delivery_address
            customer.save(update_fields=['address'])

        # 2. Configurar ítems de venta
        items_data = []
        if isinstance(items_raw, list) and len(items_raw) > 0:
            for it in items_raw:
                items_data.append({
                    'product_id': it.get('product_id'),
                    'quantity': it.get('quantity', 1),
                    'discount': it.get('discount', 0),
                    'unit_price': it.get('unit_price') or it.get('price'),
                    'name': it.get('name'),
                })
        else:
            items_data.append({
                'product_id': 'GENERIC',
                'name': f"Pedido WhatsApp: {notes[:60]}" if notes else "Pedido WhatsApp",
                'quantity': 1,
                'unit_price': amount,
                'discount': Decimal('0.00'),
            })

        # 3. Configurar método de pago
        if sale_type == 'CREDITO':
            final_payment_method = 'FIADO'
        else:
            if payment_method in ['TRANSFERENCIA', 'TARJETA']:
                final_payment_method = payment_method
            else:
                final_payment_method = 'EFECTIVO'

        payments_data = [{
            'method': final_payment_method,
            'amount': amount,
            'reference': reference or (f"WhatsApp {conv.contact.phone}" if final_payment_method != 'EFECTIVO' else ''),
        }]

        active_branch_id = request.session.get('active_branch_id')

        try:
            sale = SaleService.create_sale(
                cashier=request.user,
                items_data=items_data,
                payments_data=payments_data,
                customer_id=customer.id,
                received_currency='DOP',
                amount_received=amount,
                notes=f"[WhatsApp] {notes}".strip(),
                branch_id=active_branch_id,
                origin='WHATSAPP',
                whatsapp_conversation=conv,
            )

            # 4. Gestión de Entrega / Delivery
            if destination_type == 'EXPRESS':
                dp_id = None
                if delivery_person_id:
                    try:
                        dp_id = int(delivery_person_id)
                    except (ValueError, TypeError):
                        dp_id = None
                DeliveryService.create_delivery_order(
                    sale=sale,
                    destination_type='EXPRESS',
                    delivery_person_id=dp_id,
                    delivery_address=delivery_address or customer.address or '',
                    notes=notes,
                    whatsapp_conversation=conv,
                    user=request.user,
                )

            # 5. Notificación automática por WhatsApp con el monto explícito de la compra
            settings = BusinessSettings.get_settings()
            total_fmt = f"RD$ {sale.total:,.2f}"
            ticket_tag = f"Ticket #{sale.ticket_number}"

            items_lines = []
            if sale.items.exists():
                for it in sale.items.select_related('product').all()[:6]:
                    items_lines.append(f"• {it.quantity:g}x {it.product.name} (RD$ {it.subtotal:,.2f})")
                if sale.items.count() > 6:
                    items_lines.append(f"• ... y {sale.items.count() - 6} artículos más.")
            items_summary = "\n" + "\n".join(items_lines) + "\n" if items_lines else ""

            if sale_type == 'CREDITO':
                conf_msg = (
                    f"*{settings.name}*\n"
                    f"Hola *{customer.name}*, confirmamos su compra a crédito ({ticket_tag}):\n"
                    f"{items_summary}\n"
                    f"• *Monto de esta compra:* {total_fmt}\n"
                    f"• *Balance total adeudado:* RD$ {customer.current_balance:,.2f}\n\n"
                    f"{'Su pedido va de camino con el delivery.' if destination_type == 'EXPRESS' else 'Su pedido está preparado.'}\n"
                    f"¡Muchas gracias por su preferencia!"
                )
            else:
                conf_msg = (
                    f"*{settings.name}*\n"
                    f"Hola *{customer.name}*, confirmamos su compra ({ticket_tag}):\n"
                    f"{items_summary}\n"
                    f"• *Monto total de la compra:* {total_fmt} ({sale.get_payment_method_display()})\n\n"
                    f"{'Su pedido va de camino con el delivery.' if destination_type == 'EXPRESS' else 'Su pedido está preparado.'}\n"
                    f"¡Muchas gracias por su compra!"
                )

            WhatsAppService.send_text_message(
                phone_number=contact.phone,
                text=conf_msg,
                conversation=conv,
                user=request.user
            )

            return JsonResponse({
                'success': True,
                'ticket_number': sale.ticket_number,
                'total': float(sale.total),
                'payment_method': sale.get_payment_method_display(),
                'sale_type': sale_type,
                'delivery_express': (destination_type == 'EXPRESS'),
                'customer_name': customer.name,
                'customer_balance': float(customer.current_balance),
                'message': f"Venta {sale.ticket_number} por RD$ {sale.total:,.2f} procesada exitosamente."
            })
        except ValidationError as ex:
            return JsonResponse({'success': False, 'error': str(ex.message if hasattr(ex, 'message') else ex)}, status=400)
        except Exception as ex:
            return JsonResponse({'success': False, 'error': f"Error interno: {str(ex)}"}, status=500)


class WhatsAppRegisterCustomerView(LoginRequiredMixin, View):
    """
    Asigna o registra un cliente formal a partir de un número de WhatsApp desconocido o sin nombre.
    """
    def post(self, request, pk):
        conv = get_object_or_404(WhatsAppConversation, pk=pk)
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip() or conv.contact.phone
        alias = request.POST.get('alias', '').strip()
        address = request.POST.get('address', '').strip()
        notes = request.POST.get('notes', '').strip()
        credit_limit_raw = request.POST.get('credit_limit', '3000.00').strip()

        if not name:
            return JsonResponse({'success': False, 'error': 'El nombre del cliente es obligatorio.'}, status=400)

        try:
            credit_limit = Decimal(credit_limit_raw)
        except Exception:
            credit_limit = Decimal('3000.00')

        try:
            customer = CustomerCreditService.register_or_link_whatsapp_customer(
                contact_id=conv.contact.id,
                name=name,
                phone=phone,
                alias=alias,
                address=address,
                notes=notes,
                credit_limit=credit_limit,
                user=request.user,
            )
            return JsonResponse({
                'success': True,
                'customer_id': customer.id,
                'customer_name': customer.name,
                'customer_phone': customer.phone,
                'customer_balance': float(customer.current_balance),
                'message': f"Cliente '{customer.name}' registrado exitosamente y vinculado a la conversación."
            })
        except Exception as ex:
            return JsonResponse({'success': False, 'error': str(ex)}, status=400)



class WhatsAppConfigView(LoginRequiredMixin, View):
    def get(self, request):
        from apps.whatsapp.services import WAHAService

        phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
        waba_id = getattr(settings, 'WHATSAPP_BUSINESS_ACCOUNT_ID', '')
        token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
        verify_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '')

        masked_token = f"{token[:10]}...{token[-6:]}" if len(token) > 16 else ("Configurado" if token else "No configurado")
        
        # Webhook URL
        host = request.get_host()
        webhook_url = f"{request.scheme}://{host}/whatsapp/webhook/"

        # Estado WAHA
        waha_url = WAHAService.get_api_url()
        waha_session = WAHAService.get_session()
        waha_health = WAHAService.check_health()
        waha_simulate_typing = getattr(settings, 'WAHA_SIMULATE_TYPING', True)

        return render(request, 'whatsapp/config.html', {
            'webhook_url': webhook_url,
            'phone_id': phone_id,
            'waba_id': waba_id,
            'masked_token': masked_token,
            'verify_token': verify_token,
            'has_credentials': bool(phone_id and token),
            'waha_url': waha_url,
            'waha_session': waha_session,
            'waha_health': waha_health,
            'waha_simulate_typing': waha_simulate_typing,
        })


class WAHAStatusAjaxView(LoginRequiredMixin, View):
    """
    Endpoint AJAX para comprobar en vivo el estado del contenedor WAHA y de la sesión.
    """
    def get(self, request):
        from apps.whatsapp.services import WAHAService
        health = WAHAService.check_health()
        return JsonResponse(health)


class WhatsAppLiveUpdatesView(LoginRequiredMixin, View):
    """
    Endpoint AJAX para sondeo en vivo (real-time live polling):
    - Retorna el conteo total global de mensajes no leídos para badges en el sistema.
    - Retorna lista de conversaciones activas con sus últimos mensajes, estados y saldos de clientes.
    - Retorna mensajes entrantes y salientes nuevos para el chat activo sin requerir recargar la página.
    """
    def get(self, request):
        chat_id = request.GET.get('chat_id')
        last_msg_id = request.GET.get('last_msg_id')

        # 1. Conteo total de no leídos
        total_unread = WhatsAppConversation.objects.aggregate(total=Sum('unread_count'))['total'] or 0

        # 2. Lista de conversaciones activas (primeras 35)
        conv_qs = WhatsAppConversation.objects.select_related('contact__customer').all().order_by('-last_message_at')[:35]
        conversations_data = []
        for c in conv_qs:
            conversations_data.append({
                'id': c.id,
                'name': c.contact.display_name or c.contact.phone,
                'phone': c.contact.phone,
                'last_message': c.last_message_preview,
                'time': timezone.localtime(c.last_message_at).strftime('%d/%m %I:%M %p') if c.last_message_at else '',
                'unread_count': c.unread_count,
                'has_customer': bool(c.contact.customer),
                'customer_id': c.contact.customer.id if c.contact.customer else None,
                'customer_name': c.contact.customer.name if c.contact.customer else '',
                'customer_balance': float(c.contact.customer.current_balance) if c.contact.customer else 0.0,
            })

        # 3. Mensajes nuevos del chat activo
        new_messages = []
        statuses = {}
        chat_info = None

        if chat_id and str(chat_id).isdigit():
            try:
                active_conv = WhatsAppConversation.objects.select_related('contact__customer').get(id=int(chat_id))
                # Limpiar no leídos si el operador tiene el chat abierto
                if active_conv.unread_count > 0:
                    active_conv.unread_count = 0
                    active_conv.save(update_fields=['unread_count'])
                    total_unread = WhatsAppConversation.objects.aggregate(total=Sum('unread_count'))['total'] or 0

                chat_info = {
                    'id': active_conv.id,
                    'name': active_conv.contact.display_name or active_conv.contact.phone,
                    'phone': active_conv.contact.phone,
                    'has_customer': bool(active_conv.contact.customer),
                    'customer_id': active_conv.contact.customer.id if active_conv.contact.customer else None,
                    'customer_name': active_conv.contact.customer.name if active_conv.contact.customer else '',
                    'customer_balance': float(active_conv.contact.customer.current_balance) if active_conv.contact.customer else 0.0,
                }

                msgs_qs = active_conv.messages.all()
                if last_msg_id and str(last_msg_id).isdigit():
                    new_msgs = msgs_qs.filter(id__gt=int(last_msg_id)).order_by('created_at')
                else:
                    new_msgs = []

                for m in new_msgs:
                    new_messages.append({
                        'id': m.id,
                        'direction': m.direction,
                        'message_type': m.message_type,
                        'content': m.content,
                        'media_url': m.media_display_url,
                        'media_mime_type': m.media_mime_type,
                        'is_image': m.is_image,
                        'is_audio': m.is_audio,
                        'is_video': m.is_video,
                        'is_document': m.is_document,
                        'status': m.status,
                        'time': timezone.localtime(m.created_at).strftime('%I:%M %p'),
                        'error_message': m.clean_error_message,
                    })

                # Estados actualizados de los últimos 20 mensajes
                for m in msgs_qs.order_by('-id')[:20]:
                    statuses[m.id] = m.status

            except WhatsAppConversation.DoesNotExist:
                pass

        return JsonResponse({
            'total_unread': total_unread,
            'conversations': conversations_data,
            'new_messages': new_messages,
            'statuses': statuses,
            'chat_info': chat_info,
        })


class WhatsAppDeleteMessageView(LoginRequiredMixin, View):
    """
    Elimina un mensaje individual de la conversación en ColmadoPOS.
    """
    def post(self, request, pk):
        message = get_object_or_404(WhatsAppMessage, pk=pk)
        conv = message.conversation
        message.delete()

        # Recalcular el último mensaje de la conversación
        last_msg = conv.messages.order_by('-created_at').first()
        if last_msg:
            conv.last_message_text = last_msg.content
            conv.last_message_at = last_msg.created_at
        else:
            conv.last_message_text = ""
        conv.save(update_fields=['last_message_text', 'last_message_at'])

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
            return JsonResponse({
                'success': True,
                'message': 'Mensaje eliminado exitosamente',
                'last_message_preview': conv.last_message_preview,
                'remaining_count': conv.messages.count(),
            })

        messages.success(request, 'Mensaje eliminado exitosamente.')
        return redirect(f"/whatsapp/bandeja/?chat={conv.id}")


class WhatsAppDeleteConversationView(LoginRequiredMixin, View):
    """
    Elimina una conversación completa y todos sus mensajes en ColmadoPOS.
    """
    def post(self, request, pk):
        conv = get_object_or_404(WhatsAppConversation, pk=pk)
        contact = conv.contact
        conv.delete()

        # Si el contacto no está registrado como cliente formal y no tiene otros chats, limpiar contacto
        if contact and not contact.customer and not contact.conversations.exists():
            contact.delete()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
            return JsonResponse({
                'success': True,
                'message': 'Conversación eliminada exitosamente',
                'redirect_url': '/whatsapp/bandeja/'
            })

        messages.success(request, 'Conversación eliminada exitosamente.')
        return redirect('whatsapp_inbox')


class WhatsAppMediaProxyView(LoginRequiredMixin, View):
    """
    Entrega o retransmite de forma segura archivos multimedia (imágenes, audios, comprobantes PDF)
    asociados a un mensaje de WhatsApp. Si el archivo no está en caché local, lo solicita a WAHA
    o al servidor externo y lo guarda permanentemente en disco.
    """
    def get(self, request, pk):
        msg = get_object_or_404(WhatsAppMessage, pk=pk)
        if not (msg.media_file or msg.media_url):
            raise Http404("El mensaje no contiene ningún archivo multimedia.")

        # 1. Si ya se descargó y existe en el almacenamiento local
        if msg.media_file:
            try:
                return FileResponse(msg.media_file.open('rb'), content_type=msg.media_mime_type or 'application/octet-stream')
            except Exception:
                pass

        # 2. Si tiene URL remota (servidor WAHA o Meta)
        if msg.media_url:
            try:
                from apps.whatsapp.services import WAHAService
                headers = WAHAService.get_headers() if ('localhost:3000' in msg.media_url or 'api/files' in msg.media_url) else {}
                resp = requests.get(msg.media_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    content_type = resp.headers.get('content-type') or msg.media_mime_type or 'application/octet-stream'

                    # Guardar archivo en disco para caché local
                    try:
                        from django.core.files.base import ContentFile
                        ext = '.jpg'
                        if 'image' in content_type: ext = '.jpg'
                        elif 'audio' in content_type: ext = '.ogg'
                        elif 'video' in content_type: ext = '.mp4'
                        elif 'pdf' in content_type: ext = '.pdf'
                        filename = f"wa_{msg.id}_{msg.created_at.strftime('%Y%m%d%H%M%S')}{ext}"
                        msg.media_file.save(filename, ContentFile(resp.content), save=True)
                    except Exception as ex_save:
                        logger.warning("No se pudo cachear archivo multimedia localmente: %s", ex_save)

                    return HttpResponse(resp.content, content_type=content_type)
            except Exception as e:
                logger.error("Error al obtener media de WhatsApp (id=%s): %s", msg.id, e)

        raise Http404("El archivo multimedia no está disponible.")

