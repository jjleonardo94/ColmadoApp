from django.urls import path
from apps.customers import views

urlpatterns = [
    path('', views.CustomerListView.as_view(), name='customer_list'),
    path('nuevo/', views.CustomerCreateView.as_view(), name='customer_create'),
    path('<int:pk>/', views.CustomerDetailView.as_view(), name='customer_detail'),
    path('<int:pk>/editar/', views.CustomerUpdateView.as_view(), name='customer_update'),
    path('<int:pk>/abono/', views.RecordAbonoView.as_view(), name='customer_abono'),
    path('<int:pk>/abonar/', views.RecordAbonoView.as_view(), name='customer_abonar'),
    path('<int:pk>/estado-cuenta/whatsapp/', views.CustomerWhatsAppSummaryView.as_view(), name='customer_whatsapp_summary'),
]
