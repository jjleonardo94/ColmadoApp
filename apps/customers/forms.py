from django import forms
from decimal import Decimal
from apps.customers.models import Customer

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'identification', 'address', 'credit_limit', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Doña Carmen Santana'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. 809-555-0123'}),
            'identification': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Cédula o RNC'}),
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Dirección o referencia del colmado'}),
            'credit_limit': forms.NumberInput(attrs={'step': '100', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
        }


class AbonoPaymentForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-4 py-3 border border-slate-300 rounded-xl text-lg font-semibold text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': '0.00'}),
        label='Monto a Abonar (RD$)'
    )
    payment_method = forms.ChoiceField(
        choices=[
            ('EFECTIVO', 'Efectivo (Entra a la Caja)'),
            ('TRANSFERENCIA', 'Transferencia Bancaria'),
            ('TARJETA', 'Tarjeta'),
            ('OTRO', 'Otro Método'),
        ],
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
        label='Método de Cobro'
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. No. Transf. Banreservas o recibo firmado'}),
        label='Referencia / No. Comprobante'
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Observaciones'}),
        label='Observaciones'
    )
