from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q

from apps.catalog.models import Category, Product
from apps.catalog.forms import CategoryForm, ProductForm
from apps.core.models import AuditLog

class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'catalog/product_list.html'
    context_object_name = 'products'
    paginate_by = 30

    def get_queryset(self):
        qs = Product.objects.select_related('category', 'supplier').all()
        q = self.request.GET.get('q', '').strip()
        cat = self.request.GET.get('categoria')
        stock_filter = self.request.GET.get('stock')

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(internal_code__icontains=q) | Q(barcode__icontains=q))
        if cat:
            qs = qs.filter(category_id=cat)
        if stock_filter == 'bajo':
            qs = [p for p in qs if p.is_low_stock]
        elif stock_filter == 'agotado':
            qs = [p for p in qs if p.is_out_of_stock]

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = Category.objects.filter(is_active=True)
        ctx['selected_cat'] = self.request.GET.get('categoria', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['stock_filter'] = self.request.GET.get('stock', '')
        return ctx


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'catalog/product_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.objects.create(
            user=self.request.user,
            action='CREAR_PRODUCTO',
            target_model='Product',
            target_id=self.object.internal_code,
            details=f"Creación del producto '{self.object.name}' con precio RD$ {self.object.sale_price}"
        )
        messages.success(self.request, f"Producto '{self.object.name}' registrado exitosamente.")
        return response


class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'catalog/product_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.objects.create(
            user=self.request.user,
            action='EDITAR_PRODUCTO',
            target_model='Product',
            target_id=self.object.internal_code,
            details=f"Actualización del producto '{self.object.name}'"
        )
        messages.success(self.request, f"Producto '{self.object.name}' actualizado exitosamente.")
        return response


class ProductToggleActiveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.is_active = not product.is_active
        product.save(update_fields=['is_active'])
        status_str = "activado" if product.is_active else "desactivado"
        AuditLog.objects.create(
            user=request.user,
            action='ESTADO_PRODUCTO',
            target_model='Product',
            target_id=product.internal_code,
            details=f"Producto '{product.name}' {status_str} (Soft delete/reactivación)."
        )
        messages.info(request, f"Producto '{product.name}' {status_str}.")
        return redirect('product_list')


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'catalog/category_list.html'
    context_object_name = 'categories'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = CategoryForm()
        return ctx


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'catalog/category_list.html'
    success_url = reverse_lazy('category_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Categoría '{self.object.name}' creada exitosamente.")
        return response
