from django.urls import path
from apps.core import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('configuracion/', views.BusinessSettingsView.as_view(), name='business_settings'),
    path('auditoria/', views.AuditLogListView.as_view(), name='audit_log'),
    path('sucursales/', views.BranchListView.as_view(), name='branch_list'),
    path('sucursales/nueva/', views.BranchCreateView.as_view(), name='branch_create'),
    path('sucursales/<int:pk>/editar/', views.BranchUpdateView.as_view(), name='branch_update'),
    path('sucursales/cambiar/<int:pk>/', views.SwitchBranchView.as_view(), name='branch_switch'),
]
