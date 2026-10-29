from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from apps.accounts.models import UserProfile, CustomRole, UserRole
from apps.core.models import ColmadoBranch

CHECKBOX_STYLE = 'rounded border-slate-300 text-orange-600 focus:ring-orange-500 h-4 w-4'

class ColmadoLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent transition-all',
            'placeholder': 'Nombre de usuario (ej. admin o cajero)',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent transition-all',
            'placeholder': 'Contraseña',
        })
    )


class CustomRoleForm(forms.ModelForm):
    class Meta:
        model = CustomRole
        fields = [
            'name', 'description',
            # POS
            'can_access_pos', 'can_apply_discounts', 'can_change_prices', 'can_void_sales', 'can_view_sales_history',
            # Fiados
            'can_access_credit', 'can_authorize_credit', 'can_record_abono', 'can_manage_customers',
            # Catalogo
            'can_access_catalog', 'can_edit_products', 'can_adjust_inventory', 'can_access_purchases',
            # Caja
            'can_open_close_shifts', 'can_view_cash_history', 'can_register_expenses',
            # Reportes
            'can_view_reports', 'can_export_reports', 'can_view_audit_log',
            # Administracion
            'can_manage_whatsapp', 'can_manage_branches', 'can_manage_users', 'can_manage_settings',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-orange-500', 'placeholder': 'Ej. Encargado de Noche, Cajero Principal, Supervisor'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-orange-500', 'rows': 2, 'placeholder': 'Descripción de funciones y responsabilidades de este perfil'}),
            
            # Checkboxes
            'can_access_pos': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_apply_discounts': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_change_prices': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_void_sales': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_view_sales_history': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_access_credit': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_authorize_credit': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_record_abono': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_customers': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_access_catalog': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_edit_products': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_adjust_inventory': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_access_purchases': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_open_close_shifts': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_view_cash_history': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_register_expenses': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_view_reports': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_export_reports': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_view_audit_log': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_manage_whatsapp': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_branches': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_users': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_settings': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
        }


class UserProfileForm(forms.ModelForm):
    assigned_branches = forms.ModelMultipleChoiceField(
        queryset=ColmadoBranch.objects.filter(is_active=True).order_by('-is_main', 'name'),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': CHECKBOX_STYLE})
    )

    class Meta:
        model = UserProfile
        fields = [
            'custom_role', 'phone', 'identification',
            'all_branches_access', 'assigned_branches',
            'override_role_permissions',
            # Individual overrides
            'can_access_pos', 'can_apply_discounts', 'can_change_prices', 'can_void_sales', 'can_view_sales_history',
            'can_access_credit', 'can_authorize_credit', 'can_record_abono', 'can_manage_customers',
            'can_access_catalog', 'can_edit_products', 'can_adjust_inventory', 'can_access_purchases',
            'can_open_close_shifts', 'can_view_cash_history', 'can_register_expenses',
            'can_view_reports', 'can_export_reports', 'can_view_audit_log',
            'can_manage_whatsapp', 'can_manage_branches', 'can_manage_users', 'can_manage_settings',
        ]
        widgets = {
            'custom_role': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-orange-500'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-orange-500', 'placeholder': '(809) 000-0000'}),
            'identification': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-orange-500', 'placeholder': '001-0000000-0'}),
            'all_branches_access': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE, 'id': 'id_all_branches_access'}),
            'override_role_permissions': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE, 'id': 'id_override_role_permissions'}),
            
            # Individual permission checkboxes
            'can_access_pos': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_apply_discounts': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_change_prices': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_void_sales': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_view_sales_history': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_access_credit': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_authorize_credit': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_record_abono': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_customers': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_access_catalog': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_edit_products': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_adjust_inventory': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_access_purchases': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_open_close_shifts': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_view_cash_history': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_register_expenses': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_view_reports': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_export_reports': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_view_audit_log': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),

            'can_manage_whatsapp': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_branches': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_users': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
            'can_manage_settings': forms.CheckboxInput(attrs={'class': CHECKBOX_STYLE}),
        }
