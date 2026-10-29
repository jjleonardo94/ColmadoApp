from django.urls import path
from apps.expenses import views

urlpatterns = [
    path('', views.ExpenseListView.as_view(), name='expense_list'),
    path('nuevo/', views.ExpenseCreateView.as_view(), name='expense_create'),
]
