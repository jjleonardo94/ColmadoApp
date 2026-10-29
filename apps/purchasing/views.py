from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.purchasing.models import Supplier, Purchase, PurchaseItem, PurchaseStatus
from apps.purchasing.forms import SupplierForm, PurchaseForm
from apps.purchasing.services import PurchaseService
from apps.catalog.models import Product

class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = 'purchasing/supplier_list.html'
    context_object_name = 'suppliers'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = SupplierForm()
        return ctx


class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchasing/supplier_list.html'
    success_url = reverse_lazy('supplier_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Suplidor '{self.object.name}' registrado exitosamente.")
        return response


class PurchaseListView(LoginRequiredMixin, ListView):
    model = Purchase
    template_name = 'purchasing/purchase_list.html'
    context_object_name = 'purchases'
    paginate_by = 30

    def get_queryset(self):
        return Purchase.objects.select_related('supplier', 'created_by', 'received_by').all().order_by('-purchase_date', '-created_at')


class PurchaseCreateView(LoginRequiredMixin, View):
    def get(self, request):
        form = PurchaseForm()
        products = Product.objects.filter(is_active=True).order_by('name')
        return render(request, 'purchasing/purchase_form.html', {'form': form, 'products': products})

    def post(self, request):
        form = PurchaseForm(request.POST)
        if form.is_valid():
            supplier = form.cleaned_data['supplier']
            invoice_num = form.cleaned_data['invoice_number']
            purchase_date = form.cleaned_data['purchase_date']
            payment_status = form.cleaned_data['payment_status']
            tax = form.cleaned_data['tax'] or Decimal('0.00')
            discount = form.cleaned_data['discount'] or Decimal('0.00')
            notes = form.cleaned_data['notes']

            product_ids = request.POST.getlist('product_id[]')
            quantities = request.POST.getlist('quantity[]')
            unit_costs = request.POST.getlist('unit_cost[]')

            if not product_ids:
                messages.error(request, "Debe agregar al menos un producto a la compra.")
                return render(request, 'purchasing/purchase_form.html', {'form': form, 'products': Product.objects.filter(is_active=True)})

            with transaction.atomic():
                purchase = Purchase.objects.create(
                    supplier=supplier,
                    invoice_number=invoice_num,
                    purchase_date=purchase_date,
                    status=PurchaseStatus.BORRADOR,
                    payment_status=payment_status,
                    tax=tax,
                    discount=discount,
                    notes=notes,
                    created_by=request.user,
                )

                subtotal = Decimal('0.00')
                for p_id, q_val, c_val in zip(product_ids, quantities, unit_costs):
                    p_obj = Product.objects.get(pk=p_id)
                    qty = Decimal(q_val)
                    cost = Decimal(c_val)
                    line_sub = qty * cost
                    subtotal += line_sub

                    PurchaseItem.objects.create(
                        purchase=purchase,
                        product=p_obj,
                        quantity=qty,
                        unit_cost=cost,
                        subtotal=line_sub,
                    )

                purchase.subtotal = subtotal
                purchase.total = subtotal + tax - discount
                purchase.save()

            messages.success(request, f"Compra #{purchase.id} registrada en borrador. Confirme la recepción para actualizar inventario.")
            return redirect('purchase_list')

        return render(request, 'purchasing/purchase_form.html', {'form': form, 'products': Product.objects.filter(is_active=True)})


class ReceivePurchaseView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            purchase = PurchaseService.receive_purchase(purchase_id=pk, user=request.user)
            messages.success(
                request,
                f"Compra #{purchase.id} confirmada como recibida. El inventario y costos de compra fueron actualizados."
            )
        except ValidationError as ex:
            messages.error(request, str(ex.message if hasattr(ex, 'message') else ex))
        return redirect('purchase_list')
