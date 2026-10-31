import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.core.models import BusinessSettings
from apps.catalog.models import Product, Category
from apps.customers.models import Customer
from apps.cash.models import CashShift, CashShiftStatus
from apps.sales.models import (
    Sale, SaleItem, Payment, SaleStatus,
    DeliveryPerson, DeliveryOrder, DeliveryStatus
)
from apps.sales.forms import DeliveryPersonForm
from apps.sales.services import SaleService, DeliveryService

class POSView(LoginRequiredMixin, View):
    def get(self, request):
        active_branch_id = request.session.get('active_branch_id')
        shift_qs = CashShift.objects.filter(status=CashShiftStatus.ABIERTO)
        if active_branch_id:
            shift_qs = shift_qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))

        active_shift = shift_qs.filter(cashier=request.user).first()
        if not active_shift:
            active_shift = shift_qs.first()

        categories = Category.objects.filter(is_active=True).prefetch_related('products')
        cust_qs = Customer.objects.filter(is_active=True)
        if active_branch_id:
            cust_qs = cust_qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))
        customers = cust_qs.order_by('name')
        settings = BusinessSettings.get_settings()
        
        # Productos frecuentes (primeros 24 productos activos con stock)
        popular_products = Product.objects.filter(is_active=True).select_related('category')[:30]

        context = {
            'active_shift': active_shift,
            'categories': categories,
            'customers': customers,
            'settings': settings,
            'popular_products': popular_products,
        }
        return render(request, 'pos/pos_screen.html', context)


class ProductSearchAPIView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        cat_id = request.GET.get('categoria')

        products_qs = Product.objects.filter(is_active=True)
        if cat_id:
            products_qs = products_qs.filter(category_id=cat_id)

        if q:
            # Buscar por código exacto de barras o interno primero (escáner)
            exact_match = products_qs.filter(Q(barcode=q) | Q(internal_code__iexact=q)).first()
            if exact_match:
                return JsonResponse({
                    'exact_match': True,
                    'products': [{
                        'id': exact_match.id,
                        'name': exact_match.name,
                        'internal_code': exact_match.internal_code,
                        'barcode': exact_match.barcode or '',
                        'sale_price': str(exact_match.sale_price),
                        'current_stock': str(exact_match.current_stock),
                        'sale_type': exact_match.sale_type,
                        'unit_of_measure': exact_match.get_unit_of_measure_display(),
                        'allows_decimals': exact_match.allows_decimals,
                    }]
                })

            products_qs = products_qs.filter(
                Q(name__icontains=q) | Q(internal_code__icontains=q) | Q(barcode__icontains=q)
            )

        products_data = []
        for p in products_qs[:20]:
            products_data.append({
                'id': p.id,
                'name': p.name,
                'internal_code': p.internal_code,
                'barcode': p.barcode or '',
                'sale_price': str(p.sale_price),
                'current_stock': str(p.current_stock),
                'sale_type': p.sale_type,
                'unit_of_measure': p.get_unit_of_measure_display(),
                'allows_decimals': p.allows_decimals,
            })

        return JsonResponse({'exact_match': False, 'products': products_data})


