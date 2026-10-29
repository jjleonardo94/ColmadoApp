from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction

from apps.expenses.models import Expense, ExpenseCategory, ExpensePaymentMethod
from apps.expenses.forms import ExpenseForm
from apps.cash.models import CashShift, CashShiftStatus, CashMovement, CashMovementType
from apps.core.models import AuditLog

from django.db.models import Q

class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = 'expenses/expense_list.html'
    context_object_name = 'expenses'
    paginate_by = 30

    def get_queryset(self):
        qs = Expense.objects.select_related('category', 'user', 'cash_shift').all()
        active_branch_id = self.request.session.get('active_branch_id')
        if active_branch_id:
            qs = qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))
        cat_id = self.request.GET.get('categoria')
        method = self.request.GET.get('metodo')
        date_str = self.request.GET.get('fecha')

        if cat_id:
            qs = qs.filter(category_id=cat_id)
        if method:
            qs = qs.filter(payment_method=method)
        if date_str:
            qs = qs.filter(date=date_str)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = ExpenseCategory.objects.filter(is_active=True)
        ctx['selected_cat'] = self.request.GET.get('categoria', '')
        ctx['selected_method'] = self.request.GET.get('metodo', '')
        ctx['selected_date'] = self.request.GET.get('fecha', '')
        return ctx


class ExpenseCreateView(LoginRequiredMixin, View):
    def get(self, request):
        form = ExpenseForm()
        return render(request, 'expenses/expense_form.html', {'form': form})

    def post(self, request):
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                expense = form.save(commit=False)
                expense.user = request.user
                active_branch_id = request.session.get('active_branch_id')
                if active_branch_id:
                    expense.branch_id = active_branch_id

                # Si se paga en efectivo y está pagado, vincular al turno de caja abierto
                if expense.payment_method == ExpensePaymentMethod.EFECTIVO and expense.is_paid:
                    shift = CashShift.objects.filter(cashier=request.user, status=CashShiftStatus.ABIERTO).first()
                    if not shift:
                        shift = CashShift.objects.filter(status=CashShiftStatus.ABIERTO).first()
                    
                    if shift:
                        expense.cash_shift = shift
                        CashMovement.objects.create(
                            shift=shift,
                            movement_type=CashMovementType.EGRESO,
                            category='GASTO_CAJA',
                            amount=expense.amount,
                            description=f"Gasto: {expense.category.name} - {expense.description}",
                            user=request.user,
                        )

                expense.save()

                AuditLog.objects.create(
                    user=request.user,
                    action='REGISTRO_GASTO',
                    target_model='Expense',
                    target_id=str(expense.id),
                    details=f"Gasto de RD$ {expense.amount:,.2f} en '{expense.category.name}' ({expense.get_payment_method_display()})"
                )

            messages.success(request, f"Gasto de RD$ {expense.amount:,.2f} registrado exitosamente.")
            return redirect('expense_list')

        return render(request, 'expenses/expense_form.html', {'form': form})
