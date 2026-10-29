import json
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.db.models import Sum, Count, F, Q

from apps.core.models import BusinessSettings, AuditLog, ColmadoBranch
from apps.core.forms import BusinessSettingsForm, ColmadoBranchForm
from apps.sales.models import Sale, SaleItem, Payment, SaleStatus, PaymentMethodChoices
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.cash.models import CashShift, CashShiftStatus
from apps.expenses.models import Expense

class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        today = timezone.localdate()
        date_filter_str = request.GET.get('fecha')
        selected_date = today
        if date_filter_str:
            try:
                selected_date = timezone.datetime.strptime(date_filter_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = today

        active_branch_id = request.session.get('active_branch_id')
        branch_q = Q(branch_id=active_branch_id) if active_branch_id else Q()

        # 1. Ventas del día seleccionado
        sales_qs = Sale.objects.filter(branch_q, created_at__date=selected_date, status=SaleStatus.COMPLETADA)
        sales_today_total = sales_qs.aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        transactions_count = sales_qs.count()

        # Métodos de pago del día
        cash_payments_today = Payment.objects.filter(
            sale__in=sales_qs,
            payment_method=PaymentMethodChoices.EFECTIVO
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        other_payments_today = Payment.objects.filter(
            sale__in=sales_qs
        ).exclude(
            payment_method__in=[PaymentMethodChoices.EFECTIVO, PaymentMethodChoices.FIADO]
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        fiado_sales_today = Payment.objects.filter(
            sale__in=sales_qs,
            payment_method=PaymentMethodChoices.FIADO
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # 2. Cuentas por cobrar totales acumuladas
        active_customers = Customer.objects.filter(branch_q, is_active=True)
        total_accounts_receivable = sum(c.current_balance for c in active_customers if c.current_balance > 0)

        # 3. Gastos del día
        expenses_today = Expense.objects.filter(branch_q, date=selected_date, is_paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # 4. Ganancia bruta estimada del día (Venta total - Costo histórico de los productos vendidos)
        sale_items_today = SaleItem.objects.filter(sale__in=sales_qs)
        total_cost_today = sum(item.quantity * item.unit_cost for item in sale_items_today)
        gross_profit_today = sales_today_total - total_cost_today
        net_profit_today = gross_profit_today - expenses_today

        # 5. Alertas de inventario
        low_stock_products = Product.objects.filter(
            is_active=True,
            current_stock__lte=F('min_stock'),
            current_stock__gt=Decimal('0.000')
        ).count()

        out_of_stock_products = Product.objects.filter(
            is_active=True,
            current_stock__lte=Decimal('0.000')
        ).count()

        # 6. Caja actualmente abierta
        open_shift = CashShift.objects.filter(branch_q, status=CashShiftStatus.ABIERTO).select_related('register', 'cashier').first()

        # 7. Gráfico: Ventas de los últimos 7 días
        days_chart_labels = []
        days_chart_data = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_total = Sale.objects.filter(created_at__date=d, status=SaleStatus.COMPLETADA).aggregate(t=Sum('total'))['t'] or Decimal('0.00')
            days_chart_labels.append(d.strftime('%d/%m'))
            days_chart_data.append(float(day_total))

        # 8. Gráfico: Métodos de pago hoy
        payment_methods_chart = {
            'labels': ['Efectivo', 'Tarjeta', 'Transferencia', 'Fiado'],
            'data': [
                float(cash_payments_today),
                float(Payment.objects.filter(sale__in=sales_qs, payment_method=PaymentMethodChoices.TARJETA).aggregate(t=Sum('amount'))['t'] or 0),
                float(Payment.objects.filter(sale__in=sales_qs, payment_method=PaymentMethodChoices.TRANSFERENCIA).aggregate(t=Sum('amount'))['t'] or 0),
                float(fiado_sales_today),
            ]
        }

        # 9. Top 5 productos más vendidos del mes
        first_day_month = today.replace(day=1)
        top_products = SaleItem.objects.filter(
            sale__created_at__date__gte=first_day_month,
            sale__status=SaleStatus.COMPLETADA
        ).values('product__name').annotate(
            total_qty=Sum('quantity'),
            total_amount=Sum('subtotal')
        ).order_by('-total_amount')[:5]

        # 10. Últimas 5 ventas del día
        recent_sales = sales_qs.select_related('customer', 'cashier').order_by('-created_at')[:5]

        context = {
            'selected_date': selected_date,
            'sales_today_total': sales_today_total,
            'transactions_count': transactions_count,
            'cash_payments_today': cash_payments_today,
            'other_payments_today': other_payments_today,
            'fiado_sales_today': fiado_sales_today,
            'total_accounts_receivable': total_accounts_receivable,
            'expenses_today': expenses_today,
            'gross_profit_today': gross_profit_today,
            'net_profit_today': net_profit_today,
            'low_stock_products': low_stock_products,
            'out_of_stock_products': out_of_stock_products,
            'open_shift': open_shift,
            'days_chart_labels_json': json.dumps(days_chart_labels),
            'days_chart_data_json': json.dumps(days_chart_data),
            'payment_chart_json': json.dumps(payment_methods_chart),
            'top_products': top_products,
            'recent_sales': recent_sales,
        }
        return render(request, 'dashboard/index.html', context)


class BusinessSettingsView(LoginRequiredMixin, View):
    def get(self, request):
        if not (request.user.is_superuser or request.user.profile.check_permission('can_manage_settings') or request.user.profile.check_permission('can_manage_cash_settings')):
            messages.error(request, "No tiene permisos para modificar las configuraciones del sistema o de caja.")
            return redirect('dashboard')
        settings_obj = BusinessSettings.get_settings()
        form = BusinessSettingsForm(instance=settings_obj)
        return render(request, 'core/settings.html', {'form': form, 'settings': settings_obj})

    def post(self, request):
        if not (request.user.is_superuser or request.user.profile.check_permission('can_manage_settings') or request.user.profile.check_permission('can_manage_cash_settings')):
            messages.error(request, "No tiene permisos para modificar las configuraciones del sistema o de caja.")
            return redirect('dashboard')
        settings_obj = BusinessSettings.get_settings()
        form = BusinessSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user,
                action='ACTUALIZAR_CONFIGURACION',
                target_model='BusinessSettings',
                target_id='1',
                details="Configuraciones del colmado y parámetros de caja actualizados exitosamente."
            )
            messages.success(request, "Configuraciones del colmado actualizadas exitosamente.")
            return redirect('business_settings')
        return render(request, 'core/settings.html', {'form': form, 'settings': settings_obj})


class AuditLogListView(LoginRequiredMixin, ListView):
    model = AuditLog
    template_name = 'core/audit_log.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related('user').all()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(action__icontains=q) | Q(details__icontains=q) | Q(user__username__icontains=q))
        return qs


class BranchListView(LoginRequiredMixin, ListView):
    model = ColmadoBranch
    template_name = 'core/branches.html'
    context_object_name = 'branches'

    def get_queryset(self):
        return ColmadoBranch.objects.all().order_by('-is_main', 'name')


class BranchCreateView(LoginRequiredMixin, CreateView):
    model = ColmadoBranch
    form_class = ColmadoBranchForm
    template_name = 'core/branch_form.html'
    success_url = reverse_lazy('branch_list')

    def form_valid(self, form):
        if form.cleaned_data.get('is_main'):
            ColmadoBranch.objects.filter(is_main=True).update(is_main=False)
        response = super().form_valid(form)
        messages.success(self.request, f"Colmado / Sucursal '{self.object.name}' creada exitosamente.")
        return response


class BranchUpdateView(LoginRequiredMixin, UpdateView):
    model = ColmadoBranch
    form_class = ColmadoBranchForm
    template_name = 'core/branch_form.html'
    success_url = reverse_lazy('branch_list')

    def form_valid(self, form):
        if form.cleaned_data.get('is_main'):
            ColmadoBranch.objects.filter(is_main=True).exclude(pk=self.object.pk).update(is_main=False)
        response = super().form_valid(form)
        messages.success(self.request, f"Datos de '{self.object.name}' actualizados correctamente.")
        return response


class SwitchBranchView(LoginRequiredMixin, View):
    def get(self, request, pk):
        branch = get_object_or_404(ColmadoBranch, pk=pk, is_active=True)
        if not (request.user.is_superuser or request.user.profile.can_access_branch(branch.id)):
            messages.error(request, f"Acceso denegado: No está asignado ni autorizado para operar en '{branch.name}'.")
            return redirect('dashboard')
        request.session['active_branch_id'] = branch.id
        messages.success(request, f"Colmado activo: {branch.name}")
        next_url = request.META.get('HTTP_REFERER')
        if not next_url or 'cambiar' in next_url:
            next_url = reverse_lazy('dashboard')
        return redirect(next_url)