class CreateSaleAPIView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)

        items_data = data.get('items', [])
        payments_data = data.get('payments', [])
        customer_id = data.get('customer_id') or None
        received_currency = data.get('currency', 'DOP')
        amount_received = Decimal(str(data.get('amount_received', '0.00')))
        notes = data.get('notes', '')
        send_whatsapp = bool(data.get('send_whatsapp', False))
        whatsapp_phone = data.get('whatsapp_phone') or None

        try:
            active_branch_id = request.session.get('active_branch_id')
            sale = SaleService.create_sale(
                cashier=request.user,
                items_data=items_data,
                payments_data=payments_data,
                customer_id=customer_id,
                received_currency=received_currency,
                amount_received=amount_received,
                notes=notes,
                branch_id=active_branch_id,
            )

            # Envío automático de recibo por WhatsApp si fue solicitado
            whatsapp_result = None
            if send_whatsapp:
                whatsapp_result = SaleService.send_sale_whatsapp_receipt(
                    sale=sale,
                    phone_number=whatsapp_phone,
                    user=request.user
                )

            return JsonResponse({
                'success': True,
                'ticket_number': sale.ticket_number,
                'total': str(sale.total),
                'change': str(sale.change_given),
                'receipt_url': f"/pos/recibo/{sale.ticket_number}/",
                'whatsapp_sent': whatsapp_result.get('success', False) if whatsapp_result else False,
                'whatsapp_message': whatsapp_result.get('message', '') if whatsapp_result else '',
            })
        except ValidationError as ex:
            msg = ex.message if hasattr(ex, 'message') else str(ex)
            return JsonResponse({'success': False, 'error': msg}, status=400)
        except Exception as ex:
            return JsonResponse({'success': False, 'error': f"Error interno: {str(ex)}"}, status=500)


class SendSaleWhatsAppAPIView(LoginRequiredMixin, View):
    def post(self, request, ticket_number):
        sale = get_object_or_404(Sale, ticket_number=ticket_number)
        phone = None
        if request.body:
            try:
                body = json.loads(request.body)
                phone = body.get('phone')
            except Exception:
                pass
        
        result = SaleService.send_sale_whatsapp_receipt(
            sale=sale,
            phone_number=phone,
            user=request.user
        )
        return JsonResponse(result, status=200 if result.get('success') else 400)


