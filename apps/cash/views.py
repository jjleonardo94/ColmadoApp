from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.cash.models import (
    CashRegister,
    CashShift,
    CashShiftStatus,
    CashDenomination,
    CashMovement,
)
from apps.cash.forms import OpenShiftForm
from apps.cash.services import CashService
from apps.core.models import BusinessSettings

class CashShiftListView(LoginRequiredMixin, ListView):
    model = CashShift
    template_name = 'cash/shift_list.html'
    context_object_name = 'shifts'
    paginate_by = 25

    def get_queryset(self):
        qs = CashShift.objects.select_related('register', 'cashier', 'closed_by', 'difference_authorized_by').all().order_by('-opened_at')
        active_branch_id = self.request.session.get('active_branch_id')
        if active_branch_id:
            qs = qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))

        # Filtros
        date_from = self.request.GET.get('desde')
        date_to = self.request.GET.get('hasta')
        user_id = self.request.GET.get('usuario')
        register_id = self.request.GET.get('caja')
        status = self.request.GET.get('estado')
        has_diff = self.request.GET.get('con_diferencia')

        if date_from:
            qs = qs.filter(opened_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(opened_at__date__lte=date_to)
        if user_id:
            qs = qs.filter(cashier_id=user_id)
        if register_id:
            qs = qs.filter(register_id=register_id)
        if status:
            qs = qs.filter(status=status)
        if has_diff == '1' or has_diff == 'true':
            qs = qs.filter(status=CashShiftStatus.CERRADO).exclude(difference=Decimal('0.00'))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['registers'] = CashRegister.objects.filter(is_active=True)
        ctx['cashiers'] = User.objects.filter(is_active=True).order_by('username')
        ctx['filter_desde'] = self.request.GET.get('desde', '')
        ctx['filter_hasta'] = self.request.GET.get('hasta', '')
        ctx['filter_usuario'] = self.request.GET.get('usuario', '')
        ctx['filter_caja'] = self.request.GET.get('caja', '')
        ctx['filter_estado'] = self.request.GET.get('estado', '')
        ctx['filter_diferencia'] = self.request.GET.get('con_diferencia', '')
        return ctx


class OpenShiftView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.profile.check_permission('can_open_close_shifts'):
            messages.error(request, "No tiene permisos para abrir cierres/turnos de caja.")
            return redirect('cash_shift_list')

        # Verificar si el usuario ya tiene turno abierto
        user_shift = CashShift.objects.filter(cashier=request.user, status=CashShiftStatus.ABIERTO).first()
        if user_shift:
            messages.info(request, f"Ya tiene una caja abierta (#{user_shift.id}) en {user_shift.register.name}.")
            return redirect('cash_shift_detail', pk=user_shift.pk)

        form = OpenShiftForm()
        settings = BusinessSettings.get_settings()
        return render(request, 'cash/open_shift.html', {'form': form, 'settings': settings})

    def post(self, request):
        if not request.user.profile.check_permission('can_open_close_shifts'):
            messages.error(request, "No tiene permisos para abrir cierres/turnos de caja.")
            return redirect('cash_shift_list')

        form = OpenShiftForm(request.POST)
        if form.is_valid():
            register = form.cleaned_data['register']
            initial_cash = form.cleaned_data['initial_cash']
            initial_notes = form.cleaned_data['initial_notes']
            try:
                active_branch_id = request.session.get('active_branch_id')
                shift = CashService.open_shift(
                    register_id=register.id,
                    cashier=request.user,
                    initial_cash=initial_cash,
                    initial_notes=initial_notes,
                    branch_id=active_branch_id,
                )
                messages.success(request, f"Caja #{shift.id} abierta exitosamente en '{register.name}' con fondo RD$ {initial_cash:,.2f}.")
                return redirect('pos')
            except ValidationError as ex:
                messages.error(request, str(ex.message if hasattr(ex, 'message') else ex))
        settings = BusinessSettings.get_settings()
        return render(request, 'cash/open_shift.html', {'form': form, 'settings': settings})


class CloseShiftView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.profile.check_permission('can_open_close_shifts'):
            messages.error(request, "No tiene permisos para cerrar cajas.")
            return redirect('cash_shift_list')

        shift = get_object_or_404(CashShift.objects.select_related('register', 'cashier'), pk=pk)
        if shift.status == CashShiftStatus.CERRADO:
            messages.info(request, "Este cierre de caja ya fue completado previamente.")
            return redirect('cash_shift_detail', pk=shift.pk)

        denominations = CashDenomination.objects.filter(is_active=True).order_by('-value')
        expected_cash = shift.calculate_current_expected_cash()
        movements = shift.cash_movements.all()

        incomes = sum(m.amount for m in movements if m.movement_type == 'INGRESO' and m.category != 'FONDO_INICIAL')
        expenses = sum(m.amount for m in movements if m.movement_type == 'EGRESO')

        audit_summary = shift.get_sales_audit_summary()
        settings = BusinessSettings.get_settings()

        context = {
            'shift': shift,
            'denominations': denominations,
            'expected_cash': expected_cash,
            'incomes': incomes,
            'expenses': expenses,
            'audit': audit_summary,
            'settings': settings,
            'default_closing_fund': settings.default_closing_cash_fund,
            'can_authorize_differences': request.user.profile.check_permission('can_authorize_cash_differences'),
            'credit_sales_detail': shift.get_credit_sales_detail(),
            'transfer_operations_detail': shift.get_transfer_operations_detail(),
            'cash_operations_detail': shift.get_cash_operations_detail(),
            'card_operations_detail': shift.get_card_operations_detail(),
            'abonos_detail': shift.get_abonos_detail(),
        }
        return render(request, 'cash/close_shift.html', context)

    def post(self, request, pk):
        if not request.user.profile.check_permission('can_open_close_shifts'):
            messages.error(request, "No tiene permisos para cerrar cajas.")
            return redirect('cash_shift_list')

        shift = get_object_or_404(CashShift, pk=pk)
        if shift.status == CashShiftStatus.CERRADO:
            messages.info(request, "Este cierre ya se encuentra registrado y sellado.")
            return redirect('cash_shift_detail', pk=shift.pk)

        closing_notes = request.POST.get('closing_notes', '').strip()
        diff_explanation = request.POST.get('difference_explanation', '').strip()
        
        settings = BusinessSettings.get_settings()
        cash_to_remain_raw = request.POST.get('cash_to_remain', '').strip().replace(',', '.')
        try:
            cash_to_remain = Decimal(cash_to_remain_raw) if cash_to_remain_raw else settings.default_closing_cash_fund
        except Exception:
            cash_to_remain = settings.default_closing_cash_fund

        # Conteo de denominaciones
        denominations = CashDenomination.objects.filter(is_active=True)
        denomination_counts = {}
        for denom in denominations:
            field_name = f"denom_{denom.id}"
            qty_val = request.POST.get(field_name, '0').strip()
            try:
                denomination_counts[denom.id] = int(qty_val) if qty_val else 0
            except ValueError:
                denomination_counts[denom.id] = 0

        # Autorización de diferencia si aplica
        diff_authorized_by = None
        if request.user.profile.check_permission('can_authorize_cash_differences') or request.user.is_superuser:
            diff_authorized_by = request.user

        try:
            closed_shift = CashService.close_shift(
                shift_id=shift.id,
                user=request.user,
                denomination_counts=denomination_counts,
                closing_notes=closing_notes,
                difference_explanation=diff_explanation,
                cash_to_remain=cash_to_remain,
                difference_authorized_by=diff_authorized_by,
            )
            messages.success(request, f"Cierre de Caja #{closed_shift.id} sellado exitosamente. Arqueo completado.")
            return redirect('cash_shift_detail', pk=closed_shift.pk)
        except ValidationError as ex:
            messages.error(request, str(ex.message if hasattr(ex, 'message') else ex))
            return redirect('cash_close_shift', pk=shift.pk)


class ShiftDetailView(LoginRequiredMixin, DetailView):
    model = CashShift
    template_name = 'cash/shift_detail.html'
    context_object_name = 'shift'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        shift = self.get_object()
        ctx['movements'] = shift.cash_movements.select_related('user').all()
        ctx['denomination_counts'] = shift.denomination_counts.select_related('denomination').all()
        ctx['settings'] = BusinessSettings.get_settings()
        ctx['audit'] = shift.get_sales_audit_summary()
        ctx['credit_sales_detail'] = shift.get_credit_sales_detail()
        ctx['transfer_operations_detail'] = shift.get_transfer_operations_detail()
        ctx['cash_operations_detail'] = shift.get_cash_operations_detail()
        ctx['card_operations_detail'] = shift.get_card_operations_detail()
        ctx['abonos_detail'] = shift.get_abonos_detail()
        return ctx
