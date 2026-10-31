from django.urls import path
from apps.sales import views

urlpatterns = [
    path('', views.POSView.as_view(), name='pos'),
    path('api/productos/buscar/', views.ProductSearchAPIView.as_view(), name='api_product_search'),
    path('api/crear-venta/', views.CreateSaleAPIView.as_view(), name='api_create_sale'),
    path('api/ventas/crear/', views.CreateSaleAPIView.as_view(), name='api_ventas_crear'),
    path('api/ventas/<str:ticket_number>/enviar-whatsapp/', views.SendSaleWhatsAppAPIView.as_view(), name='api_sale_send_whatsapp'),
    path('ventas/', views.SaleListView.as_view(), name='sale_list'),
    path('recibo/<str:ticket_number>/', views.SaleReceiptView.as_view(), name='sale_receipt'),
    path('anular/<int:pk>/', views.VoidSaleView.as_view(), name='sale_void'),

    # Delivery & Repartidores
    path('repartidores/', views.DeliveryPersonListView.as_view(), name='delivery_person_list'),
    path('repartidores/nuevo/', views.DeliveryPersonCreateView.as_view(), name='delivery_person_create'),
    path('repartidores/<int:pk>/editar/', views.DeliveryPersonUpdateView.as_view(), name='delivery_person_update'),
    path('repartidores/<int:pk>/toggle/', views.DeliveryPersonToggleActiveView.as_view(), name='delivery_person_toggle'),

    # Delivery Express APIs
    path('delivery/api/pendientes/', views.DeliveryExpressPendingAPIView.as_view(), name='api_delivery_pending'),
    path('delivery/api/pendientes/express/', views.DeliveryExpressPendingAPIView.as_view(), name='delivery_express_pending'),
    path('delivery/api/despachar/<int:pk>/', views.DeliveryExpressDispatchAPIView.as_view(), name='api_delivery_dispatch'),
    path('delivery/api/despachar/<int:pk>/express/', views.DeliveryExpressDispatchAPIView.as_view(), name='delivery_express_dispatch'),
    path('delivery/api/despachar-todos/', views.DeliveryExpressDispatchAllAPIView.as_view(), name='api_delivery_dispatch_all'),
    path('delivery/api/despachar-todos/express/', views.DeliveryExpressDispatchAllAPIView.as_view(), name='delivery_express_dispatch_all'),
    path('delivery/api/entregar/<int:pk>/', views.DeliveryExpressMarkDeliveredAPIView.as_view(), name='api_delivery_deliver'),
    path('delivery/api/asignar/<int:pk>/', views.DeliveryExpressAssignDeliveryAPIView.as_view(), name='api_delivery_assign'),
]
