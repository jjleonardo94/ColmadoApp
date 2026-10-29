from django import forms
from apps.catalog.models import Category, Product

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Bebidas y Licores'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Descripción opcional'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'internal_code', 'barcode', 'category', 'description',
            'unit_of_measure', 'sale_type', 'cost_price', 'sale_price', 'wholesale_price',
            'current_stock', 'min_stock', 'max_stock', 'supplier', 'expiry_date', 'image', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Cerveza Presidente Regular 650ml'}),
            'internal_code': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. BEB-001'}),
            'barcode': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Escanee o escriba código de barras'}),
            'category': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'unit_of_measure': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'sale_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'cost_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'sale_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'wholesale_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'current_stock': forms.NumberInput(attrs={'step': '0.001', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'min_stock': forms.NumberInput(attrs={'step': '0.001', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'max_stock': forms.NumberInput(attrs={'step': '0.001', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'supplier': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'image': forms.FileInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
        }
