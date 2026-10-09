# ALTIVIA Facturas v3 — Publicar en Render

Esta versión contiene la aplicación completa (`altivia/`, `static/`), un Dockerfile para instalar Tesseract, un `render.yaml` y arranque no interactivo. **No es una aplicación Streamlit**.

## 1. GitHub

1. Descarga y descomprime el ZIP.
2. En tu repositorio `yersicp-oss/Altivia-Facturas` elimina archivos sueltos incorrectos solo si no has realizado cambios propios.
3. Sube **el contenido de la carpeta `ALTIVIA_Facturas_Render_v3` a la raíz del repositorio**, no la carpeta contenedora ni el ZIP. Deben verse `render.yaml`, `Dockerfile`, `cloud_start.py`, `altivia/` y `static/` en la raíz.
4. NO subas `.env`, la carpeta `data` con facturas, contraseñas ni credenciales OAuth.

## 2. Render

1. En https://dashboard.render.com/ selecciona **New > Blueprint** y conecta tu repositorio GitHub.
2. Render leerá `render.yaml` y creará el servicio Docker.
3. Se requiere un **plan Starter de pago** con disco persistente (10 GB por defecto). No elijas Free para datos reales: se perderían en cada despliegue.
4. Completa las variables secretas solicitadas: `ALTIVIA_ADMIN_USER` (p. ej. admin.altivia), `ALTIVIA_ADMIN_PASSWORD` (mínimo 12 caracteres y única); `GOOGLE_REDIRECT_URI` puede dejarse sin valor hasta conectar Drive.
5. Publica y espera los logs: `Administrador inicial creado` y `ALTIVIA Gestión de Facturas`.
6. Abre `https://TU-SERVICIO.onrender.com/`. Usa **Iniciar sesión** como administrador y crea los miembros.
7. Después del primer inicio, elimina `ALTIVIA_ADMIN_PASSWORD` de las variables en Render (se almacena en la base como hash, no se necesita más). **No elimines el disco persistente.**

## 3. OCR

Docker instala Tesseract (español e inglés), Pillow, pytesseract, pypdf, pdf2image y OpenCV desde `requirements-ocr.txt`. Puedes probar con una fotografía en el formulario. La extracción es heurística y **NO garantiza** detectar todos los valores: los siete campos deben verificarse manualmente. `OPENAI_VISION_ENABLED=0` evita el envío externo de imágenes.

## 4. Google Drive (configuración posterior)

`GOOGLE_DRIVE_ROOT_ID` está preconfigurado con la carpeta facilitada. La conexión **NO queda autorizada automáticamente**. Se necesita crear credencial OAuth de aplicación web con URI de redirección `https://TU-SERVICIO.onrender.com/drive/callback`, guardarla **fuera de GitHub** en `/var/data/google_oauth_client.json`, configurar `GOOGLE_REDIRECT_URI` con esa URI y autorizar desde el módulo Drive del administrador. El sistema actual lee ese JSON desde el disco persistente, por lo que necesitarás cargarlo por un método privado y seguro antes de conectar Google. No publiques el JSON. Sin conexión, el respaldo queda local con estado pendiente/error; conserva y respalda `/var/data`.

## 5. Precauciones importantes

- Esta v3 adapta la v2 a Render; **no es una auditoría de seguridad ni un SaaS listo para datos sensibles de producción**.
- Los miembros no se autentican y pueden seleccionar el nombre de otro miembro: no uses el sistema para atribución legal de documentos sin validación adicional.
- Solo admite una instancia del servicio debido a SQLite y disco local.
- La persistencia exige disco; realiza copias de seguridad externas cifradas (el disco no sustituye los backups).
- No subas facturas reales hasta probar permisos, recuperación de backups y Drive.
- El servidor integrado de Python fue conservado para compatibilidad; para una exposición empresarial permanente conviene migrar a un servidor y framework auditables (FastAPI/Flask + servidor de producción).

## 6. Diagnóstico

- `ModuleNotFoundError: No module named altivia`: carpeta `altivia/` ausente o archivos subidos en subdirectorio incorrecto.
- `No existe administrador`: faltan variables secretas y/o disco persistente.
- `Tesseract not found`: reconstruir imagen Docker y revisar logs; no usar `.bat` en Render.
- `health check` falla: revisar logs y validar que el servicio escucha `0.0.0.0:$PORT`.

## Para Windows

Los scripts anteriores `INICIAR_ALTIVIA.bat` e `INSTALAR_OCR.bat` se conservan para operación local. Para Render no se ejecutan.
