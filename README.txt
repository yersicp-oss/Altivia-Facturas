ALTIVIA | GESTION INTELIGENTE DE FACTURAS V2.0
===============================================

DESCRIPCION
Aplicacion web local en Python 3.11+ para registrar facturas, leer datos
basicos con OCR, administrar comprobantes y pagos, exportar libros Excel
y respaldar originales en Google Drive al conectar la cuenta autorizada.

INSTALACION E INICIO WINDOWS
1. Extraer ZIP completo, no ejecutar dentro del ZIP.
2. Instalar Python 3.11 o superior con opcion "Add Python to PATH".
3. Ejecutar INICIAR_ALTIVIA.bat.
4. Crear usuario administrador y contraseña maestra (minimo 10 caracteres).
5. Abrir http://localhost:8765/ y elegir el tipo de ingreso.
6. Mantener la consola abierta mientras se utiliza la aplicacion.

ROL Y ACCESOS V2
- ADMIN: inicia sesion con contraseña; crea miembros, administradores y
  contadores, revisa facturas, gestiona pagos, exporta Excel y conecta Drive.
- CONTADOR: inicia sesion con contraseña; consulta y exporta; no registra.
- MIEMBRO: NO inicia sesion; desde REGISTRAR FACTURA elige su nombre de
  la lista configurada por administrador, sube un comprobante y confirma.
  Este acceso no permite ver, modificar ni descargar registros previos.

IMPORTANTE SOBRE LA IDENTIDAD DE LOS MIEMBROS
Seleccionar un nombre no prueba identidad. Una persona con acceso a la pagina
podria elegir el nombre de otra. El sistema marca en auditoria esos registros
como no autenticados. Se recomienda usar esta modalidad SOLO en redes y
entornos internos confiables. No publicar el formulario libremente en Internet.
Se incluye limite de peticiones para reducir abusos, no es una defensa DDoS.

REGISTRO DE FACTURAS
El formulario solo muestra siete campos:
1. Tipo de comprobante.
2. Serie.
3. Numero correlativo.
4. Fecha de emision.
5. Proveedor/razon social.
6. RUC proveedor (11 digitos).
7. Importe total.

Los campos adicionales de contabilidad de la V1 permanecen en la base de
datos para compatibilidad, pero no se piden al colaborador. Si no se captura
el desglose, el subtotal e IGV no deben considerarse verificados. Los Excel
muestran esos valores en blanco cuando no se dispone de desglose.
La moneda interna por defecto es PEN; cuando el OCR lee claramente USD,
se conserva USD. Antes de usar reportes contables verifica moneda y desglose,
especialmente en documentos sin OCR. Esta V2 no genera registros oficiales SIRE.

OCR EN WINDOWS (MUY IMPORTANTE)
El motor OCR gratuito Tesseract y sus bibliotecas NO vienen empacados en el
ZIP por su peso. Para activar lectura automatica de fotografias:
1. Conectar el equipo a Internet.
2. Ejecutar INSTALAR_OCR.bat. Descarga las bibliotecas Python Pillow,
   pytesseract, OpenCV y PyMuPDF desde pip.
3. El script intenta localizar Tesseract instalado y, si falta, instalarlo
   usando winget (paquete UB-Mannheim.TesseractOCR).
4. Si winget no existe, instalar Tesseract para Windows manualmente desde
   el distribuidor UB Mannheim, asegurando incluir el idioma espanol spa.
5. Reiniciar el sistema ALTIVIA.
6. Ejecutar "python VERIFICAR_OCR.py" para comprobar si el motor ya esta listo.

El OCR detecta y reorienta algunas imagenes, ajusta contraste y prueba
modos de reconocimiento alternativos. Fotos mal iluminadas, torcidas o
borrosas pueden producir datos parciales o erroneos. Comprueba todos los
valores con el comprobante original. Los PDF digitales se extraen con
PyMuPDF y no necesitan Tesseract si contienen texto accesible.

