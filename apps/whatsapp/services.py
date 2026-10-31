import hmac
import hashlib
import json
import logging
import random
import re
import sys
import time
import requests
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.customers.models import Customer
from apps.customers.services import CustomerCreditService
from apps.whatsapp.models import (
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppWebhookEvent,
    ConversationStatus,
    MessageDirection,
    MessageStatus,
)

logger = logging.getLogger(__name__)


class WAHAService:
    """
    Servicio de integración directa con WAHA (WhatsApp HTTP API - devlikeapro/waha).
    Implementa:
    1. Rutina Anti-Baneo oficial recomendada:
       sendSeen -> startTyping -> retardo humanizado dinámico con jitter -> stopTyping -> sendText.
    2. Monitoreo de estado de sesiones e interfaz con el contenedor Docker.
    3. Normalización y despacho de mensajes hacia números estándar (@c.us).
    """

    @classmethod
    def get_api_url(cls) -> str:
        url = getattr(settings, 'WAHA_API_URL', 'http://localhost:3000') or 'http://localhost:3000'
        return url.rstrip('/')

    @classmethod
    def get_session(cls) -> str:
        return getattr(settings, 'WAHA_SESSION', 'default') or 'default'

    @classmethod
    def get_headers(cls) -> dict:
        headers = {'Content-Type': 'application/json'}
        api_key = getattr(settings, 'WAHA_API_KEY', '') or 'colmadopos_secret_waha_api_key_2026'
        if api_key:
            headers['X-Api-Key'] = api_key
        return headers

    @classmethod
    def get_contact_info(cls, jid: str, session: str = None) -> dict:
        """
        Obtiene los datos del contacto desde WAHA (nombre en agenda, pushname, etc.)
        """
        if not jid:
            return {}
        s_name = session or cls.get_session()
        url = f"{cls.get_api_url()}/api/contacts?contactId={jid}&session={s_name}"
        try:
            resp = requests.get(url, headers=cls.get_headers(), timeout=4)
            if resp.status_code == 200:
                return resp.json() or {}
        except Exception as ex:
            logger.debug("Error obteniendo contacto %s en WAHA: %s", jid, ex)
        return {}

    @classmethod
    def resolve_lid_to_phone(cls, jid: str, session: str = None) -> str:
        """
        Si el JID es un LID (@lid) de WhatsApp WebJS/Multi-device, consulta a la API de WAHA
        para obtener el JID telefónico real (@c.us) del contacto.
        """
        if not jid or '@lid' not in jid:
            return jid
        info = cls.get_contact_info(jid, session=session)
        contact_id = info.get('id', '')
        if '@c.us' in contact_id:
            return contact_id
        return jid

    @classmethod
    def check_health(cls) -> dict:
        """
        Verifica el estado del contenedor WAHA y de la sesión activa de WhatsApp.
        Retorna información útil para la pantalla de configuración.
        """
        url = f"{cls.get_api_url()}/api/sessions"
        active_session_name = cls.get_session()
        try:
            resp = requests.get(url, headers=cls.get_headers(), timeout=3)
            if resp.status_code == 200:
                sessions = resp.json()
                curr_session = next((s for s in sessions if s.get('name') == active_session_name), None)
                status_str = curr_session.get('status') if curr_session else 'STOPPED'
                return {
                    'online': True,
                    'status': status_str,
                    'session_name': active_session_name,
                    'session_data': curr_session or {'name': active_session_name, 'status': 'NOT_FOUND'},
                    'all_sessions': sessions,
                    'error': None
                }
            return {
                'online': False,
                'status': 'OFFLINE',
                'session_name': active_session_name,
                'error': f"HTTP {resp.status_code}: {resp.text}"
            }
        except Exception as ex:
            return {
                'online': False,
                'status': 'OFFLINE',
                'session_name': active_session_name,
                'error': str(ex)
            }

    @classmethod
    def send_seen(cls, chat_id: str, session: str = None) -> bool:
        """
        Marca la conversación como vista (doble check azul) para simular atención humana.
        """
        s_name = session or cls.get_session()
        url = f"{cls.get_api_url()}/api/sendSeen"
        payload = {"session": s_name, "chatId": chat_id}
        try:
            resp = requests.post(url, json=payload, headers=cls.get_headers(), timeout=4)
            return resp.status_code in [200, 201]
        except Exception as ex:
            logger.debug("Error enviando sendSeen a WAHA: %s", ex)
            return False

    @classmethod
    def start_typing(cls, chat_id: str, session: str = None) -> bool:
        """
        Activa el indicador 'Escribiendo...' en la conversación de WhatsApp.
        """
        s_name = session or cls.get_session()
        url = f"{cls.get_api_url()}/api/startTyping"
        payload = {"session": s_name, "chatId": chat_id}
        try:
            resp = requests.post(url, json=payload, headers=cls.get_headers(), timeout=4)
            return resp.status_code in [200, 201]
        except Exception as ex:
            logger.debug("Error enviando startTyping a WAHA: %s", ex)
            return False

    @classmethod
    def stop_typing(cls, chat_id: str, session: str = None) -> bool:
        """
        Detiene el indicador 'Escribiendo...'.
        """
        s_name = session or cls.get_session()
        url = f"{cls.get_api_url()}/api/stopTyping"
        payload = {"session": s_name, "chatId": chat_id}
        try:
            resp = requests.post(url, json=payload, headers=cls.get_headers(), timeout=4)
            return resp.status_code in [200, 201]
        except Exception as ex:
            logger.debug("Error enviando stopTyping a WAHA: %s", ex)
            return False

    @classmethod
    def calculate_human_delay(cls, text: str) -> float:
        """
        Calcula un tiempo de espera breve para cuando se requiera simular tipeo:
        0.3s a 0.8s máximo con jitter mínimo para no congelar la aplicación.
        """
        base_delay = min(max(len(text) * 0.005, 0.25), 0.75)
        jitter = random.uniform(0.05, 0.15)
        return round(base_delay + jitter, 2)

    @classmethod
    def send_text_message(cls, phone_number: str, text: str, session: str = None, simulate_typing: bool = False) -> dict:
        """
        Despacha un mensaje a través de WAHA. Por defecto envía de forma inmediata (sub-segundo).
        Si simulate_typing es True, ejecuta la secuencia con un breve indicador de tipeo.
        """
        clean_phone = WhatsAppService.normalize_phone(phone_number)
        chat_id = f"{clean_phone}@c.us"
        s_name = session or cls.get_session()

        should_simulate = simulate_typing and getattr(settings, 'WAHA_SIMULATE_TYPING', False)
        is_testing = getattr(settings, 'TESTING', False) or 'test' in sys.argv

        if should_simulate:
            cls.send_seen(chat_id, session=s_name)
            cls.start_typing(chat_id, session=s_name)
            if not is_testing:
                delay = cls.calculate_human_delay(text)
                time.sleep(delay)
            cls.stop_typing(chat_id, session=s_name)

        url = f"{cls.get_api_url()}/api/sendText"
        payload = {
            "session": s_name,
            "chatId": chat_id,
            "text": text
        }

        try:
            resp = requests.post(url, json=payload, headers=cls.get_headers(), timeout=5)
            data = resp.json() if resp.content else {}
            if resp.status_code in [200, 201]:
                raw_id = data.get('id', '')
                if isinstance(raw_id, dict):
                    msg_id = raw_id.get('_serialized') or raw_id.get('id') or str(raw_id)
                else:
                    msg_id = str(raw_id)
                msg_id = str(msg_id)[:140]
                return {
                    'success': True,
                    'message_id': msg_id,
                    'data': data
                }
            else:
                err_text = data.get('message') or data.get('error') or resp.text
                return {
                    'success': False,
                    'error': f"WAHA Error ({resp.status_code}): {err_text}"
                }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f"El servidor WAHA no está activo en {cls.get_api_url()}. Inicie el contenedor Docker (docker compose -f docker-compose.waha.yml up -d) para entregar los mensajes."
            }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': f"Tiempo de espera agotado al conectar con WAHA ({cls.get_api_url()})."
            }
        except Exception as ex:
            return {
                'success': False,
                'error': f"Error al conectar con servidor WAHA ({cls.get_api_url()}): {str(ex)}"
            }


    @classmethod
    def send_image_message(cls, phone_number: str, image_url: str, caption: str = '', filename: str = 'ticket.png', session: str = None) -> dict:
        """
        Despacha una imagen a través de WAHA (/api/sendImage).
        Soporta URLs públicas o rutas locales mapeadas para Docker.
        """
        clean_phone = WhatsAppService.normalize_phone(phone_number)
        chat_id = f"{clean_phone}@c.us"
        s_name = session or cls.get_session()

        target_url = image_url
        if 'localhost:8000' in target_url or '127.0.0.1:8000' in target_url:
            target_url = target_url.replace('localhost:8000', 'host.docker.internal:8000').replace('127.0.0.1:8000', 'host.docker.internal:8000')

        url = f"{cls.get_api_url()}/api/sendImage"
        payload = {
            "session": s_name,
            "chatId": chat_id,
            "file": {
                "url": target_url,
                "filename": filename,
                "mimetype": "image/png"
            }
        }
        if caption and str(caption).strip():
            payload["caption"] = str(caption).strip()

        try:
            resp = requests.post(url, json=payload, headers=cls.get_headers(), timeout=15)
            data = resp.json() if resp.content else {}
            if resp.status_code in [200, 201]:
                raw_id = data.get('id', '')
                if isinstance(raw_id, dict):
                    msg_id = raw_id.get('_serialized') or raw_id.get('id') or str(raw_id)
                else:
                    msg_id = str(raw_id)
                return {
                    'success': True,
                    'message_id': str(msg_id)[:140],
                    'data': data
                }
            else:
                err_text = data.get('message') or data.get('error') or resp.text
                return {
                    'success': False,
                    'error': f"WAHA Error ({resp.status_code}): {err_text}"
                }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f"El servidor WAHA no está activo en {cls.get_api_url()}."
            }
        except Exception as ex:
            return {
                'success': False,
                'error': f"Error al enviar imagen por WAHA: {str(ex)}"
            }


