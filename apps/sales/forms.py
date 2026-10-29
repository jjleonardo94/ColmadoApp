from django import forms
from apps.sales.models import DeliveryPerson

class DeliveryPersonForm(forms.ModelForm):
    class Meta:
        model = DeliveryPerson
        fields = ['name', 'phone', 'vehicle', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500',
                'placeholder': 'Ej. Carlos Sánchez',
                'required': True,
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500',
                'placeholder': 'Ej. (809) 555-0199',
            }),
            'vehicle': forms.TextInput(attrs={
                'class': 'w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500',
                'placeholder': 'Ej. Motor Honda CG / Placa K12345',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-orange-600 rounded border-slate-300 focus:ring-orange-500',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500',
                'rows': 2,
                'placeholder': 'Zona de reparto, turno o notas adicionales...',
            }),
        }
