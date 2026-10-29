from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Módulos de ColmadoPOS
    path('', include('apps.core.urls')),
    path('', include('apps.accounts.urls')),
    path('pos/', include('apps.sales.urls')),
    path('catalogo/', include('apps.catalog.urls')),
    path('inventario/', include('apps.inventory.urls')),
    path('clientes/', include('apps.customers.urls')),
    path('caja/', include('apps.cash.urls')),
    path('compras/', include('apps.purchasing.urls')),
    path('gastos/', include('apps.expenses.urls')),
    path('reportes/', include('apps.reports.urls')),
    path('whatsapp/', include('apps.whatsapp.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
