import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.customers.models import Customer, CreditTransaction
from apps.customers.forms import CustomerForm, AbonoPaymentForm
from apps.customers.services import CustomerCreditService

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'customers/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 30

    def get_queryset(self):
        qs = Customer.objects.prefetch_related('credit_transactions').all()
        active_branch_id = self.request.session.get('active_branch_id')
        if active_branch_id:
            qs = qs.filter(Q(branch_id=active_branch_id) | Q(branch__isnull=True))
        q = self.request.GET.get('q', '').strip()
        filtro_deuda = self.request.GET.get('deuda')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(identification__icontains=q))
        
        # Filtrar en python si tiene saldo pendiente
        customer_list = list(qs)
        if filtro_deuda == 'con_deuda':
            customer_list = [c for c in customer_list if c.current_balance > Decimal('0.00')]
        elif filtro_deuda == 'sin_deuda':
            customer_list = [c for c in customer_list if c.current_balance <= Decimal('0.00')]
        return customer_list

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['filtro_deuda'] = self.request.GET.get('deuda', '')
        return ctx


class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'customers/customer_detail.html'
    context_object_name = 'customer'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = self.get_object()
        ctx['transactions'] = customer.credit_transactions.select_related('sale', 'user').prefetch_related('sale__items__product').all()[:100]
        ctx['abono_form'] = AbonoPaymentForm()
        ctx['whatsapp_text'] = CustomerCreditService.generate_whatsapp_summary(customer)
        clean_phone = customer.phone.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
        if clean_phone:
            encoded_msg = urllib.parse.quote(ctx['whatsapp_text'])
            ctx['whatsapp_direct_url'] = f"https://wa.me/{clean_phone}?text={encoded_msg}"
        return ctx


class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'
    success_url = reverse_lazy('customer_list')

    def form_valid(self, form):
        active_branch_id = self.request.session.get('active_branch_id')
        if active_branch_id:
            form.instance.branch_id = active_branch_id
        response = super().form_valid(form)
        messages.success(self.request, f"Cliente '{self.object.name}' registrado en la libreta.")
        return response


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'
    success_url = reverse_lazy('customer_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Datos de '{self.object.name}' actualizados.")
        return response


class RecordAbonoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        form = AbonoPaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            payment_method = form.cleaned_data['payment_method']
            reference = form.cleaned_data['reference']
            notes = form.cleaned_data['notes']

            try:
                tx = CustomerCreditService.record_abono(
                    customer_id=customer.id,
                    amount=amount,
                    payment_method=payment_method,
                    user=request.user,
                    notes=notes,
                    reference=reference,
                )
                messages.success(
                    request,
                    f"Abono de RD$ {amount:,.2f} registrado exitosamente para {customer.name}. Nuevo saldo: RD$ {tx.balance_after:,.2f}."
                )
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('customer_detail', pk=customer.pk)
            except ValidationError as ex:
                messages.error(request, str(ex.message if hasattr(ex, 'message') else ex))
        else:
            messages.error(request, "Datos inválidos en el formulario de abono.")
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('customer_detail', pk=customer.pk)


class CustomerWhatsAppSummaryView(LoginRequiredMixin, View):
    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        summary = CustomerCreditService.generate_whatsapp_summary(customer)
        clean_phone = customer.phone.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
        encoded_msg = urllib.parse.quote(summary)
        wa_url = f"https://wa.me/{clean_phone}?text={encoded_msg}" if clean_phone else "#"
        return render(request, 'customers/whatsapp_summary_modal.html', {
            'customer': customer,
            'summary_text': summary,
            'wa_url': wa_url,
        })
