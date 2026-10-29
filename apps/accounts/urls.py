from django.urls import path
from apps.accounts import views

urlpatterns = [
    path('login/', views.ColmadoLoginView.as_view(), name='login'),
    path('logout/', views.ColmadoLogoutView.as_view(), name='logout'),
    
    # Usuarios
    path('usuarios/', views.UserListView.as_view(), name='users_list'),
    path('usuarios/crear/', views.UserCreateView.as_view(), name='user_create'),
    path('usuarios/<int:pk>/editar/', views.UserUpdateView.as_view(), name='user_update'),

    # Perfiles & Roles
    path('usuarios/roles/', views.RoleListView.as_view(), name='role_list'),
    path('usuarios/roles/nuevo/', views.RoleCreateView.as_view(), name='role_create'),
    path('usuarios/roles/<int:pk>/editar/', views.RoleUpdateView.as_view(), name='role_update'),
    path('usuarios/roles/<int:pk>/eliminar/', views.RoleDeleteView.as_view(), name='role_delete'),
]
