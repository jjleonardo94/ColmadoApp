from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.views.generic import View, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q, Count

from apps.accounts.models import UserProfile, CustomRole, UserRole
from apps.accounts.forms import ColmadoLoginForm, UserProfileForm, CustomRoleForm
from apps.core.models import AuditLog, ColmadoBranch

class ColmadoLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = ColmadoLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f"¡Bienvenido de vuelta, {form.get_user().get_full_name() or form.get_user().username}!")
        AuditLog.objects.create(
            user=form.get_user(),
            action='INICIO_SESION',
            target_model='User',
            target_id=str(form.get_user().id),
            details="Inicio de sesión exitoso.",
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
        return super().form_valid(form)


class ColmadoLogoutView(View):
    def get(self, request):
        if request.user.is_authenticated:
            AuditLog.objects.create(
                user=request.user,
                action='CIERRE_SESION',
                target_model='User',
                target_id=str(request.user.id),
                details="Cierre de sesión de usuario."
            )
            logout(request)
        return redirect('login')


# ==========================================
# GESTIÓN DE USUARIOS
# ==========================================

class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users_list'

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related('profile', 'profile__custom_role').prefetch_related('profile__assigned_branches').all().order_by('username')
        
        # Aislamiento por colmado:
        # Si el usuario NO es superusuario ni tiene acceso global a todos los colmados ni permiso de gestionar usuarios en general,
        # solo puede ver los usuarios que comparten su(s) misma(s) sucursal(es).
        if not (user.is_superuser or getattr(user.profile, 'all_branches_access', False) or user.profile.has_perm('can_manage_users')):
            allowed_branches = user.profile.get_allowed_branches()
            qs = qs.filter(profile__assigned_branches__in=allowed_branches).distinct()
        else:
            # Filtro opcional por sucursal en el panel de admin
            branch_filter = self.request.GET.get('sucursal')
            if branch_filter and branch_filter.isdigit():
                qs = qs.filter(Q(profile__all_branches_access=True) | Q(profile__assigned_branches__id=int(branch_filter))).distinct()

        # Búsqueda por texto
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['all_branches'] = ColmadoBranch.objects.filter(is_active=True).order_by('-is_main', 'name')
        context['selected_branch'] = self.request.GET.get('sucursal', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['can_manage_users'] = user.is_superuser or user.profile.has_perm('can_manage_users')
        context['roles_count'] = CustomRole.objects.count()
        return context


class UserCreateView(LoginRequiredMixin, View):
    def get(self, request):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para crear usuarios.")
            return redirect('users_list')
        profile_form = UserProfileForm()
        return render(request, 'accounts/user_form.html', {'profile_form': profile_form, 'is_create': True})

    def post(self, request):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para crear usuarios.")
            return redirect('users_list')

        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '').strip()

        if not username or not password:
            messages.error(request, "El nombre de usuario y la contraseña son requeridos.")
            return render(request, 'accounts/user_form.html', {'profile_form': UserProfileForm(request.POST), 'is_create': True})

        if User.objects.filter(username=username).exists():
            messages.error(request, f"El nombre de usuario '{username}' ya está registrado.")
            return render(request, 'accounts/user_form.html', {'profile_form': UserProfileForm(request.POST), 'is_create': True})

        new_user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
        )

        profile_form = UserProfileForm(request.POST, instance=new_user.profile)
        if profile_form.is_valid():
            profile = profile_form.save()
            # Si tiene custom_role y no sobrescribe, sincronizar flags del rol
            if profile.custom_role and not profile.override_role_permissions:
                for field in profile.custom_role._meta.fields:
                    if field.name.startswith('can_'):
                        setattr(profile, field.name, getattr(profile.custom_role, field.name))
                profile.save()

            messages.success(request, f"Usuario '{username}' creado exitosamente.")
            return redirect('users_list')

        return render(request, 'accounts/user_form.html', {'profile_form': profile_form, 'is_create': True})


class UserUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para editar usuarios.")
            return redirect('users_list')
        target_user = get_object_or_404(User, pk=pk)
        profile_form = UserProfileForm(instance=target_user.profile)
        return render(request, 'accounts/user_form.html', {'target_user': target_user, 'profile_form': profile_form, 'is_create': False})

    def post(self, request, pk):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para editar usuarios.")
            return redirect('users_list')
        target_user = get_object_or_404(User, pk=pk)
        target_user.first_name = request.POST.get('first_name', target_user.first_name)
        target_user.last_name = request.POST.get('last_name', target_user.last_name)
        new_pass = request.POST.get('password', '').strip()
        if new_pass:
            target_user.set_password(new_pass)
        target_user.save()

        profile_form = UserProfileForm(request.POST, instance=target_user.profile)
        if profile_form.is_valid():
            profile = profile_form.save()
            # Si no sobreescribe permisos, sincronizar con su custom_role
            if profile.custom_role and not profile.override_role_permissions:
                for field in profile.custom_role._meta.fields:
                    if field.name.startswith('can_'):
                        setattr(profile, field.name, getattr(profile.custom_role, field.name))
                profile.save()

            messages.success(request, f"Usuario '{target_user.username}' actualizado correctamente.")
            return redirect('users_list')

        return render(request, 'accounts/user_form.html', {'target_user': target_user, 'profile_form': profile_form, 'is_create': False})


# ==========================================
# GESTIÓN DE PERFILES Y ROLES PERSONALIZADOS
# ==========================================

class RoleListView(LoginRequiredMixin, ListView):
    model = CustomRole
    template_name = 'accounts/role_list.html'
    context_object_name = 'roles'

    def get_queryset(self):
        return CustomRole.objects.annotate(users_count=Count('profiles')).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['can_manage_roles'] = user.is_superuser or user.profile.has_perm('can_manage_users')
        context['users_count'] = User.objects.count()
        return context


class RoleCreateView(LoginRequiredMixin, CreateView):
    model = CustomRole
    form_class = CustomRoleForm
    template_name = 'accounts/role_form.html'
    success_url = reverse_lazy('role_list')

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para administrar perfiles y roles.")
            return redirect('role_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Perfil '{self.object.name}' creado exitosamente con sus permisos configurados.")
        return response


class RoleUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomRole
    form_class = CustomRoleForm
    template_name = 'accounts/role_form.html'
    success_url = reverse_lazy('role_list')

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para administrar perfiles y roles.")
            return redirect('role_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        role = self.object
        # Sincronizar perfiles asociados que no tengan sobrescritura individual
        for prof in role.profiles.filter(override_role_permissions=False):
            for field in role._meta.fields:
                if field.name.startswith('can_'):
                    setattr(prof, field.name, getattr(role, field.name))
            prof.save()

        messages.success(self.request, f"Perfil '{role.name}' y los usuarios asignados han sido actualizados.")
        return response


class RoleDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not (request.user.is_superuser or request.user.profile.has_perm('can_manage_users')):
            messages.error(request, "No tiene permisos para eliminar perfiles.")
            return redirect('role_list')
        role = get_object_or_404(CustomRole, pk=pk)
        if role.is_system_default:
            messages.error(request, f"El perfil '{role.name}' es del sistema y no puede eliminarse.")
            return redirect('role_list')
        
        assigned_count = role.profiles.count()
        if assigned_count > 0:
            messages.error(request, f"No se puede eliminar '{role.name}' porque tiene {assigned_count} usuario(s) asignado(s). Reasigne esos usuarios primero.")
            return redirect('role_list')

        name = role.name
        role.delete()
        messages.success(request, f"Perfil '{name}' eliminado exitosamente.")
        return redirect('role_list')
