from django.urls import path
from apps.cash import views

urlpatterns = [
    path('', views.CashShiftListView.as_view(), name='cash_shift_list'),
    path('apertura/', views.OpenShiftView.as_view(), name='cash_open_shift'),
    path('cierre/<int:pk>/', views.CloseShiftView.as_view(), name='cash_close_shift'),
    path('arqueo/<int:pk>/', views.ShiftDetailView.as_view(), name='cash_shift_detail'),
]
