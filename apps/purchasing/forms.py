from django import forms
from apps.purchasing.models import Supplier, Purchase

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'tax_id', 'phone', 'email', 'address', 'contact_person', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Cervecería Nacional Dominicana'}),
            'tax_id': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'RNC o Cédula'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Teléfono'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Correo'}),
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'contact_person': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Nombre del preventa o vendedor'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
        }


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'invoice_number', 'purchase_date', 'payment_status', 'tax', 'discount', 'notes']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'invoice_number': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'No. Factura física'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'payment_status': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'tax': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'discount': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
        }
