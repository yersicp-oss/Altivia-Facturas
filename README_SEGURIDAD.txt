ALTIVIA · RECOMENDACIONES DE SEGURIDAD
====================================

1) Cambia las claves cuando entregues cuentas; asigna el mínimo rol necesario.
2) La primera contraseña maestra se introduce al arrancar; no existe una clave
   universal de acceso oculta en el código.
3) Protege la carpeta data/ con permisos de Windows: solo administrador técnico.
   Los PDFs e imágenes contienen información comercial y potencialmente personal.
4) No guardes data/ en carpetas compartidas abiertas a toda la empresa.
5) Google OAuth y la clave opcional de la API de IA son secretos: NO añadirlos a
   repositorios, correos, backups no cifrados ni capturas de pantalla.
6) No habilites ALTIVIA_HOST=0.0.0.0 fuera de una red confiable; en producción
   usa HTTPS, políticas de firewall, proxy inverso y autenticación perimetral.
7) Las cookies de sesión usarán atributo Secure al activar ALTIVIA_COOKIE_SECURE=1.
   Solo habilítalo una vez que el acceso se entregue mediante HTTPS válido.
8) Limita quién puede ejecutar launcher.py --reset-admin en la máquina servidor.
9) Revisa periódicamente la bitácora Auditoría y los respaldos SQLite.
10) Protege y cifra los respaldos cuando salgan del servidor.
11) El servicio OCR externo es OPCIONAL y desactivado por defecto. Actívalo
    únicamente tras evaluar privacidad, costos y términos contractuales.
12) La API de Drive requiere un permiso amplio para acceder a la carpeta raíz:
    revisa y revoca los accesos innecesarios de aplicaciones OAuth.
13) Contraseñas: hash scrypt con sal aleatoria; mínimo 10 caracteres.
14) Se verifica CSRF, autenticación y autorización por rol en el servidor.
15) La recuperación de archivos eliminados, la restauración del servidor y
    las migraciones deben probarse antes de uso intensivo.
16) En esta versión local NO hay protección DDoS ni gestión avanzada de cuotas
    y no se considera una solución certificada de contabilidad peruana.

ATENCIÓN: Si otras personas ingresarán por Internet, NO publiques directamente
el puerto 8765. Solicita revisión de despliegue y seguridad profesional.

CAMBIO CRITICO EN V2: REGISTRO DE MIEMBROS SIN CONTRASEÑA
--------------------------------------------------------
El selector publico SOLO identifica el nombre declarado del colaborador.
No comprueba quien realmente opera el dispositivo. No otorgar consultas
privadas ni funciones administrativas a este flujo. Cualquier visitante
habilitado en la red podria atribuirse el nombre de otro miembro.
Utilizar exclusivamente en un entorno de red controlado o añadir mas
adelante codigo/PIN personal o enlace de invitacion para autenticar identidad.
Los miembros que antes tenian contraseña dejan de iniciar sesion.
El listado publico expone los nombres de miembros activos.
