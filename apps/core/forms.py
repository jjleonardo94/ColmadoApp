from django import forms
from apps.core.models import BusinessSettings, ColmadoBranch

class BusinessSettingsForm(forms.ModelForm):
    class Meta:
        model = BusinessSettings
        fields = [
            'name', 'rnc', 'phone', 'address', 'slogan', 'receipt_footer',
            'usd_rate', 'eur_rate', 'low_stock_threshold', 'allow_negative_stock', 'printer_width',
            'default_initial_cash', 'default_closing_cash_fund', 'delivery_notification_template'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'rnc': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'slogan': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'receipt_footer': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'usd_rate': forms.NumberInput(attrs={'step': '0.0001', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'eur_rate': forms.NumberInput(attrs={'step': '0.0001', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'allow_negative_stock': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
            'printer_width': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
            'default_initial_cash': forms.NumberInput(attrs={'step': '50', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500 font-semibold'}),
            'default_closing_cash_fund': forms.NumberInput(attrs={'step': '50', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500 font-semibold'}),
            'delivery_notification_template': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500 text-sm font-mono'}),
        }


class ColmadoBranchForm(forms.ModelForm):
    class Meta:
        model = ColmadoBranch
        fields = ['name', 'code', 'phone', 'rnc', 'address', 'city', 'manager_name', 'is_main', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Colmado El Progreso #2'}),
            'code': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. SUC-02'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': '(809) 555-0199'}),
            'rnc': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': '1-31-89745-2'}),
            'address': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Calle 3ra #12, Villa Juana'}),
            'city': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Santo Domingo'}),
            'manager_name': forms.TextInput(attrs={'class': 'w-full px-3.5 py-2.5 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Nombre del encargado'}),
            'is_main': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-orange-600 focus:ring-orange-500'}),
        }
