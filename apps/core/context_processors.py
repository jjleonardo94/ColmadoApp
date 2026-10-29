from apps.core.models import BusinessSettings, ColmadoBranch
from apps.cash.models import CashShift

def business_context(request):
    settings_obj = BusinessSettings.get_settings()
    open_shift = None
    user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None

    if user:
        open_shift = CashShift.objects.filter(cashier=user, status='ABIERTO').select_related('register').first()
        if not open_shift:
            open_shift = CashShift.objects.filter(status='ABIERTO').select_related('register', 'cashier').first()

    # Multi-Colmado: sucursales permitidas según permisos del usuario
    if user and hasattr(user, 'profile'):
        available_branches = list(user.profile.get_allowed_branches())
    else:
        available_branches = list(ColmadoBranch.objects.filter(is_active=True).order_by('-is_main', 'name'))

    if not available_branches:
        default_b = ColmadoBranch.get_default_branch()
        available_branches = [default_b]

    allowed_branch_ids = [b.id for b in available_branches]
    active_branch_id = getattr(request, 'session', {}).get('active_branch_id') if hasattr(request, 'session') else None

    current_branch = None
    # Validar que la sucursal activa en la sesión esté efectivamente permitida para este usuario
    if active_branch_id and active_branch_id in allowed_branch_ids:
        current_branch = next((b for b in available_branches if b.id == active_branch_id), None)

    if not current_branch:
        current_branch = available_branches[0]
        if hasattr(request, 'session'):
            request.session['active_branch_id'] = current_branch.id

    can_switch_branch = len(available_branches) > 1 and (
        user.is_superuser or getattr(user.profile, 'all_branches_access', False) if user and hasattr(user, 'profile') else False
    )

    return {
        'business': settings_obj,
        'current_shift': open_shift,
        'current_branch': current_branch,
        'available_branches': available_branches,
        'can_switch_branch': can_switch_branch,
    }
