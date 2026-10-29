from django import forms
from decimal import Decimal
from apps.cash.models import CashRegister, CashDenomination

class OpenShiftForm(forms.Form):
    register = forms.ModelChoiceField(
        queryset=CashRegister.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
        label='Caja Física / Terminal'
    )
    initial_cash = forms.DecimalField(
        min_value=Decimal('0.00'),
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '100', 'class': 'w-full px-4 py-3 border border-slate-300 rounded-xl text-lg font-semibold text-slate-800 focus:outline-none focus:border-orange-500'}),
        label='Fondo Inicial de Gaveta (RD$)'
    )
    initial_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Cambio inicial en billetes de 50 y monedas'}),
        label='Observaciones de Apertura'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import BusinessSettings
        settings = BusinessSettings.get_settings()
        if 'initial_cash' not in self.initial or not self.initial['initial_cash']:
            self.fields['initial_cash'].initial = settings.default_initial_cash
