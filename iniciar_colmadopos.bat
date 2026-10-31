@echo off
title ColmadoPOS - Servidor Local
color 0A

echo ========================================================
echo        INICIANDO COLMADOPOS Y SERVICIO WHATSAPP
echo ========================================================
echo.

echo 1. Verificando contenedor Docker de WhatsApp (WAHA)...
docker compose -f docker-compose.waha.yml up -d

echo.
echo 2. Iniciando servidor web de ColmadoPOS...
echo    Acceso en tu navegador: http://localhost:8000
echo    Usuario: admin  ^|  Clave: admin123
echo.
echo ========================================================
echo [Presione Ctrl + C en esta ventana para detener el servidor]
echo ========================================================
echo.

python manage.py runserver 0.0.0.0:8000
pause

