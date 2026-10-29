from django.urls import path
from apps.inventory import views

urlpatterns = [
    path('', views.InventoryMovementListView.as_view(), name='inventory_list'),
    path('ajuste/', views.InventoryAdjustmentView.as_view(), name='inventory_adjust'),
    path('alertas/', views.StockAlertsView.as_view(), name='stock_alerts'),
]
