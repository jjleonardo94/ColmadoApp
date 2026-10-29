from django import forms
from apps.expenses.models import Expense, ExpenseCategory

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date', 'category', 'description', 'amount', 'payment_method', 'is_paid', 'voucher_image']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'category': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'description': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Factura eléctrica Edesur del mes'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': '0.00'}),
            'payment_method': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'is_paid': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
            'voucher_image': forms.FileInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
        }
