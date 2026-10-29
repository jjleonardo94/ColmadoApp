from django.urls import path
from apps.reports import views

urlpatterns = [
    path('', views.ReportsDashboardView.as_view(), name='reports_home'),
    path('resumen/', views.ReportsDashboardView.as_view(), name='reports_dashboard'),
    path('ventas/', views.SalesReportView.as_view(), name='sales_report'),
    path('ganancias/', views.ProfitsReportView.as_view(), name='profits_report'),
    path('exportar/ventas/excel/', views.ExportSalesExcelView.as_view(), name='export_sales_excel'),
    path('exportar/ventas/csv/', views.ExportSalesCSVView.as_view(), name='export_sales_csv'),
]
