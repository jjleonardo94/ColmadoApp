from django.urls import path
from apps.purchasing import views

urlpatterns = [
    path('', views.PurchaseListView.as_view(), name='purchase_list'),
    path('nueva/', views.PurchaseCreateView.as_view(), name='purchase_create'),
    path('<int:pk>/recibir/', views.ReceivePurchaseView.as_view(), name='purchase_receive'),
    path('suplidores/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suplidores/nuevo/', views.SupplierCreateView.as_view(), name='supplier_create'),
]
