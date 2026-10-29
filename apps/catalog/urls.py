from django.urls import path
from apps.catalog import views

urlpatterns = [
    path('productos/', views.ProductListView.as_view(), name='product_list'),
    path('productos/nuevo/', views.ProductCreateView.as_view(), name='product_create'),
    path('productos/<int:pk>/editar/', views.ProductUpdateView.as_view(), name='product_update'),
    path('productos/<int:pk>/desactivar/', views.ProductToggleActiveView.as_view(), name='product_toggle_active'),
    path('categorias/', views.CategoryListView.as_view(), name='category_list'),
    path('categorias/nueva/', views.CategoryCreateView.as_view(), name='category_create'),
]
