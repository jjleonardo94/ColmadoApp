from django.shortcuts import render, redirect
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F

from apps.inventory.models import InventoryMovement
from apps.inventory.forms import InventoryAdjustmentForm
from apps.inventory.services import InventoryService
from apps.catalog.models import Product
from apps.core.models import AuditLog

class InventoryMovementListView(LoginRequiredMixin, ListView):
    model = InventoryMovement
    template_name = 'inventory/movement_list.html'
    context_object_name = 'movements'
    paginate_by = 40

    def get_queryset(self):
        qs = InventoryMovement.objects.select_related('product', 'user').all()
        m_type = self.request.GET.get('tipo')
        prod_q = self.request.GET.get('q')
        if m_type:
            qs = qs.filter(movement_type=m_type)
        if prod_q:
            qs = qs.filter(product__name__icontains=prod_q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_type'] = self.request.GET.get('tipo', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class InventoryAdjustmentView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.profile.check_permission('can_adjust_inventory'):
            messages.error(request, "No tiene permisos para realizar ajustes manuales de inventario.")
            return redirect('inventory_list')
        form = InventoryAdjustmentForm()
        return render(request, 'inventory/adjustment_form.html', {'form': form})

    def post(self, request):
        if not request.user.profile.check_permission('can_adjust_inventory'):
            messages.error(request, "No tiene permisos para realizar ajustes manuales de inventario.")
            return redirect('inventory_list')

        form = InventoryAdjustmentForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data['product']
            movement_type = form.cleaned_data['movement_type']
            quantity = form.cleaned_data['quantity']
            reason = form.cleaned_data['reason']

            try:
                movement = InventoryService.process_movement(
                    product_id=product.id,
                    movement_type=movement_type,
                    quantity=quantity,
                    user=request.user,
                    reason=reason,
                    reference_doc="Ajuste Manual de Inventario"
                )
                AuditLog.objects.create(
                    user=request.user,
                    action='AJUSTE_INVENTARIO',
                    target_model='Product',
                    target_id=product.internal_code,
                    details=f"Ajuste {movement_type} de {quantity} en '{product.name}'. Motivo: {reason}. Stock resultante: {movement.new_stock}"
                )
                messages.success(request, f"Ajuste aplicado exitosamente a '{product.name}'. Nuevo stock: {movement.new_stock}.")
                return redirect('inventory_list')
            except ValidationError as ex:
                messages.error(request, str(ex.message if hasattr(ex, 'message') else ex))
        return render(request, 'inventory/adjustment_form.html', {'form': form})


class StockAlertsView(LoginRequiredMixin, View):
    def get(self, request):
        low_stock = [p for p in Product.objects.filter(is_active=True).select_related('category', 'supplier') if p.is_low_stock]
        out_of_stock = [p for p in Product.objects.filter(is_active=True).select_related('category', 'supplier') if p.is_out_of_stock]
        return render(request, 'inventory/alerts.html', {
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
        })