IA VISUAL EXTERNA (OPCIONAL)
Admite OPENAI_VISION_ENABLED=1 y OPENAI_API_KEY como variables de entorno.
Esto envia archivos a una API EXTERNA con cobro propio, NO incluida en
ChatGPT Plus. Solo habilitar tras evaluar privacidad y consentimiento.
Dejar desactivado por defecto. Revisa .env.example.

GOOGLE DRIVE
La carpeta destino configurada es:
https://drive.google.com/drive/folders/1rOoOcJ9SXHHc9BX6tLHjDIfE2_SqkeA1
Para conectar realmente:
1. En Google Cloud Console crear/seleccionar un proyecto y habilitar
   "Google Drive API".
2. Configurar pantalla de consentimiento OAuth, usuarios de prueba (si
   corresponde) y cliente OAuth tipo aplicacion web.
3. Registrar EXACTAMENTE la URI de redireccion:
   http://localhost:8765/drive/callback
4. Descargar JSON del cliente OAuth y guardarlo como:
   data/google_oauth_client.json
5. Entrar como administrador -> Google Drive -> Conectar Google Drive.
6. Autorizar la cuenta que TENGA PERMISO DE EDICION sobre la carpeta.
7. Registrar factura y verificar los respaldos. Las fallidas quedan
   pendientes/error; usar la opcion de sincronizar desde el modulo Drive.

Organizacion: /CARPETA_RAIZ/NOMBRE_USUARIO_clave/FECHA_EMISION_DD-MM-AAAA/
La fecha de subida o registro NO determina la subcarpeta.

ATENCION: Google Drive requiere credenciales y permiso real. La existencia
solo del enlace a una carpeta NO permite que el programa almacene documentos.
No se almacenan tokens en este paquete. Protege data/google_tokens.json.

EXCEL Y CONTABILIDAD
Solo administrador y contador pueden exportar. Contiene hojas Detalle,
Resumen mensual, Proveedores, Proyectos, Estados y Totales por moneda.
Separacion PEN/USD, fechas de emision, estado y responsable. Los valores
contables deben verificarse con la factura y con el contador antes de rendir.

CAMBIOS DESDE V1
- Inicio publico dividido en dos acciones.
- Registro de miembros sin contraseña.
- Selector de miembro previo a elegir foto o PDF.
- Solo siete campos visibles en la confirmacion y edicion.
- Mejorada deteccion OCR y diagnostico de instalaciones Windows.
- Sesiones antiguas de rol miembro ya no dan acceso a datos privados.
- Restricciones y limites adicionales de acceso publico.

ACTUALIZAR SIN PERDER FACTURAS
No reemplaces ni borres data/ antes de respaldarla.
1. Cerrar ALTIVIA V1.
2. Copiar la carpeta completa antigua a una ubicacion de respaldo.
3. Extraer V2 en una carpeta nueva.
4. Copiar desde la version antigua SOLO la carpeta data/ (base de datos,
   archivos y credenciales), sin mezclar codigo V1 con V2.
5. Iniciar V2. La creacion de tablas nuevas se realiza sin eliminar facturas.
6. Verificar usuarios, facturas y Google Drive.
No compartir carpetas data/ con personal no autorizado.

MOVILES Y REDES
Por defecto la app escucha 127.0.0.1 y solo la laptop puede abrirla.
Para acceso en LAN, configurar ALTIVIA_HOST=0.0.0.0 y firewall de forma
controlada; cada celular abre https://servidor/registro con HTTPS frente al
servidor (la camara movil suele necesitar un origen seguro). El servidor
nativo es solo para uso local: para produccion usar proxy HTTPS y controles
perimetrales, preferiblemente un despliegue especializado.

PRUEBAS
En la carpeta de proyecto: python -m unittest discover -s tests -v
Las pruebas automatizadas usan una carpeta temporal; no alteran las facturas
reales de tu data/. La sincronizacion Google no puede probarse sin tus
credenciales y permisos de Drive.

SEGURIDAD: leer tambien README_SEGURIDAD.txt.
