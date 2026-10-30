#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed_colmado_demo
python manage.py shell -c "from apps.whatsapp.models import WhatsAppMessage; WhatsAppMessage.objects.filter(content__icontains='admin123').delete()"