class SaleListView(LoginRequiredMixin, ListView):
    model = Sale
    template_name = 'pos/sale_list.html'
    context_object_name = 'sales'
    paginate_by = 30

    def get_queryset(self):
        qs = Sale.objects.select_related('customer', 'cashier').all()
        active_branch_id = self.request.session.get('active_branch_id')
        if active_branch_id:
            qs = qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))
        q = self.request.GET.get('q')
        status = self.request.GET.get('estado')
        date_str = self.request.GET.get('fecha')
        
        if q:
            qs = qs.filter(Q(ticket_number__icontains=q) | Q(customer__name__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if date_str:
            qs = qs.filter(created_at__date=date_str)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['status_filter'] = self.request.GET.get('estado', '')
        ctx['date_filter'] = self.request.GET.get('fecha', '')
        return ctx


class SaleReceiptView(LoginRequiredMixin, DetailView):
    model = Sale
    template_name = 'pos/receipt.html'
    context_object_name = 'sale'

    def get_object(self):
        return get_object_or_404(
            Sale.objects.select_related('customer', 'cashier', 'cash_shift').prefetch_related('items__product', 'payments'),
            ticket_number=self.kwargs['ticket_number']
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['settings'] = BusinessSettings.get_settings()
        return ctx


class VoidSaleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not request.user.profile.check_permission('can_void_sales'):
            messages.error(request, "No tiene permisos para anular ventas.")
            return redirect('sale_list')

        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, "Debe especificar un motivo detallado para anular la venta.")
            return redirect('sale_list')

        try:
            sale = SaleService.void_sale(sale_id=pk, user=request.user, void_reason=reason)
            messages.success(request, f"La venta {sale.ticket_number} ha sido anulada exitosamente. Se restableció el inventario.")
        except ValidationError as ex:
            messages.error(request, str(ex.message if hasattr(ex, 'message') else ex))
        return redirect('sale_list')


# ==============================================================================
# GESTIÓN DE REPARTIDORES / DELIVERY
# ==============================================================================

class DeliveryPersonListView(LoginRequiredMixin, ListView):
    model = DeliveryPerson
    template_name = 'sales/delivery_persons.html'
    context_object_name = 'delivery_persons'

    def get_queryset(self):
        active_branch_id = self.request.session.get('active_branch_id')
        qs = DeliveryPerson.objects.all().order_by('-is_active', 'name')
        if active_branch_id:
            qs = qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(vehicle__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = DeliveryPersonForm()
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class DeliveryPersonCreateView(LoginRequiredMixin, View):
    def post(self, request):
        if not (request.user.is_superuser or request.user.profile.check_permission('can_manage_deliveries') or request.user.profile.check_permission('can_manage_settings')):
            messages.error(request, "No tiene permisos para agregar repartidores.")
            return redirect('delivery_person_list')

        form = DeliveryPersonForm(request.POST)
        if form.is_valid():
            dp = form.save(commit=False)
            active_branch_id = request.session.get('active_branch_id')
            if active_branch_id:
                dp.branch_id = active_branch_id
            dp.save()
            messages.success(request, f"Repartidor '{dp.name}' registrado exitosamente.")
        else:
            messages.error(request, "Error al registrar el repartidor. Verifique los campos.")
        return redirect('delivery_person_list')


class DeliveryPersonUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not (request.user.is_superuser or request.user.profile.check_permission('can_manage_deliveries') or request.user.profile.check_permission('can_manage_settings')):
            messages.error(request, "No tiene permisos para modificar repartidores.")
            return redirect('delivery_person_list')

        dp = get_object_or_404(DeliveryPerson, pk=pk)
        form = DeliveryPersonForm(request.POST, instance=dp)
        if form.is_valid():
            form.save()
            messages.success(request, f"Datos del repartidor '{dp.name}' actualizados.")
        else:
            messages.error(request, "Error al actualizar el repartidor.")
        return redirect('delivery_person_list')


class DeliveryPersonToggleActiveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not (request.user.is_superuser or request.user.profile.check_permission('can_manage_deliveries') or request.user.profile.check_permission('can_manage_settings')):
            return JsonResponse({'success': False, 'error': 'Permiso denegado'}, status=403)

        dp = get_object_or_404(DeliveryPerson, pk=pk)
        dp.is_active = not dp.is_active
        dp.save(update_fields=['is_active'])
        return JsonResponse({'success': True, 'is_active': dp.is_active, 'name': dp.name})


# ==============================================================================
# DELIVERY EXPRESS - APIS DE PEDIDOS PENDIENTES Y DESPACHO
# ==============================================================================

class DeliveryExpressPendingAPIView(LoginRequiredMixin, View):
    """
    Retorna el conteo y la lista de pedidos pendientes de entrega (Delivery Express).
    Alimenta el badge numérico y el drawer lateral interactivo.
    """
    def get(self, request):
        pending_qs = DeliveryOrder.objects.filter(
            status__in=[DeliveryStatus.PENDIENTE_ENVIO, DeliveryStatus.PREPARANDO]
        ).select_related('sale', 'customer', 'delivery_person', 'whatsapp_conversation__contact').order_by('created_at')

        active_branch_id = request.session.get('active_branch_id')
        if active_branch_id:
            pending_qs = pending_qs.filter(Q(sale__branch_id=active_branch_id) | Q(sale__branch__isnull=True))

        orders_data = []
        for o in pending_qs:
            items_summary = []
            for it in o.sale.items.select_related('product').all()[:4]:
                items_summary.append(f"{it.quantity:g}x {it.product.name}")
            if o.sale.items.count() > 4:
                items_summary.append(f"+{o.sale.items.count() - 4} más")

            customer_name = (
                o.customer.name if o.customer
                else (o.whatsapp_conversation.contact.display_name if o.whatsapp_conversation and o.whatsapp_conversation.contact else 'Cliente Mostrador')
            )
            customer_phone = (
                o.customer.phone if o.customer
                else (o.whatsapp_conversation.contact.phone if o.whatsapp_conversation and o.whatsapp_conversation.contact else '')
            )

            orders_data.append({
                'id': o.id,
                'sale_id': o.sale.id,
                'ticket_number': o.sale.ticket_number,
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'total': f"{o.sale.total:,.2f}",
                'total_raw': float(o.sale.total),
                'payment_method': o.sale.get_payment_method_display(),
                'items_summary': ', '.join(items_summary) if items_summary else 'Provisiones varias',
                'delivery_address': o.delivery_address or (o.customer.address if o.customer else 'Entrega local'),
                'delivery_person_id': o.delivery_person_id,
                'delivery_person_name': o.delivery_person.name if o.delivery_person else 'Sin Asignar',
                'status': o.status,
                'status_display': o.get_status_display(),
                'created_at': o.created_at.strftime('%I:%M %p'),
                'notes': o.notes,
            })

        dp_qs = DeliveryPerson.objects.filter(is_active=True).order_by('name')
        if active_branch_id:
            dp_qs = dp_qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))

        deliveries_data = [{'id': dp.id, 'name': dp.name, 'vehicle': dp.vehicle} for dp in dp_qs]

        return JsonResponse({
            'count': len(orders_data),
            'orders': orders_data,
            'delivery_persons': deliveries_data,
        })


class DeliveryExpressDispatchAPIView(LoginRequiredMixin, View):
    """
    Despacha un pedido individual de Delivery Express.
    Pasa a EN_CAMINO y envía mensaje individual y personalizado por WhatsApp con datos reales.
    """
    def post(self, request, pk):
        delivery_person_id = request.POST.get('delivery_person_id') or None
        if delivery_person_id:
            try:
                delivery_person_id = int(delivery_person_id)
            except ValueError:
                delivery_person_id = None

        try:
            res = DeliveryService.dispatch_delivery_order(
                delivery_order_id=pk,
                user=request.user,
                delivery_person_id=delivery_person_id
            )
            return JsonResponse(res)
        except Exception as ex:
            return JsonResponse({'success': False, 'error': str(ex)}, status=400)


class DeliveryExpressDispatchAllAPIView(LoginRequiredMixin, View):
    """
    Despacha todos los pedidos pendientes de manera independiente,
    enviando el mensaje personalizado a cada cliente (jamás mensajes grupales).
    """
    def post(self, request):
        delivery_person_id = request.POST.get('delivery_person_id') or None
        if delivery_person_id:
            try:
                delivery_person_id = int(delivery_person_id)
            except ValueError:
                delivery_person_id = None

        try:
            results = DeliveryService.dispatch_all_pending(
                user=request.user,
                delivery_person_id=delivery_person_id
            )
            sent_count = sum(1 for r in results if r.get('success'))
            return JsonResponse({
                'success': True,
                'total_processed': len(results),
                'dispatched_count': sent_count,
                'results': results,
            })
        except Exception as ex:
            return JsonResponse({'success': False, 'error': str(ex)}, status=400)


class DeliveryExpressMarkDeliveredAPIView(LoginRequiredMixin, View):
    """
    Marca un pedido como ENTREGADO.
    """
    def post(self, request, pk):
        try:
            order = DeliveryService.mark_as_delivered(delivery_order_id=pk, user=request.user)
            return JsonResponse({
                'success': True,
                'id': order.id,
                'status': order.status,
                'status_display': order.get_status_display(),
            })
        except Exception as ex:
            return JsonResponse({'success': False, 'error': str(ex)}, status=400)


class DeliveryExpressAssignDeliveryAPIView(LoginRequiredMixin, View):
    """
    Asigna o actualiza el repartidor para una orden de delivery pendiente.
    """
    def post(self, request, pk):
        dp_id = request.POST.get('delivery_person_id')
        order = get_object_or_404(DeliveryOrder, pk=pk)
        if dp_id:
            dp = get_object_or_404(DeliveryPerson, pk=dp_id, is_active=True)
            order.delivery_person = dp
        else:
            order.delivery_person = None
        order.save(update_fields=['delivery_person'])
        return JsonResponse({
            'success': True,
            'id': order.id,
            'delivery_person_id': order.delivery_person_id,
            'delivery_person_name': order.delivery_person.name if order.delivery_person else 'Sin Asignar',
        })

