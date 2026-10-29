from django import forms
from decimal import Decimal
from apps.catalog.models import Product
from apps.inventory.models import MovementType

class InventoryAdjustmentForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
        label='Producto a Ajustar'
    )
    movement_type = forms.ChoiceField(
        choices=[
            (MovementType.AJUSTE_POSITIVO, 'Ajuste Positivo (+ Entrada por conteo o sobrante)'),
            (MovementType.AJUSTE_NEGATIVO, 'Ajuste Negativo (- Salida por diferencia de inventario)'),
            (MovementType.MERMA_DANADO, 'Merma / Avería (- Producto dañado, vencido o roto)'),
        ],
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500'}),
        label='Tipo de Ajuste'
    )
    quantity = forms.DecimalField(
        min_value=Decimal('0.001'),
        decimal_places=3,
        widget=forms.NumberInput(attrs={'step': '0.001', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. 5.0 o 0.5'}),
        label='Cantidad del Ajuste'
    )
    reason = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:border-orange-500', 'placeholder': 'Ej. Botella rota accidentalmente en estante'}),
        label='Motivo / Justificación'
    )