class WhatsAppService:
    @staticmethod
    def normalize_phone(phone_str: str) -> str:
        """
        Normaliza un número telefónico a formato internacional sin espacios ni caracteres especiales.
        Ejemplo dominicano: '(809) 555-0199' -> '18095550199' o '8095550199'.
        """
        digits = re.sub(r'\D', '', str(phone_str))
        if len(digits) == 10 and digits.startswith(('809', '829', '849')):
            digits = '1' + digits
        return digits

    @staticmethod
    def verify_webhook_signature(payload_bytes: bytes, signature_header: str) -> bool:
        """
        Verifica la firma SHA-256 enviada por Meta en el encabezado X-Hub-Signature-256.
        """
        app_secret = getattr(settings, 'WHATSAPP_APP_SECRET', '')
        if not app_secret:
            # Si no hay secreto configurado, se permite para pruebas locales
            return True
        if not signature_header or not signature_header.startswith('sha256='):
            return False

        expected_sig = signature_header[7:]
        calculated_sig = hmac.new(
            app_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, calculated_sig)

    @staticmethod
    def sanitize_message_content(content: str) -> str:
        """
        Sanitiza el contenido de los mensajes para evitar que credenciales críticas
        (como contraseñas de administradores o accesos) queden expuestas en la bandeja pública.
        """
        if not content:
            return content
        content = re.sub(
            r'(?i)\b(contrase[ñn]a|clave|password|pass)\s*[:=]\s*[^\s\n]+',
            r'\1: [PROTEGIDO POR SEGURIDAD]',
            content
        )
        content = re.sub(
            r'\badmin123\b',
            '[PROTEGIDO]',
            content
        )
        return content

    @classmethod
    @transaction.atomic
    def process_incoming_webhook(cls, payload: dict) -> list:
        """
        Procesa el payload oficial enviado por el webhook de Meta Cloud API.
        Maneja deduplicación por wamid, asociación de clientes y reconocimiento de intenciones.
        """
        webhook_log = WhatsAppWebhookEvent.objects.create(payload=payload)
        processed_messages = []

        try:
            entry = payload.get('entry', [])
            for e in entry:
                changes = e.get('changes', [])
                for change in changes:
                    value = change.get('value', {})
                    contacts_meta = {c.get('wa_id'): c.get('profile', {}).get('name', '') for c in value.get('contacts', [])}
                    messages_list = value.get('messages', [])

                    for msg_item in messages_list:
                        wamid = msg_item.get('id')
                        from_number = msg_item.get('from', '')
                        msg_type = msg_item.get('type', 'text')
                        content = ""

                        if msg_type == 'text':
                            content = msg_item.get('text', {}).get('body', '')
                        elif msg_type == 'image':
                            content = msg_item.get('image', {}).get('caption', '[Imagen recibida]')
                        else:
                            content = f"[{msg_type.capitalize()} recibido]"

                        # 1. Deduplicación por WAMID
                        if wamid and WhatsAppMessage.objects.filter(wamid=wamid).exists():
                            continue

                        # 2. Normalizar número y buscar/crear contacto
                        normalized_phone = cls.normalize_phone(from_number)
                        profile_name = contacts_meta.get(from_number, '')

                        contact = WhatsAppContact.objects.filter(phone=normalized_phone).first()
                        if not contact:
                            matched_customer = Customer.objects.filter(
                                phone__icontains=normalized_phone[-8:]
                            ).first()
                            
                            contact = WhatsAppContact.objects.create(
                                phone=normalized_phone,
                                display_name=profile_name or f"Contacto {normalized_phone}",
                                customer=matched_customer,
                                is_verified=matched_customer is not None,
                            )
                        elif profile_name and not contact.display_name:
                            contact.display_name = profile_name
                            contact.save(update_fields=['display_name'])

                        # 3. Conversación
                        conversation, _ = WhatsAppConversation.objects.get_or_create(
                            contact=contact,
                            defaults={'status': ConversationStatus.PENDIENTE}
                        )
                        conversation.unread_count += 1
                        conversation.last_message_text = content
                        conversation.last_message_at = timezone.now()
                        conversation.save()

                        # 4. Guardar Mensaje
                        msg_obj = WhatsAppMessage.objects.create(
                            conversation=conversation,
                            wamid=wamid,
                            direction=MessageDirection.INBOUND,
                            message_type=msg_type,
                            content=content,
                            status=MessageStatus.DELIVERED,
                        )
                        processed_messages.append(msg_obj)

                        # 5. Detección de Intenciones de Fiados
                        cls.handle_customer_intent(contact, conversation, content)

            webhook_log.processed = True
            webhook_log.save(update_fields=['processed'])
        except Exception as ex:
            webhook_log.error = str(ex)
            webhook_log.save(update_fields=['error'])
            raise ex

        return processed_messages

    @classmethod
    @transaction.atomic
    def process_waha_webhook(cls, payload: dict) -> list:
        """
        Procesa eventos emitidos por WAHA (webhook 'message' o 'message.any').
        Registra cada mensaje en WhatsAppMessage y actualiza o crea el contacto y conversación.
        Permite sincronizar tanto mensajes entrantes de clientes como mensajes salientes
        enviados desde el celular del colmadero.
        """
        webhook_log = WhatsAppWebhookEvent.objects.create(payload=payload)
        processed_messages = []

        try:
            msg_data = payload.get('payload', payload)
            if not isinstance(msg_data, dict):
                msg_data = {}

            wamid = msg_data.get('id')
            raw_from = msg_data.get('from', '')
            raw_to = msg_data.get('to', '')
            from_me = bool(msg_data.get('fromMe', False))

            # 0. Filtrar mensajes de grupos, comunidades, boletines y difusiones
            is_group = (
                '@g.us' in raw_from or 
                '@g.us' in raw_to or 
                '@newsletter' in raw_from or 
                '@broadcast' in raw_from or 
                bool(msg_data.get('participant')) or
                bool(msg_data.get('_data', {}).get('participant'))
            )
            if is_group:
                webhook_log.processed = True
                webhook_log.save(update_fields=['processed'])
                return []

            direction = MessageDirection.OUTBOUND if from_me else MessageDirection.INBOUND

            # Determinar el número del contacto
            session_name = payload.get('session')
            target_jid = raw_to if from_me else raw_from
            if '@lid' in target_jid:
                target_jid = WAHAService.resolve_lid_to_phone(target_jid, session=session_name)
            phone_raw = target_jid.split('@')[0] if '@' in target_jid else target_jid
            normalized_phone = cls.normalize_phone(phone_raw)

            if not normalized_phone:
                webhook_log.processed = True
                webhook_log.save(update_fields=['processed'])
                return []

            # 1. Deduplicación por ID de mensaje
            if wamid and WhatsAppMessage.objects.filter(wamid=wamid).exists():
                webhook_log.processed = True
                webhook_log.save(update_fields=['processed'])
                return []

            # 2. Contenido del mensaje y Multimedia
            content = msg_data.get('body', '')
            msg_type = 'text'
            media_url = ''
            media_mime = ''

            if msg_data.get('hasMedia') or msg_data.get('media'):
                media_info = msg_data.get('media') or {}
                if isinstance(media_info, dict):
                    media_url = media_info.get('url', '') or ''
                    media_mime = media_info.get('mimetype', '') or ''
                if not media_mime:
                    media_mime = msg_data.get('_data', {}).get('mimetype', '') or ''

                if media_mime.startswith('image/'):
                    msg_type = 'image'
                elif media_mime.startswith('audio/') or 'voice' in media_mime:
                    msg_type = 'audio'
                elif media_mime.startswith('video/'):
                    msg_type = 'video'
                elif 'pdf' in media_mime or media_mime.startswith('application/'):
                    msg_type = 'document'
                else:
                    msg_type = 'media'

                caption = msg_data.get('caption', '')
                content = caption if caption else ""
            elif not content:
                content = "[Mensaje sin texto]"
            else:
                content = cls.sanitize_message_content(content)

            # 3. Buscar o crear Contacto con Jerarquía Profesional de Nombres
            matched_customer = Customer.objects.filter(
                phone__icontains=normalized_phone[-8:]
            ).first()

            # Consultar agenda telefónica en WAHA
            contact_info = WAHAService.get_contact_info(f"{normalized_phone}@c.us", session=session_name)
            if not contact_info and '@lid' in (raw_from or raw_to):
                contact_info = WAHAService.get_contact_info(target_jid, session=session_name)
            phonebook_name = contact_info.get('name') or contact_info.get('shortName')

            if matched_customer:
                profile_name = matched_customer.name
            elif phonebook_name:
                profile_name = phonebook_name
            elif not from_me:
                profile_name = (
                    msg_data.get('_data', {}).get('notifyName') or 
                    msg_data.get('notifyName') or 
                    contact_info.get('pushname') or
                    f"Contacto {normalized_phone}"
                )
            else:
                profile_name = f"Contacto {normalized_phone}"

            contact = WhatsAppContact.objects.filter(phone=normalized_phone).first()
            if not contact:
                contact = WhatsAppContact.objects.create(
                    phone=normalized_phone,
                    display_name=profile_name,
                    customer=matched_customer,
                    is_verified=matched_customer is not None,
                )
            else:
                updated_fields = []
                if not contact.customer and matched_customer:
                    contact.customer = matched_customer
                    contact.is_verified = True
                    contact.display_name = matched_customer.name
                    updated_fields.extend(['customer', 'is_verified', 'display_name'])
                elif phonebook_name and contact.display_name != phonebook_name and not contact.customer:
                    contact.display_name = phonebook_name
                    updated_fields.append('display_name')
                elif profile_name and (not contact.display_name or contact.display_name.startswith('Contacto ')):
                    contact.display_name = profile_name
                    updated_fields.append('display_name')
                if updated_fields:
                    contact.save(update_fields=updated_fields)

            # 4. Actualizar o crear Conversación
            conversation, _ = WhatsAppConversation.objects.get_or_create(
                contact=contact,
                defaults={'status': ConversationStatus.PENDIENTE}
            )
            if direction == MessageDirection.INBOUND:
                conversation.unread_count += 1
            conversation.last_message_text = content
            conversation.last_message_at = timezone.now()
            conversation.save()

            # 5. Guardar Registro del Mensaje
            msg_obj = WhatsAppMessage.objects.create(
                conversation=conversation,
                wamid=wamid,
                direction=direction,
                message_type=msg_type,
                content=content,
                media_url=media_url,
                media_mime_type=media_mime,
                status=MessageStatus.DELIVERED if direction == MessageDirection.INBOUND else MessageStatus.SENT,
            )
            processed_messages.append(msg_obj)

            # 5.1 Descargar y persistir archivo multimedia de inmediato si está disponible en WAHA
            if media_url:
                cls.download_and_persist_media(msg_obj, media_url, media_mime)

            # 6. Detección de intenciones si es entrante (Saldo, Abonos, etc.)
            if direction == MessageDirection.INBOUND:
                cls.handle_customer_intent(contact, conversation, content)

            webhook_log.processed = True
            webhook_log.save(update_fields=['processed'])
        except Exception as ex:
            webhook_log.error = str(ex)
            webhook_log.save(update_fields=['error'])
            raise ex

        return processed_messages

    @classmethod
    def handle_customer_intent(cls, contact: WhatsAppContact, conversation: WhatsAppConversation, text: str):
        """
        Reconoce automáticamente intenciones clave del cliente para el colmado:
        - Consultar saldo / deuda
        - Notificar pago realizado
        - Solicitar hablar con el encargado
        """
        text_lower = text.lower().strip()

        # Intención: Consulta de Saldo / Deuda / Libreta
        balance_triggers = ['cuanto debo', 'cuánto debo', 'mi saldo', 'saldo', 'mi deuda', 'deuda', 'estado de cuenta', 'mi balance', 'balance']
        if any(trigger in text_lower for trigger in balance_triggers):
            if contact.customer and contact.is_verified:
                summary = CustomerCreditService.generate_whatsapp_summary(contact.customer)
                cls.send_text_message(
                    phone_number=contact.phone,
                    text=summary,
                    conversation=conversation,
                )
            else:
                cls.send_text_message(
                    phone_number=contact.phone,
                    text=(
                        "Hola, para consultar su libreta de fiados su número debe estar registrado y verificado en nuestro sistema. "
                        "Por favor indique su nombre completo para que nuestro encargado lo atienda en breve."
                    ),
                    conversation=conversation,
                )
            return

        # Intención: Notificación de Pago realizado
        payment_triggers = ['ya transferi', 'ya transferí', 'hice el pago', 'pagué', 'pague', 'le mande el dinero', 'le mandé el dinero', 'hice el abono']
        if any(trigger in text_lower for trigger in payment_triggers):
            conversation.status = ConversationStatus.PENDIENTE
            conversation.save(update_fields=['status'])
            cls.send_text_message(
                phone_number=contact.phone,
                text=(
                    "¡Muchas gracias por su aviso! Hemos notificado al encargado, vamos a verificar su comprobante. "
                    "Tan pronto sea confirmado, su libreta se actualizará automáticamente."
                ),
                conversation=conversation,
            )
            return

        # Intención: Solicitar encargado
        agent_triggers = ['encargado', 'humano', 'colmaduero', 'dueno', 'dueño', 'hablar con alguien']
        if any(trigger in text_lower for trigger in agent_triggers):
            conversation.status = ConversationStatus.PENDIENTE
            conversation.save(update_fields=['status'])
            cls.send_text_message(
                phone_number=contact.phone,
                text="Entendido, le estamos avisando al encargado para que le atienda de inmediato. ¡Un momento por favor!",
                conversation=conversation,
            )

    @classmethod
    def download_and_persist_media(cls, msg_obj: WhatsAppMessage, media_url: str, media_mime: str = ''):
        """
        Descarga el archivo multimedia de WAHA en el mismo instante en que se recibe
        y lo guarda en disco permanente (MEDIA_ROOT/whatsapp/) para que no expire.
        """
        if not media_url:
            return
        try:
            headers = WAHAService.get_headers() if ('localhost:3000' in media_url or 'api/files' in media_url) else {}
            resp = requests.get(media_url, headers=headers, timeout=8)
            if resp.status_code == 200 and resp.content:
                from django.core.files.base import ContentFile
                content_type = resp.headers.get('content-type') or media_mime or ''
                ext = '.jpg'
                if 'image' in content_type: ext = '.jpg'
                elif 'audio' in content_type or 'ogg' in content_type: ext = '.ogg'
                elif 'video' in content_type: ext = '.mp4'
                elif 'pdf' in content_type: ext = '.pdf'
                filename = f"wa_{msg_obj.id}_{int(time.time())}{ext}"
                msg_obj.media_file.save(filename, ContentFile(resp.content), save=True)
                logger.info("Multimedia guardado exitosamente para mensaje %s en %s", msg_obj.id, msg_obj.media_file.name)
        except Exception as e:
            logger.warning("No se pudo descargar media de %s: %s", media_url, e)

    @classmethod
    def parse_operator_credit_command(cls, text: str) -> dict | None:
        """
        Analiza si el mensaje ingresado por el encargado en el chat de WhatsApp es un comando
        rápido de Libreta de Fiados (Abonar a cuenta o Cargar a la deuda):
        - Abono: 'Abonar 500', 'Abono 300', '/abono 200', 'Pagar 150', 'Abonar 1000 transferencia', etc.
        - Fiado/Cargo: 'Fiar 150 arroz y sopa', 'Anotar 200', 'Debe 300', 'Cargo 450', 'Añadir en la cuenta que debe 300', etc.
        Retorna un diccionario estructurado o None si es un mensaje de texto ordinario.
        """
        if not text:
            return None

        cleaned = text.strip()
        normalized = cleaned.lstrip('/').strip()

        # Patrón 1: Abonos a cuenta
        abono_pattern = re.compile(
            r'^(?:(?:anadir|añadir|poner|registrar)\s+)?(?:abono|abonar|pago|pagar)\s+(?:rd\$|\$)?\s*([0-9]+(?:[\.,][0-9]{1,2})?)(?:\s+(.*))?$',
            re.IGNORECASE
        )
        abono_match = abono_pattern.match(normalized)
        if abono_match:
            raw_amount = abono_match.group(1).replace(',', '.')
            try:
                amount = Decimal(raw_amount)
                if amount <= Decimal('0.00'):
                    return None
            except Exception:
                return None

            rest = (abono_match.group(2) or '').strip()
            rest_lower = rest.lower()

            if any(w in rest_lower for w in ['transf', 'transferencia', 'banco', 'deposito', 'depósito']):
                payment_method = 'TRANSFERENCIA'
            elif any(w in rest_lower for w in ['tarjeta', 'card', 'pos']):
                payment_method = 'TARJETA'
            else:
                payment_method = 'EFECTIVO'

            return {
                'type': 'ABONO',
                'amount': amount,
                'payment_method': payment_method,
                'notes': rest or f"Abono registrado vía chat ({payment_method})",
            }

        # Patrón 2: Cargos / Fiados a la cuenta
        cargo_pattern = re.compile(
            r'^(?:(?:anadir|añadir|agregar)\s+(?:en\s+la\s+cuenta\s+que\s+debe|a\s+(?:la\s+)?cuenta\s+que\s+debe|a\s+(?:la\s+)?deuda|deuda|a\s+cuenta)|fiar|debe|anotar(?:\s+en\s+la\s+libreta)?|cargo|cargar)\s+(?:rd\$|\$)?\s*([0-9]+(?:[\.,][0-9]{1,2})?)(?:\s+(.*))?$',
            re.IGNORECASE
        )
        cargo_match = cargo_pattern.match(normalized)
        if cargo_match:
            raw_amount = cargo_match.group(1).replace(',', '.')
            try:
                amount = Decimal(raw_amount)
                if amount <= Decimal('0.00'):
                    return None
            except Exception:
                return None

            notes = (cargo_match.group(2) or '').strip()
            return {
                'type': 'CARGO',
                'amount': amount,
                'notes': notes or "Fiado registrado vía chat",
            }

        return None

    @classmethod
    def send_text_message(cls, phone_number: str, text: str, conversation: WhatsAppConversation = None, user = None, simulate_typing: bool = False) -> WhatsAppMessage:
        """
        Envía un mensaje de texto.
        1. Intenta enviar a través de WAHA (inmediato por defecto o con tipeo si se especifica).
        2. Si WAHA no está activo, intenta Meta Cloud API si hay credenciales.
        3. Si no hay servicio activo, registra el mensaje localmente informando el motivo con transparencia.
        """
        clean_phone = cls.normalize_phone(phone_number)
        
        # Buscar o crear conversación si no fue provista
        if not conversation:
            contact, _ = WhatsAppContact.objects.get_or_create(
                phone=clean_phone,
                defaults={'display_name': f"Contacto {clean_phone}"}
            )
            conversation, _ = WhatsAppConversation.objects.get_or_create(
                contact=contact,
                defaults={'status': ConversationStatus.EN_ATENCION}
            )

        clean_saved_text = cls.sanitize_message_content(text)
        msg_record = WhatsAppMessage(
            conversation=conversation,
            direction=MessageDirection.OUTBOUND,
            message_type='text',
            content=clean_saved_text,
            sent_by=user,
        )

        waha_url = getattr(settings, 'WAHA_API_URL', '')
        meta_token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
        meta_phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')

        # 1. Intentar envío con WAHA
        if waha_url:
            waha_res = WAHAService.send_text_message(
                phone_number=clean_phone,
                text=text,
                simulate_typing=simulate_typing
            )
            if waha_res.get('success'):
                raw_wamid = waha_res.get('message_id') or f"waha_{int(time.time()*1000)}"
                if isinstance(raw_wamid, dict):
                    raw_wamid = raw_wamid.get('_serialized') or raw_wamid.get('id') or str(raw_wamid)
                msg_record.wamid = str(raw_wamid)[:140]
                msg_record.status = MessageStatus.SENT
                msg_record.save()
                conversation.last_message_text = clean_saved_text
                conversation.last_message_at = timezone.now()
                conversation.save(update_fields=['last_message_text', 'last_message_at'])
                return msg_record
            else:
                # Si falló WAHA y no hay Meta configurado, registramos el mensaje de error de WAHA
                if not (meta_token and meta_phone_id):
                    msg_record.status = MessageStatus.FAILED
                    msg_record.error_message = waha_res.get('error', 'Error desconocido al conectar con WAHA')
                    msg_record.save()
                    conversation.last_message_text = clean_saved_text
                    conversation.last_message_at = timezone.now()
                    conversation.save(update_fields=['last_message_text', 'last_message_at'])
                    return msg_record

        # 2. Alternativa: Meta Cloud API si hay credenciales oficiales
        if meta_token and meta_phone_id:
            api_ver = getattr(settings, 'WHATSAPP_API_VERSION', 'v20.0')
            url = f"https://graph.facebook.com/{api_ver}/{meta_phone_id}/messages"
            headers = {
                'Authorization': f'Bearer {meta_token}',
                'Content-Type': 'application/json',
            }
            payload = {
                'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': clean_phone,
                'type': 'text',
                'text': {'preview_url': False, 'body': text},
            }

            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=12)
                data = resp.json()

                if resp.status_code in [200, 201]:
                    msg_id = data.get('messages', [{}])[0].get('id')
                    msg_record.wamid = msg_id
                    msg_record.status = MessageStatus.SENT
                else:
                    msg_record.status = MessageStatus.FAILED
                    err = data.get('error', {}).get('message', resp.text)
                    msg_record.error_message = f"Error Meta API ({resp.status_code}): {err}"
            except Exception as ex:
                msg_record.status = MessageStatus.FAILED
                msg_record.error_message = f"Excepción al conectar con Meta Cloud API: {str(ex)}"

            msg_record.save()
            conversation.last_message_text = text
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['last_message_text', 'last_message_at'])
            return msg_record

        # 3. Ningún servicio activo configurado
        msg_record.status = MessageStatus.FAILED
        msg_record.error_message = (
            f"Servidor de WhatsApp no disponible en {waha_url}. "
            "Asegúrate de iniciar el contenedor WAHA en Docker (docker compose -f docker-compose.waha.yml up -d) "
            "o configurar credenciales en .env."
        )
        msg_record.save()
        conversation.last_message_text = text
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_text', 'last_message_at'])
        return msg_record


    @classmethod
    def send_image_message(cls, phone_number: str, image_url: str, caption: str = '', filename: str = 'ticket.png', conversation: WhatsAppConversation = None, user = None, relative_file_path: str = '') -> WhatsAppMessage:
        """
        Envía una imagen (ej. foto del ticket térmico) al contacto de WhatsApp.
        Si la entrega multimedia falla en WAHA, recurre automáticamente a mensaje de texto.
        """
        clean_phone = cls.normalize_phone(phone_number)
        
        if not conversation:
            contact, _ = WhatsAppContact.objects.get_or_create(
                phone=clean_phone,
                defaults={'display_name': f"Contacto {clean_phone}"}
            )
            conversation, _ = WhatsAppConversation.objects.get_or_create(
                contact=contact,
                defaults={'status': ConversationStatus.EN_ATENCION}
            )

        clean_saved_text = cls.sanitize_message_content(caption or '[Foto de Recibo]')
        msg_record = WhatsAppMessage(
            conversation=conversation,
            direction=MessageDirection.OUTBOUND,
            message_type='image',
            content=clean_saved_text,
            media_url=image_url,
            media_mime_type='image/png',
            sent_by=user,
        )
        if relative_file_path:
            msg_record.media_file.name = relative_file_path

        waha_url = getattr(settings, 'WAHA_API_URL', '')
        if waha_url:
            res = WAHAService.send_image_message(
                phone_number=clean_phone,
                image_url=image_url,
                caption=caption,
                filename=filename
            )
            if res.get('success'):
                raw_wamid = res.get('message_id') or f"waha_{int(time.time()*1000)}"
                if isinstance(raw_wamid, dict):
                    raw_wamid = raw_wamid.get('_serialized') or raw_wamid.get('id') or str(raw_wamid)
                msg_record.wamid = str(raw_wamid)[:140]
                msg_record.status = MessageStatus.SENT
                msg_record.save()
                conversation.last_message_text = clean_saved_text
                conversation.last_message_at = timezone.now()
                conversation.save(update_fields=['last_message_text', 'last_message_at'])
                return msg_record
            else:
                logger.warning("Fallo envío de imagen en WAHA: %s. Reintentando como texto resumen...", res.get('error'))

        # Fallback a mensaje de texto si falla la imagen
        return cls.send_text_message(
            phone_number=clean_phone,
            text=caption,
            conversation=conversation,
            user=user
        )

