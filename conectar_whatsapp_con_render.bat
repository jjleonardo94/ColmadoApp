@echo off
title Enlace WhatsApp - ColmadoPOS (PC a Render)
color 0B

echo ======================================================================
echo        CONEXION DE WHATSAPP ENTRE TU PC Y COLMADOPOS.ONRENDER.COM
echo ======================================================================
echo.
echo 1. Asegurando que Docker WAHA este encendido...
docker compose -f docker-compose.waha.yml up -d

echo.
echo 2. Iniciando tunel seguro Cloudflare hacia tu PC...
echo    Copia la direccion https://...trycloudflare.com que aparecera debajo
echo    y colocala en la variable WAHA_API_URL en Render.
echo.
echo ======================================================================
echo  [Deja esta ventana abierta para que Render pueda enviar WhatsApp]
echo ======================================================================
echo.

cloudflared.exe tunnel --url http://localhost:3000
pause
