from django.db import models
from django.contrib.auth.models import User

class WhatsAppContact(models.Model):
    phone = models.CharField('Teléfono Normalizado (E.164)', max_length=30, unique=True)
    display_name = models.CharField('Nombre / Perfil de WhatsApp', max_length=150, blank=True)
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='whatsapp_contacts', verbose_name='Cliente Vinculado')
    is_verified = models.BooleanField('Identidad Verificada para Información Financiera', default=False)
    created_at = models.DateTimeField('Fecha de Registro', auto_now_add=True)
    updated_at = models.DateTimeField('Última Actualización', auto_now=True)

    class Meta:
        verbose_name = 'Contacto de WhatsApp'
        verbose_name_plural = 'Contactos de WhatsApp'
        ordering = ['-updated_at']

    def __str__(self):
        c_name = f" [{self.customer.name}]" if self.customer else " (No vinculado)"
        return f"{self.display_name or self.phone}{c_name}"


class ConversationStatus(models.TextChoices):
    PENDIENTE = 'PENDIENTE', 'Pendiente de Atención'
    EN_ATENCION = 'EN_ATENCION', 'En Atención'
    RESUELTO = 'RESUELTO', 'Resuelto / Archivado'


class WhatsAppConversation(models.Model):
    contact = models.ForeignKey(WhatsAppContact, on_delete=models.CASCADE, related_name='conversations', verbose_name='Contacto')
    status = models.CharField('Estado', max_length=20, choices=ConversationStatus.choices, default=ConversationStatus.PENDIENTE)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='whatsapp_conversations', verbose_name='Asignado a')
    unread_count = models.PositiveIntegerField('Mensajes no leídos', default=0)
    last_message_text = models.TextField('Último Mensaje', blank=True)
    last_message_at = models.DateTimeField('Fecha del Último Mensaje', auto_now=True)
    created_at = models.DateTimeField('Iniciada', auto_now_add=True)

    class Meta:
        verbose_name = 'Conversación de WhatsApp'
        verbose_name_plural = 'Bandeja de Conversaciones'
        ordering = ['-last_message_at']

    @property
    def last_message_preview(self):
        text = self.last_message_text or ''
        if not text:
            last_msg = self.messages.order_by('-created_at').first()
            if last_msg:
                text = last_msg.content or ''
        if not text:
            return 'Sin mensajes recientes'
        # Reemplazar saltos de línea y espacios múltiples para mantener exactamente 1 sola línea
        clean = " ".join(text.replace('\r', ' ').replace('\n', ' ').split())
        if len(clean) > 55:
            return clean[:55].rstrip() + '...'
        return clean

    def __str__(self):
        return f"Chat con {self.contact.phone} [{self.get_status_display()}]"


class MessageDirection(models.TextChoices):
    INBOUND = 'INBOUND', 'Entrante (Del Cliente)'
    OUTBOUND = 'OUTBOUND', 'Saliente (Del Colmado)'


class MessageStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente de Envío'
    SENT = 'sent', 'Enviado'
    DELIVERED = 'delivered', 'Entregado'
    READ = 'read', 'Leído'
    FAILED = 'failed', 'Error / Fallido'


class WhatsAppMessage(models.Model):
    conversation = models.ForeignKey(WhatsAppConversation, on_delete=models.CASCADE, related_name='messages', verbose_name='Conversación')
    wamid = models.CharField('Meta WhatsApp Message ID', max_length=150, unique=True, null=True, blank=True)
    direction = models.CharField('Dirección', max_length=10, choices=MessageDirection.choices)
    message_type = models.CharField('Tipo de Contenido', max_length=30, default='text')
    content = models.TextField('Texto / Contenido del Mensaje', blank=True, default='')
    media_file = models.FileField('Archivo Multimedia Local', upload_to='whatsapp/%Y/%m/', null=True, blank=True)
    media_url = models.CharField('URL Externa de Multimedia', max_length=500, blank=True, default='')
    media_mime_type = models.CharField('Tipo MIME', max_length=100, blank=True, default='')
    status = models.CharField('Estado de Entrega', max_length=20, choices=MessageStatus.choices, default=MessageStatus.SENT)
    error_message = models.TextField('Detalle de Error', blank=True)
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Enviado por Usuario')
    created_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Mensaje de WhatsApp'
        verbose_name_plural = 'Mensajes de WhatsApp'
        ordering = ['created_at']

    @property
    def text_content(self):
        return self.content

    @property
    def clean_error_message(self):
        if not self.error_message:
            return ""
        err = self.error_message
        if any(term in err for term in ['Connection refused', 'WinError 10061', 'Errno 111', 'HTTPConnectionPool', 'no está activo', 'target machine actively refused']):
            return "No se pudo conectar con el servidor de WhatsApp (WAHA). Verifique que el servicio esté encendido."
        if 'Timeout' in err or 'Tiempo de espera' in err:
            return "Tiempo de espera agotado al enviar mensaje por WhatsApp."
        return err

    @property
    def has_media(self):
        return bool((self.media_file or self.media_url) and self.media_display_url)

    @property
    def is_image(self):
        return self.message_type == 'image' or (self.media_mime_type and self.media_mime_type.startswith('image/')) or any(self.media_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])

    @property
    def is_audio(self):
        return self.message_type == 'audio' or (self.media_mime_type and (self.media_mime_type.startswith('audio/') or 'voice' in self.media_mime_type)) or any(self.media_url.lower().endswith(ext) for ext in ['.ogg', '.mp3', '.m4a', '.wav'])

    @property
    def is_video(self):
        return self.message_type == 'video' or (self.media_mime_type and self.media_mime_type.startswith('video/')) or any(self.media_url.lower().endswith(ext) for ext in ['.mp4', '.mov'])

    @property
    def is_document(self):
        return self.message_type == 'document' or (self.media_mime_type and (self.media_mime_type.startswith('application/') or 'pdf' in self.media_mime_type)) or any(self.media_url.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx'])

    @property
    def media_display_url(self):
        if self.media_file or self.media_url:
            return f"/whatsapp/mensaje/{self.id}/media/"
        return ""

    def __str__(self):
        dir_lbl = "⬅️ Entrante" if self.direction == MessageDirection.INBOUND else "➡️ Saliente"
        return f"{self.created_at.strftime('%H:%M')} | {dir_lbl}: {self.content[:40]}"


class WhatsAppWebhookEvent(models.Model):
    event_id = models.CharField('ID del Evento', max_length=100, blank=True)
    payload = models.JSONField('Payload JSON Recibido')
    processed = models.BooleanField('Procesado con Éxito', default=False)
    error = models.TextField('Error al Procesar', blank=True)
    received_at = models.DateTimeField('Fecha y Hora', auto_now_add=True)

    class Meta:
        verbose_name = 'Evento de Webhook'
        verbose_name_plural = 'Registro de Webhooks'
        ordering = ['-received_at']
