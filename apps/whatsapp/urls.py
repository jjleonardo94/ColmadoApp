from django.urls import path
from apps.whatsapp import views

urlpatterns = [
    path('webhook/', views.WhatsAppWebhookView.as_view(), name='whatsapp_webhook'),
    path('bandeja/', views.WhatsAppInboxView.as_view(), name='whatsapp_inbox'),
    path('conversacion/<int:pk>/enviar/', views.SendWhatsAppMessageView.as_view(), name='whatsapp_send_message'),
    path('conversacion/<int:pk>/enviar/action/', views.SendWhatsAppMessageView.as_view(), name='send_whatsapp_message'),
    path('conversacion/<int:pk>/credito/', views.WhatsAppCreditActionView.as_view(), name='whatsapp_credit_action'),
    path('conversacion/<int:pk>/crear-venta/', views.WhatsAppCreateSaleView.as_view(), name='whatsapp_create_sale'),
    path('conversacion/<int:pk>/registrar-cliente/', views.WhatsAppRegisterCustomerView.as_view(), name='whatsapp_register_customer'),
    path('configuracion/', views.WhatsAppConfigView.as_view(), name='whatsapp_config'),
    path('waha/status/', views.WAHAStatusAjaxView.as_view(), name='whatsapp_waha_status'),
    path('api/live/', views.WhatsAppLiveUpdatesView.as_view(), name='whatsapp_live_updates'),
    path('mensaje/<int:pk>/eliminar/', views.WhatsAppDeleteMessageView.as_view(), name='whatsapp_delete_message'),
    path('conversacion/<int:pk>/eliminar/', views.WhatsAppDeleteConversationView.as_view(), name='whatsapp_delete_conversation'),
]
