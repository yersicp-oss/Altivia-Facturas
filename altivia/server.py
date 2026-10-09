"""ALTIVIA Gestión Inteligente de Facturas · server-side stdlib web application."""
import os, re, io, sys, json, html, math, time, sqlite3, hmac, base64, shutil, hashlib, secrets, pathlib, threading, traceback
from datetime import date,datetime,timezone,timedelta
from collections import defaultdict,Counter
from urllib.parse import urlparse,parse_qs,urlencode,quote
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from email.parser import BytesParser
from email.policy import default as mailpolicy
from .db import DATA,db,init_db,now,hash_password,verify_password,audit,paid_total,payment_status
from .ocr import extract, normal_date
from . import drive,excel

STATIC=pathlib.Path(__file__).resolve().parent.parent/'static'
UPLOADS=DATA/'uploads';TEMPS=DATA/'tmp';UPLOADS.mkdir(exist_ok=True,parents=True);TEMPS.mkdir(exist_ok=True,parents=True)
MAX_UPLOAD=15*1024*1024; COOKIE='altivia_session'; GUEST='altivia_login_csrf';
ROLES={'admin':'Administrador','miembro':'Miembro','contador':'Contador'}
STATUSES=['Pendiente','En revisión','Aprobada','Observada','Rechazada']
CURRENCIES={'PEN':'S/','USD':'US$'}

def e(s):return html.escape(str(s if s is not None else ''),quote=True)
def val(data,k,default=''):return str(data.get(k,[default])[0]).strip()
def fd(s):return s[8:10]+'-'+s[5:7]+'-'+s[:4] if s and len(s)>=10 else '—'
def clean_name(s):return re.sub(r'[^A-Za-z0-9._-]','_',str(s))[:90]
def ident(s):return str(s).strip().lower()
def amount(value,default=0):
    s=str(value if value is not None else '').strip().replace(' ','')
    if not s:return default
    if not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?',s):raise ValueError('Monto inválido: use el punto decimal, por ejemplo 120.50.')
    return round(float(s),2)
def require_date(value,label='Fecha',allow_empty=False):
    if not value and allow_empty:return None
    result=normal_date(value) if len(value)>=8 else ''
    if not result:raise ValueError(label+' inválida. Utiliza día-mes-año.')
    if int(result[:4])<2000 or int(result[:4])>2100:raise ValueError(label+' fuera de rango.')
    return result

def project_options(c,selected=None):
    rows=c.execute('SELECT id,name FROM projects WHERE active=1 ORDER BY name').fetchall()
    return '<option value="">Sin proyecto</option>'+''.join(f'<option value="{x["id"]}" {"selected" if str(x["id"])==str(selected) else ""}>{e(x["name"])}</option>' for x in rows)

def layout(user,title,body,active='',flash='',csrf='',drive_connected=False):
    role=user['role'] if user else ''
    nav=[('/dashboard','Inicio','house'),('/invoices','Facturas','receipt')]
    if role in ('admin','miembro'):nav.insert(1,('/invoices/new','Registrar factura','plus-circle'))
    if role in ('admin','contador'):nav.append(('/accounting','Contabilidad','calculator'))
    if role=='admin':nav += [('/users','Usuarios','users'),('/projects','Proyectos','folder'),('/drive','Google Drive','cloud'),('/audit','Auditoría','shield')]
    menu=''.join(f'<a class="nav-item {"selected" if active==x[0] else ""}" href="{x[0]}"><span class="nav-icon">{svg(x[2])}</span><span>{e(x[1])}</span></a>' for x in nav)
    f='<div class="notice">'+e(flash)+'</div>' if flash else ''
    avatar=''.join([x[0].upper() for x in user['full_name'].split()[:2]]) if user else 'A'
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#11294b"><title>{e(title)} · ALTIVIA</title><link rel="stylesheet" href="/static/style.css"><link rel="icon" href="/static/favicon.svg" type="image/svg+xml"></head>
    <body><div class="shell"><aside id="sidebar" class="sidebar"><a class="brand" href="/dashboard"><span class="brand-mark">A<span class="dot">.</span></span><span><strong>ALTIVIA</strong><small>GESTIÓN DE FACTURAS</small></span></a><div class="side-label">PLATAFORMA</div><nav>{menu}</nav><div class="sidebar-foot"><span class="status-dot"></span> Almacenamiento privado<br><small>Drive: {'conectado' if drive_connected else 'pendiente de conectar'}</small></div></aside>
    <main class="main"><header class="topbar"><button id="mobileMenu" class="iconbtn mobile-menu" type="button" aria-label="Abrir menú">☰</button><div class="breadcrumbs">ALTIVIA <span>/</span> {e(title)}</div><div class="top-actions"><span class="profile"><span class="initials">{e(avatar)}</span><span class="profile-text"><strong>{e(user['full_name'])}</strong><small>{ROLES[role]}</small></span></span><form method="post" action="/logout" class="inline"><input type="hidden" name="csrf" value="{e(csrf)}"><button class="logout" type="submit" title="Cerrar sesión">Salir ↗</button></form></div></header>
    <div class="content">{f}{body}<footer class="app-footer">ALTIVIA CONSULTORES · Control documental privado · Los comprobantes requieren validación humana.</footer></div></main></div><script defer src="/static/app.js"></script></body></html>'''

ICONS={'house':'<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>','receipt':'<path d="M4 3h16v18l-4-2-4 2-4-2-4 2z"/><path d="M8 8h8M8 12h8"/>','plus-circle':'<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>','users':'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 6a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5"/>','calculator':'<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 7h8M8 12h2M14 12h2M8 16h2M14 16h2"/>','folder':'<path d="M3 6h7l2 2h9v11H3z"/>','cloud':'<path d="M8 19h11a4 4 0 0 0 0-8 7 7 0 0 0-14-1 4 4 0 0 0 3 9"/>','shield':'<path d="m12 2 9 4v6c0 5-4 8-9 10-5-2-9-5-9-10V6z"/>'}
def svg(kind):return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+ICONS.get(kind,'')+'</svg>'

def titlebar(title,description='',actions=''):
    return f'<div class="pagehead"><div><h1>{e(title)}</h1><p>{e(description)}</p></div><div class="page-actions">{actions}</div></div>'
def badge(status):
    css={'Pendiente':'warn','En revisión':'info','Aprobada':'success','Observada':'danger','Rechazada':'muted','Pagada':'success','Pago parcial':'info','Pendiente de pago':'warn','Sincronizada':'success','Error':'danger'}.get(status,'muted')
    return f'<span class="badge {css}"><span class="badge-dot"></span>{e(status)}</span>'
def cards(items):
    return '<section class="cards">'+''.join(f'<div class="kpi"><div class="kpi-top"><span>{e(a)}</span><span class="kpi-ico">{e(c)}</span></div><strong>{e(b)}</strong><small>{e(d)}</small></div>' for a,b,c,d in items)+'</section>'
def textbox(label,name,value='',type='text',required=False,extra='',placeholder=''):
    return f'<label class="field"><span>{e(label)}</span><input name="{e(name)}" type="{e(type)}" value="{e(value)}" placeholder="{e(placeholder)}" {"required" if required else ""} {extra}></label>'
def dropdown(label,name,opts,selected=''):
    return f'<label class="field"><span>{e(label)}</span><select name="{e(name)}">'+''.join(f'<option value="{e(k)}" {"selected" if str(k)==str(selected) else ""}>{e(v)}</option>' for k,v in opts)+'</select></label>'
def filter_form(endpoint,query,admin=False):
    return f'''<form class="filterbar" method="get" action="{endpoint}">
    <input name="q" placeholder="Buscar factura, proveedor, RUC…" aria-label="Buscar" value="{e(val(query,'q'))}">
    <label>Desde<input type="date" name="from" value="{e(val(query,'from'))}"></label>
    <label>Hasta<input type="date" name="to" value="{e(val(query,'to'))}"></label>
    <select name="status"><option value="">Todos los estados</option>{''.join(f'<option value="{e(s)}" {"selected" if val(query,"status")==s else ""}>{e(s)}</option>' for s in STATUSES)}</select>
    <select name="currency"><option value="">Todas las monedas</option>{''.join(f'<option value="{s}" {"selected" if val(query,"currency")==s else ""}>{s}</option>' for s in CURRENCIES)}</select>
    <button class="btn btn-secondary" type="submit">Filtrar</button><a class="textlink" href="{endpoint}">Limpiar</a></form>'''

def filtered(c,user,query,limit=None):
    parts=['i.deleted_at IS NULL']; params=[]
    if user['role']=='miembro':parts.append('i.owner_id=?');params.append(user['id'])
    q=val(query,'q')[:120]
    if q:
        parts.append("(i.provider LIKE ? OR i.ruc LIKE ? OR i.number LIKE ? OR i.series LIKE ? OR u.full_name LIKE ? OR i.description LIKE ?)")
        params += ['%'+q+'%']*6
    for key,op in [('from','>='),('to','<=')]:
        v=val(query,key)
        if v and re.fullmatch(r'\d{4}-\d\d-\d\d',v):parts.append('i.issued_on'+op+'?');params.append(v)
    if val(query,'status') in STATUSES:parts.append('i.review_status=?');params.append(val(query,'status'))
    if val(query,'currency') in CURRENCIES:parts.append('i.currency=?');params.append(val(query,'currency'))
    sql='''SELECT i.*,u.full_name owner_name,p.name project_name,COALESCE(pay.paid,0) paid
      FROM invoices i JOIN users u ON u.id=i.owner_id LEFT JOIN projects p ON p.id=i.project_id
      LEFT JOIN (SELECT invoice_id,SUM(amount) paid FROM payments GROUP BY invoice_id) pay ON pay.invoice_id=i.id
      WHERE '''+' AND '.join(parts)+' ORDER BY i.issued_on DESC,i.id DESC'
    if limit:sql+=' LIMIT ?';params.append(limit)
    rows=[dict(r) for r in c.execute(sql,params)]
    for x in rows:x['payment_status']=payment_status(x['total'],x['paid'])
    return rows

def invoice_table(rows,extra=False):
    out=['<div class="table-wrap"><table class="datatable"><thead><tr><th>Fecha emisión</th><th>Comprobante</th><th>Proveedor</th><th>Responsable</th><th>Importe</th><th>Revisión</th><th>Pago</th><th>Archivo</th></tr></thead><tbody>']
    for a in rows:
        ident=f'{a["series"]}-{a["number"]}'.strip('-') or f'#{a["id"]}'
        curr=CURRENCIES.get(a['currency'],a['currency'])
        out.append(f'<tr><td class="nowrap">{fd(a["issued_on"])}</td><td><a class="cell-primary" href="/invoices/{a["id"]}">{e(ident)}</a><small>{e(a["receipt_type"])}</small></td><td><strong>{e(a["provider"])}</strong><small>{e(a["ruc"])}</small></td><td>{e(a["owner_name"])}</td><td class="nowrap amount">{curr} {a["total"]:,.2f}</td><td>{badge(a["review_status"])}</td><td>{badge(a["payment_status"])}</td><td><a class="iconlink" href="/invoices/{a["id"]}/file" target="_blank" rel="noopener">Ver ↗</a></td></tr>')
    return ''.join(out)+('</tbody></table><div class="empty">No hay facturas para los filtros seleccionados.</div>' if not rows else '</tbody></table>')+'</div>'

def invoice_fields(c,prefix='',values=None,owner_control=False):
    """Seven visible fields requested by ALTIVIA. Remaining ledger fields are internal."""
    a=values or {};g=lambda k:a.get(k,'') or ''
    return f'''<div class="formgrid invoice-seven">
      {dropdown('Tipo de comprobante','receipt_type',[(x,x) for x in ('Factura','Boleta','Nota de crédito','Otro')],g('receipt_type') or 'Factura')}
      {textbox('Serie','series',g('series'),required=True,placeholder='F001',extra='maxlength="8"')}
      {textbox('Número correlativo','number',g('number'),required=True,placeholder='000123',extra='maxlength="16"')}
      {textbox('Fecha de emisión','issued_on',g('issued_on'),'date',True)}
      {textbox('Proveedor / razón social','provider',g('provider'),required=True)}
      {textbox('RUC del proveedor','ruc',g('ruc'),required=True,extra='inputmode="numeric" pattern="[0-9]{11}" maxlength="11"')}
      {textbox('Importe total','total',g('total'),required=True,extra='inputmode="decimal" placeholder="Ej.: 118.00"')}
    </div><input type="hidden" name="currency" value="{e(g('currency') or 'PEN')}">'''

def upload_widget(c,csrf,public=False):
    """Common upload/verification workflow for administrators and public members."""
    members=c.execute("SELECT id,full_name FROM users WHERE role='miembro' AND active=1 ORDER BY full_name COLLATE NOCASE").fetchall() if public else []
    select=''
    if public:
        if not members:
            return '<section class="panel"><h3>No hay colaboradores habilitados</h3><p>El administrador debe crear primero al menos un miembro en la sección Usuarios.</p><a class="btn btn-secondary" href="/">Volver</a></section>'
        choices=''.join(f'<option value="{x["id"]}">{e(x["full_name"])}</option>' for x in members)
        select=f'''<section class="panel" id="selectMember"><div class="panel-header"><div><h3>1. ¿Quién está registrando la factura?</h3><p class="hint">Elige tu nombre de la lista habilitada por el administrador.</p></div></div><label class="field"><span>Colaborador</span><select id="publicOwner" name="owner_id" required><option value="">Seleccionar mi nombre…</option>{choices}</select></label><button type="button" class="btn btn-primary" id="memberNext">Continuar →</button><p class="hint">El acceso sin contraseña permite identificar quién entrega el comprobante, pero no verifica su identidad. Solo se permite registrar; los comprobantes y reportes siguen privados.</p></section>'''
    num='2' if public else '1';num2='3' if public else '2'
    return select+f'''<section class="panel {"hidden" if public else ""}" id="captureScreen"><div class="panel-header"><div><h3>{num}. Selecciona un documento</h3><p class="hint">Foto desde tu celular, imagen existente o PDF original. Límite: 15 MB.</p></div>{'<button class="btn btn-secondary" id="changeMember" type="button">Cambiar colaborador</button>' if public else ''}</div>
    <div class="uploadchoices"><label class="uploadtile"><strong>📷 Tomar foto</strong><span>Usar cámara del teléfono</span><input type="file" accept="image/*" capture="environment" class="invoiceUpload" data-mode="camera"></label><label class="uploadtile"><strong>▧ Subir fotografía</strong><span>JPG, PNG o WEBP</span><input type="file" accept="image/jpeg,image/png,image/webp" class="invoiceUpload" data-mode="photo"></label><label class="uploadtile"><strong>▤ Subir PDF</strong><span>Comprobante digital o escaneado</span><input type="file" accept="application/pdf" class="invoiceUpload" data-mode="pdf"></label></div><div id="analysisStatus" class="analysis-status" aria-live="polite"></div></section>
    <section class="panel hidden" id="reviewScreen"><div class="panel-header"><div><h3>{num2}. Verificar datos de factura</h3><p class="hint">Verifica los siete datos antes de guardar. Los campos no reconocidos quedan vacíos.</p></div><button class="btn btn-secondary" id="changeFile" type="button">Cambiar archivo</button></div><div id="ocrWarnings"></div><form method="post" action="/invoices/create" id="invoiceForm"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="draft_token" id="draft_token">{'<input type="hidden" name="owner_id" id="selectedOwner">' if public else ''}{invoice_fields(c)}<div class="form-actions"><button class="btn btn-primary" type="submit">✓ Confirmar y guardar factura</button><button class="btn btn-secondary" type="button" id="cancelReview">Cancelar</button></div></form></section>'''

def public_page(title,body):
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} · ALTIVIA</title><link rel="stylesheet" href="/static/style.css"><link rel="icon" href="/static/favicon.svg" type="image/svg+xml"></head><body class="publicbody"><header class="publichead"><a href="/" class="publicbrand">A<span>.</span> ALTIVIA <small>FACTURAS</small></a><nav><a href="/">Inicio</a><a class="btn btn-secondary" href="/login">Ingreso administrativo</a></nav></header><main class="publiccontent">{body}<footer class="app-footer">ALTIVIA CONSULTORES · Registro de comprobantes · Solo los administradores y contadores autorizados pueden revisar registros.</footer></main><script defer src="/static/app.js"></script></body></html>'''

def public_home():
    return public_page('Bienvenido','''<section class="welcome"><div class="welcome-tag">ALTIVIA · GESTIÓN INTELIGENTE</div><h1>Bienvenido a la plataforma de facturas</h1><p>Elige cómo deseas ingresar. Si eres colaborador, puedes registrar una factura directamente seleccionando tu nombre.</p><div class="entrygrid"><a class="entrycard" href="/registro"><span class="entryicon">📷</span><h2>Registrar factura</h2><p>Colaboradores · Sin contraseña</p><strong>Seleccionar mi nombre y subir comprobante →</strong></a><a class="entrycard" href="/login"><span class="entryicon">🔐</span><h2>Iniciar sesión</h2><p>Administrador y contador</p><strong>Ingresar con usuario y contraseña →</strong></a></div></section>''')

def invoice_detail(c,a,user,csrf):
    a=dict(a)
    paid=paid_total(c,a['id']);status=payment_status(a['total'],paid);remaining=max(0,a['total']-paid)
    file_url=f'/invoices/{a["id"]}/file'
    attrs=[('Fecha de emisión',fd(a['issued_on'])),('Fecha de registro',fd(a['created_at'][:10])),('Proveedor',a['provider']),('RUC',a['ruc'] or '—'),
        ('Número',f'{a["series"]}-{a["number"]}'),('Tipo',a['receipt_type']),('Subtotal','No desglosado' if not a['subtotal'] and not a['igv'] else f'{a["currency"]} {a["subtotal"]:,.2f}'),
        ('IGV declarado','No desglosado' if not a['subtotal'] and not a['igv'] else f'{a["currency"]} {a["igv"]:,.2f}'),('Importe total',f'{a["currency"]} {a["total"]:,.2f}'),
        ('Responsable',a['owner_name']),('Proyecto',a['project_name'] or '—'),('Estado Drive',a['drive_status'])]
    info=''.join(f'<div><small>{e(k)}</small><strong>{e(v)}</strong></div>' for k,v in attrs)
    review=''
    if user['role'] in ('admin','contador'):
        statuses=STATUSES if user['role']=='admin' else ['Observada']
        review=f'''<section class="panel"><h3>Revisión de comprobante</h3><form method="post" action="/invoices/{a['id']}/review"><input type="hidden" name="csrf" value="{e(csrf)}">{dropdown('Estado','review_status',[(s,s) for s in statuses],a['review_status'])}<label class="field"><span>Observación</span><textarea name="review_notes" rows="3">{e(a['review_notes'])}</textarea></label><button class="btn btn-primary">Guardar revisión</button></form></section>'''
    actions=f'<a class="btn btn-secondary" href="{file_url}" target="_blank" rel="noopener">Abrir respaldo ↗</a>'
    if user['role']=='admin' or (user['role']=='miembro' and a['review_status']=='Observada'):
        actions+=f'<a class="btn btn-secondary" href="/invoices/{a["id"]}/edit">Corregir datos</a><a class="btn btn-secondary" href="/invoices/{a["id"]}/replace">Reemplazar foto/PDF</a>'
    if user['role']=='admin':
        actions+=f'<form method="post" action="/invoices/{a["id"]}/delete" data-confirm="¿Enviar esta factura a la papelera?" class="inline"><input type="hidden" name="csrf" value="{e(csrf)}"><button class="btn btn-danger" type="submit">Enviar a papelera</button></form>'
    pays=c.execute('SELECT p.*,u.full_name author FROM payments p JOIN users u ON p.created_by=u.id WHERE invoice_id=? ORDER BY paid_on DESC,id DESC',(a['id'],)).fetchall()
    payrows=''.join(f'<tr><td>{fd(x["paid_on"])}</td><td>{e(x["currency"])} {x["amount"]:,.2f}</td><td>{e(x["method"])}</td><td>{e(x["reference"])}</td><td>{e(x["author"])}</td></tr>' for x in pays)
    pay_form=''
    if user['role']=='admin':
        pay_form=f'''<form class="formgrid compact" method="post" action="/invoices/{a['id']}/pay"><input type="hidden" name="csrf" value="{e(csrf)}">
        {textbox('Fecha de pago','paid_on',date.today().isoformat(),'date',True)}{textbox('Importe abonado','amount',f'{remaining:.2f}' if remaining else '',required=True)}
        {dropdown('Moneda','currency',[(a['currency'],a['currency'])],a['currency'])}{textbox('Medio de pago','method',placeholder='Transferencia')}{textbox('N.º de operación','reference')}
        <div class="form-actions wide"><button class="btn btn-primary">Registrar abono</button></div></form>'''
    preview=f'<iframe title="Vista previa" src="{file_url}" class="preview-pdf"></iframe>' if a['mime_type']=='application/pdf' else f'<img class="preview-image" alt="Respaldo de factura" src="{file_url}">'
    return titlebar(f'Comprobante #{a["id"]}',f'{a["receipt_type"]} · {a["series"]}-{a["number"]}',actions)+f'''<div class="detailgrid"><div><section class="panel"><div class="panel-header"><h3>Información del comprobante</h3>{badge(a['review_status'])}</div><div class="detail-list">{info}</div><h4>Descripción</h4><p class="description">{e(a['description']) or 'Sin descripción'}</p><h4>Observaciones</h4><p class="description">{e(a['review_notes']) or 'Sin observaciones'}</p></section>
    <section class="panel"><div class="panel-header"><h3>Control de pagos</h3>{badge(status)}</div><div class="payment-metrics"><div>Pagado <strong>{a['currency']} {paid:,.2f}</strong></div><div>Pendiente <strong>{a['currency']} {remaining:,.2f}</strong></div></div>{pay_form}<div class="table-wrap"><table class="datatable small-table"><thead><tr><th>Fecha</th><th>Importe</th><th>Medio</th><th>Referencia</th><th>Por</th></tr></thead><tbody>{payrows or '<tr><td colspan="5">Sin pagos registrados</td></tr>'}</tbody></table></div></section>{review}</div>
    <aside><section class="panel"><div class="panel-header"><h3>Documento original</h3></div>{preview}<p class="hint">{e(a['original_filename'])} · Respaldo conservado en el servidor.</p></section></aside></div>'''

def parse_invoice(form):
    tp=val(form,'receipt_type')
    if tp not in ('Factura','Boleta','Nota de crédito','Otro'):raise ValueError('Tipo de documento inválido.')
    issued=require_date(val(form,'issued_on'),'Fecha de emisión')
    due=require_date(val(form,'due_on'),'Fecha de vencimiento',True)
    provider=val(form,'provider')[:180]
    if len(provider)<2:raise ValueError('Escribe el nombre del proveedor.')
    ruc=val(form,'ruc');
    if not re.fullmatch(r'\d{11}',ruc):raise ValueError('El RUC del proveedor debe tener 11 dígitos.')
    series=val(form,'series').upper()[:8];number=val(form,'number')[:16]
    if not series or not number:raise ValueError('Ingresa tanto la serie como el correlativo.')
    total=amount(val(form,'total'),None)
    if total is None or total <= 0:raise ValueError('El importe total debe ser mayor que cero.')
    sub=amount(val(form,'subtotal'));igv=amount(val(form,'igv'))
    currency=val(form,'currency','PEN')
    if currency not in CURRENCIES:raise ValueError('Moneda inválida.')
    terms=val(form,'terms')
    if terms not in ('','Contado','Crédito'):raise ValueError('Condición de pago no reconocida.')
    pr=val(form,'project_id');pr=int(pr) if pr and pr.isdigit() else None
    return dict(receipt_type=tp,series=series,number=number,issued_on=issued,due_on=due,provider=provider,ruc=ruc,
           description=val(form,'description')[:1000],subtotal=sub,igv=igv,total=total,currency=currency,terms=terms,project_id=pr)

def _get_invoice(c,i,user):
    a=c.execute('''SELECT i.*,u.full_name owner_name,p.name project_name FROM invoices i JOIN users u ON i.owner_id=u.id LEFT JOIN projects p ON i.project_id=p.id WHERE i.id=? AND i.deleted_at IS NULL''',(i,)).fetchone()
    return a if a and (user['role']!='miembro' or a['owner_id']==user['id']) else None

def _duplicate(c,a,exclude_id=0):
    if not (a['ruc'] and a['series'] and a['number']):return []
    return c.execute('''SELECT i.id,u.full_name FROM invoices i JOIN users u ON i.owner_id=u.id
      WHERE i.ruc=? AND i.receipt_type=? AND i.series=? AND i.number=? AND i.deleted_at IS NULL AND i.id<>?''',
      (a['ruc'],a['receipt_type'],a['series'],a['number'],exclude_id)).fetchall()

def _error_page(message,status=400):return f'<div class="error-page"><h2>No se pudo completar la acción</h2><p>{e(message)}</p><a class="btn btn-primary" href="/">Volver al inicio</a></div>'

class App(BaseHTTPRequestHandler):
    server_version='ALTIVIA/2.0';sys_version=''
    def log_message(self,fmt,*args):
        print('[%s] %s'%(self.log_date_time_string(),fmt%args),file=sys.stderr)
    def _cookie(self,key):
        try:return SimpleCookie(self.headers.get('Cookie',''))[key].value
        except (KeyError,Exception):return ''
    def response(self,body,status=200,content_type='text/html; charset=utf-8',headers=None,cookies=None):
        if isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status)
        for k,v in [('Content-Type',content_type),('Content-Length',str(len(body))),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),
            ('Referrer-Policy','strict-origin-when-cross-origin'),('Cache-Control','no-store'),
            ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com")]:self.send_header(k,v)
        if headers:
            for k,v in headers.items():self.send_header(k,v)
        if cookies:
            for x in cookies:self.send_header('Set-Cookie',x)
        self.end_headers();self.wfile.write(body)
    def redirect(self,url,cookies=None):self.response(b'',303,headers={'Location':quote(url,safe='/:?=&%+#')},cookies=cookies)
    def cookieheader(self,key,value,max_age=12*3600):
        secure='; Secure' if os.getenv('ALTIVIA_COOKIE_SECURE','0')=='1' else ''
        return f'{key}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}'
    def _auth(self,c):
        t=self._cookie(COOKIE)
        if not t:return None,None
        h=hashlib.sha256(t.encode()).hexdigest()
        s=c.execute('''SELECT s.*,u.id uid,u.username,u.full_name,u.role,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?''',(h,now())).fetchone()
        if not s or not s['active'] or s['role'] not in ('admin','contador'):return None,None
        return {'id':s['uid'],'username':s['username'],'full_name':s['full_name'],'role':s['role']},dict(s)
    def _form(self):
        length=int(self.headers.get('Content-Length','0'))
        if length>MAX_UPLOAD+200000:self.fail('Archivo demasiado grande (máximo 15 MB).',413);return None,None
        raw=self.rfile.read(length)
        if self.headers.get('Content-Type','').startswith('multipart/form-data'):
            mime=self.headers['Content-Type'];msg=BytesParser(policy=mailpolicy).parsebytes(('MIME-Version: 1.0\r\nContent-Type: '+mime+'\r\n\r\n').encode()+raw)
            fields={};files={}
            for part in msg.iter_parts():
                cd=part.get('Content-Disposition','');k=part.get_param('name',header='content-disposition')
                if not k:continue
                filename=part.get_filename()
                if filename is not None:files[k]=(filename,part.get_payload(decode=True) or b'')
                else:fields[k]=[(part.get_payload(decode=True) or b'').decode('utf-8','replace')]
            return fields,files
        return parse_qs(raw.decode('utf-8','replace'),keep_blank_values=True),{}
    def fail(self,message,status=400):
        c=db();user,sess=self._auth(c)
        if user:self.response(layout(user,'Error',_error_page(message),csrf=sess['csrf']),status)
        else:self.response(_error_page(message),status)
        c.close()
    def _csrf(self,form,sess,user):
        submitted=val(form,'csrf') or self.headers.get('X-CSRF-Token','')
        expected=sess['csrf'] if user else self._cookie(GUEST)
        return bool(expected and hmac.compare_digest(submitted,expected))
    def _flash(self,q):return (q.get('msg',[''])[0] or '')[:200]
    def do_GET(self):
        p=urlparse(self.path);path=p.path;q=parse_qs(p.query,keep_blank_values=True)
        if path=='/healthz':return self.response('ok',200,'text/plain; charset=utf-8')
        if path.startswith('/static/'):
            name=path[8:]
            if name not in ('app.js','style.css','favicon.svg'):return self.response('No encontrado',404)
            typ={'app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8','favicon.svg':'image/svg+xml'}[name]
            return self.response((STATIC/name).read_bytes(),200,typ)
        c=db()
        try:
            user,sess=self._auth(c)
            if path=='/login':return self.login_page()
            if path=='/':return self.response(public_home()) if not user else self.redirect('/dashboard')
            if path=='/registro':
                if user:return self.redirect('/invoices/new') if user['role']=='admin' else self.redirect('/dashboard')
                csrf=secrets.token_urlsafe(28)
                body=titlebar('Registrar factura','Selecciona tu nombre, captura el comprobante y confirma los datos.')+upload_widget(c,csrf,public=True)
                return self.response(public_page('Registrar factura',body),cookies=[self.cookieheader(GUEST,csrf,3600)])
            if path=='/registro/exito':
                return self.response(public_page('Factura registrada','<section class="panel publicsuccess"><div class="successsymbol">✓</div><h1>Factura registrada correctamente</h1><p>El comprobante fue recibido y se encuentra pendiente de revisión. Puedes registrar otra factura.</p><a class="btn btn-primary" href="/registro">Registrar otra factura</a><a class="btn btn-secondary" href="/">Volver al inicio</a></section>'))
            if not user:
                if path in ('/','/dashboard'):return self.redirect('/login')
                if path=='/drive/callback':return self.fail('Tu sesión caducó. Vuelve a iniciar sesión.',401)
                return self.redirect('/login')
            if path in ('/','/dashboard'):
                visible=filtered(c,user,{},limit=100000)
                counts=Counter(a['review_status'] for a in visible)
                money=defaultdict(float)
                for a in visible:money[a['currency']]+=a['total']
                actions='<a class="btn btn-primary" href="/invoices/new">＋ Registrar factura</a>' if user['role']!='contador' else '<a class="btn btn-primary" href="/accounting">Ver contabilidad</a>'
                title='Panel general' if user['role']=='admin' else ('Mi escritorio' if user['role']=='miembro' else 'Panel contable')
                items=[('Comprobantes',len(visible),'▤','Total de documentos'),('Pendientes',counts['Pendiente'],'◷','Esperando revisión'),('Aprobadas',counts['Aprobada'],'✓','Validadas'),('Observadas',counts['Observada'],'!','Requieren atención')]
                blocks=cards(items);latest=visible[:8]
                totals=''.join(f'<div class="money-card"><small>Facturación · {e(curr)}</small><strong>{CURRENCIES[curr]} {total:,.2f}</strong></div>' for curr,total in sorted(money.items())) or '<div class="money-card"><small>Facturación</small><strong>Sin movimientos</strong></div>'
                monthly=defaultdict(float)
                for a in visible:
                    if a['currency']=='PEN':monthly[a['issued_on'][:7]]+=a['total']
                mm=sorted(monthly.items())[-6:];mx=max([v for _,v in mm] or [1]);chart=''.join(f'<div class="bar-item"><small>{e(k)}</small><div class="bar-bg"><div class="bar-fill" style="width:{max(1,round(v/mx*100))}%"></div></div><span>S/ {v:,.0f}</span></div>' for k,v in mm) or '<p class="hint">Los gráficos se mostrarán al registrar facturas.</p>'
                body=titlebar(title,'Resumen actualizado del registro documental y revisión de comprobantes.',actions)+blocks+f'<div class="summaryline">{totals}</div><div class="twocol"><section class="panel"><div class="panel-header"><h3>Últimos comprobantes</h3><a class="textlink" href="/invoices">Ver todos ↗</a></div>{invoice_table(latest)}</section><section class="panel"><h3>Evolución en soles</h3><p class="hint">Importes facturados por mes de emisión · PEN</p><div class="barchart">{chart}</div><hr><h3>Estado de revisión</h3><div class="status-stats">{''.join(f'<div><span>{e(s)}</span><strong>{counts[s]}</strong></div>' for s in STATUSES)}</div></section></div>'
                if user['role']=='admin':
                    byperson=defaultdict(lambda: [0,defaultdict(float)])
                    byproject=defaultdict(lambda: [0,defaultdict(float)])
                    for item in visible:
                        byperson[item['owner_name']][0]+=1
                        byperson[item['owner_name']][1][item['currency']]+=item['total']
                        pr=item['project_name'] or 'Sin proyecto'
                        byproject[pr][0]+=1;byproject[pr][1][item['currency']]+=item['total']
                    def ranked(source):
                        return '<div class="rank-list">'+''.join('<div class="rank-row"><div><strong>'+e(label)+'</strong><small>'+str(data[0])+' factura(s)</small></div><span>'+(' · '.join(CURRENCIES[k]+' '+format(v,',.2f') for k,v in sorted(data[1].items())))+'</span></div>' for label,data in sorted(source.items(),key=lambda x:(-x[1][0],x[0]))[:8])+'</div>' if source else '<p class="hint">Sin movimientos registrados.</p>'
                    body+='<div class="twocol"><section class="panel"><h3>Resumen por colaborador</h3>'+ranked(byperson)+'</section><section class="panel"><h3>Gastos por proyecto</h3>'+ranked(byproject)+'</section></div>'
                return self.page(user,sess,title,body,'/dashboard',self._flash(q))
            if path in ('/invoices','/accounting'):
                if path=='/accounting' and user['role']=='miembro':return self.fail('Acceso restringido.',403)
                rows=filtered(c,user,q,limit=1000)
                name='Contabilidad y rendición' if path=='/accounting' else 'Registro de facturas'
                desc='Consulta y descarga información contable organizada.' if path=='/accounting' else 'Documentos registrados y seguimiento de estados.'
                btn='<a class="btn btn-primary" href="/invoices/new">＋ Nueva factura</a>' if user['role']!='contador' and path=='/invoices' else ''
                if path=='/accounting':btn=f'<a class="btn btn-primary" href="/export.xlsx?{urlencode({k:val(q,k) for k in ("q","from","to","status","currency")})}">↓ Descargar Excel</a>'
                body=titlebar(name,desc,btn)+f'<section class="panel"><div class="panel-header"><h3>{len(rows)} resultado(s)</h3><span class="hint">Hasta 1,000 resultados en pantalla; Excel contiene todos los registros filtrados.</span></div>{filter_form(path,q)}{invoice_table(rows)}</section>'
                return self.page(user,sess,name,body,path,self._flash(q))
            if path=='/export.xlsx':
                if user['role'] not in ('admin','contador'):return self.fail('Sin permiso para exportar.',403)
                rows=filtered(c,user,q)
                audit(c,user['id'],'EXPORTAR_EXCEL','report',None,f'{len(rows)} facturas',self.client_address[0]);c.commit()
                blob=excel.workbook(rows)
                return self.response(blob,200,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',{'Content-Disposition':'attachment; filename="ALTIVIA_Facturas_'+date.today().isoformat()+'.xlsx"'})
            if path=='/invoices/new':
                if user['role']=='contador':return self.fail('El contador no puede registrar comprobantes.',403)
                form=upload_widget(c,sess['csrf'])
                if user['role']=='admin':
                    # Existing admin capability: duplicate override is still available.
                    form=form.replace('<div class="form-actions"><button class="btn btn-primary" type="submit">','''<div class="warnbox"><strong>Excepción de duplicado (solo administrador)</strong><label><input type="checkbox" name="override_duplicate" value="yes"> Autorizar duplicado</label><label class="field"><span>Justificación</span><textarea name="override_reason" rows="2"></textarea></label></div><div class="form-actions"><button class="btn btn-primary" type="submit">''')

                return self.page(user,sess,'Registrar factura',titlebar('Registrar factura','Tres formas de registrar un comprobante. Reconocimiento y confirmación de datos.')+form,'/invoices/new')
            m=re.fullmatch(r'/invoices/(\d+)(?:/(file|edit|replace))?',path)
            if m:
                iid=int(m[1]); a=_get_invoice(c,iid,user)
                if not a:return self.fail('No se encontró este comprobante o no tienes permiso.',404)
                if m[2]=='file':
                    pth=pathlib.Path(a['local_path']).resolve()
                    if not pth.is_relative_to(UPLOADS.resolve()) or not pth.is_file():return self.fail('El archivo no está disponible.',404)
                    data=pth.read_bytes();return self.response(data,200,a['mime_type'],{'Content-Disposition':f'inline; filename="{clean_name(a["original_filename"])}"'})
                if m[2]=='replace':
                    if not (user['role']=='admin' or (user['role']=='miembro' and a['review_status']=='Observada')):return self.fail('No puedes reemplazar este documento.',403)
                    body=titlebar(f'Reemplazar respaldo #{iid}','Se conservará el archivo anterior en un archivo histórico privado.')+f'''<section class="panel"><h3>Cargar nueva fotografía o PDF</h3><p>Sube un comprobante legible. El sistema guardará el anterior en una carpeta de archivo, reiniciará la revisión y solicitará nuevamente la sincronización con Drive.</p><form enctype="multipart/form-data" method="post" action="/invoices/{iid}/replace"><input type="hidden" name="csrf" value="{e(sess['csrf'])}"><label class="field"><span>Nuevo archivo JPG / PNG / WEBP / PDF (máximo 15 MB)</span><input required name="file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf"></label><div class="form-actions"><button class="btn btn-primary" type="submit">Reemplazar y enviar a revisión</button><a class="btn btn-secondary" href="/invoices/{iid}">Cancelar</a></div></form></section>'''
                    return self.page(user,sess,'Reemplazar documento',body,'/invoices')
                if m[2]=='edit':
                    if not (user['role']=='admin' or (user['role']=='miembro' and a['review_status']=='Observada')):return self.fail('Esta factura no admite edición con tu rol o estado.',403)
                    form=f'''<section class="panel"><h3>Modificar datos del comprobante</h3><p class="hint">El documento original no se reemplaza desde aquí. Si está ilegible, el administrador debe conservar la trazabilidad de cualquier sustitución.</p><form method="post" action="/invoices/{iid}/edit"><input type="hidden" name="csrf" value="{e(sess['csrf'])}">{invoice_fields(c,values=dict(a))}<div class="form-actions"><button class="btn btn-primary">Guardar correcciones</button><a href="/invoices/{iid}" class="btn btn-secondary">Cancelar</a></div></form></section>'''
                    return self.page(user,sess,'Corregir factura',titlebar(f'Corregir factura #{iid}')+form,'/invoices')
                return self.page(user,sess,'Detalle de factura',invoice_detail(c,a,user,sess['csrf']),'/invoices',self._flash(q))
            if path=='/users':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                users=c.execute('SELECT * FROM users ORDER BY active DESC,full_name').fetchall()
                rows=''.join(f'<tr><td><strong>{e(x["full_name"])}</strong><small>@{e(x["username"])}</small></td><td>{ROLES[x["role"]]}</td><td>{badge("Aprobada" if x["active"] else "Rechazada")}</td><td><form class="inline user-actions" method="post" action="/users/{x["id"]}/update"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><select name="role">{''.join(f"<option value={k} {'selected' if k==x['role'] else ''}>{v}</option>" for k,v in ROLES.items())}</select><input name="new_password" type="password" placeholder="Clave solo admin/contador" minlength="10" autocomplete="new-password"><button class="btn btn-secondary">Actualizar</button></form><form class="inline" method="post" action="/users/{x["id"]}/toggle"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button class="btn btn-ghost" data-confirm="¿Cambiar el acceso de este usuario?">{("Desactivar" if x["active"] else "Activar")}</button></form></td></tr>' for x in users)
                form=f'''<section class="panel"><h3>Crear usuario</h3><p class="hint">Los miembros se registran sin contraseña y aparecen en la lista pública de Registro. Solo administradores y contadores necesitan contraseña.</p><form method="post" action="/users/create"><input type="hidden" name="csrf" value="{e(sess['csrf'])}"><div class="formgrid">{textbox('Nombre completo','full_name',required=True)}{textbox('Usuario','username',required=True,extra='pattern="[a-zA-Z0-9._-]{3,40}"')}{textbox('Contraseña (solo admin/contador)','password',type='password',extra='minlength="10" autocomplete="new-password"')}{dropdown('Rol','role',[(k,v) for k,v in ROLES.items()],'miembro')}</div><button class="btn btn-primary">＋ Crear usuario</button></form></section>'''
                body=titlebar('Administrar usuarios','Crea miembros y contadores. Los miembros usan acceso directo sin contraseña. Administradores y contadores inician sesión con clave segura.')+f'<section class="panel"><h3>Usuarios existentes</h3><div class="table-wrap"><table class="datatable"><thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th><th>Administrar</th></tr></thead><tbody>{rows}</tbody></table></div></section>'+form
                return self.page(user,sess,'Usuarios',body,'/users',self._flash(q))
            if path=='/projects':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                projects=c.execute('SELECT * FROM projects ORDER BY name').fetchall()
                rows=''.join(f'<tr><td>{e(x["name"])}</td><td>{"Activo" if x["active"] else "Inactivo"}</td><td><form method="post" action="/projects/{x["id"]}/toggle"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button class="btn btn-secondary">{("Desactivar" if x["active"] else "Activar")}</button></form></td></tr>' for x in projects)
                body=titlebar('Proyectos','Clasificación interna de gastos por proyecto')+f'<section class="panel"><h3>Agregar proyecto</h3><form method="post" action="/projects/create" class="filterbar"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><input name="name" required maxlength="120" placeholder="Nombre del proyecto"><button class="btn btn-primary">Agregar</button></form></section><section class="panel"><h3>Catálogo de proyectos</h3><div class="table-wrap"><table class="datatable"><thead><tr><th>Nombre</th><th>Estado</th><th>Acción</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
                return self.page(user,sess,'Proyectos',body,'/projects',self._flash(q))
            if path=='/drive':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                connected=drive.TOKEN_PATH.exists();pending=c.execute("SELECT COUNT(*) FROM invoices WHERE drive_file_id IS NULL AND deleted_at IS NULL").fetchone()[0]
                body=titlebar('Integración con Google Drive','Respaldo de archivos por colaborador y por fecha de emisión')+f'''<section class="panel"><h3>Estado de conexión</h3><p>{badge('Sincronizada' if connected else 'Pendiente')}</p><p><strong>Carpeta raíz:</strong> {e(drive.ROOT_ID)}</p><p class="hint">Las facturas se guardan localmente de forma privada y se suben a Drive cuando se conecta la cuenta. No se modifican los comprobantes originales.</p><p><strong>{pending} factura(s) por sincronizar.</strong></p><div class="form-actions"><a class="btn btn-primary" href="/drive/connect">{('Reconectar Google' if connected else 'Conectar Google Drive')}</a><form method="post" action="/drive/sync"><input type="hidden" name="csrf" value="{e(sess['csrf'])}"><button class="btn btn-secondary">↻ Sincronizar pendientes</button></form></div></section><section class="panel"><h3>Configuración inicial</h3><p>Coloca las credenciales OAuth descargadas de Google Cloud en <code>data/google_oauth_client.json</code> y configura el URI de redirección <code>{e(drive.redirect_uri())}</code>.</p><p class="hint">Requiere permiso de acceso a Google Drive. La integración solo se activa con tu autorización expresa y funciona en una cuenta del propietario; revisa la documentación de seguridad.</p></section>'''
                return self.page(user,sess,'Google Drive',body,'/drive',self._flash(q))
            if path=='/drive/connect':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                try:
                    state=secrets.token_urlsafe(26)
                    c.execute('UPDATE sessions SET oauth_state=?,oauth_started=? WHERE token_hash=?',(state,now(),sess['token_hash']));c.commit()
                    return self.redirect(drive.authorization_url(state))
                except Exception as exc:return self.page(user,sess,'Google Drive',_error_page(str(exc)),'/drive')
            if path=='/drive/callback':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                if val(q,'state')!=sess.get('oauth_state') or not sess.get('oauth_state'):return self.fail('Estado OAuth inválido.',403)
                if not sess.get('oauth_started') or datetime.fromisoformat(sess['oauth_started']) < datetime.now(timezone.utc)-timedelta(minutes=10):return self.fail('Autorización vencida.',403)
                c.execute('UPDATE sessions SET oauth_state=NULL,oauth_started=NULL WHERE token_hash=?',(sess['token_hash'],));c.commit()
                if val(q,'error'):return self.fail('Google rechazó autorización: '+val(q,'error'))
                try:drive.exchange_code(val(q,'code'))
                except Exception as exc:return self.fail(str(exc))
                audit(c,user['id'],'DRIVE_CONECTADO','settings');c.commit()
                return self.redirect('/drive?msg=Cuenta+Google+conectada')
            if path=='/audit':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                ev=c.execute('''SELECT a.*,u.full_name FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 250''').fetchall()
                rows=''.join(f'<tr><td>{e(x["created_at"][:19].replace("T"," "))} UTC</td><td>{e(x["full_name"] or "Sistema")}</td><td>{e(x["event"])}</td><td>{e(x["details"])}</td></tr>' for x in ev)
                return self.page(user,sess,'Auditoría',titlebar('Registro de auditoría','Últimos 250 eventos de la plataforma')+f'<section class="panel"><div class="table-wrap"><table class="datatable"><thead><tr><th>Fecha UTC</th><th>Responsable</th><th>Actividad</th><th>Detalles</th></tr></thead><tbody>{rows}</tbody></table></div></section>','/audit')
            return self.fail('Ruta inexistente.',404)
        except Exception as exc:
            traceback.print_exc();return self.fail('Ocurrió un error interno. Consulta la consola del servidor para obtener detalles.',500)
        finally:c.close()
    def page(self,user,sess,title,body,active='',flash=''):
        return self.response(layout(user,title,body,active,flash,sess['csrf'],drive.TOKEN_PATH.exists()))
    def login_page(self,error=''):
        token=secrets.token_urlsafe(28)
        err=f'<div class="login-error">{e(error)}</div>' if error else ''
        body=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Acceso · ALTIVIA</title><link rel="stylesheet" href="/static/style.css"><link rel="icon" href="/static/favicon.svg"></head><body class="loginbody"><div class="login-layout"><section class="login-hero"><div class="hero-brand">A<span>.</span> ALTIVIA</div><div><div class="hero-pill">GESTIÓN DOCUMENTAL INTELIGENTE</div><h1>Tus facturas,<br><em>bajo control.</em></h1><p>Captura, verifica y gestiona cada comprobante en una sola plataforma, con trazabilidad y respaldo documental.</p><div class="hero-stats"><span>01 <small>Registrar</small></span><span>02 <small>Validar</small></span><span>03 <small>Controlar</small></span></div></div><div class="hero-footer">ALTIVIA CONSULTORES SAC · Plataforma privada</div></section><section class="login-panel"><form method="post" action="/login" class="login-card"><div class="login-icon">A<span>.</span></div><h2>Bienvenido de nuevo</h2><p>Acceso reservado al administrador y al contador.</p>{err}<input type="hidden" name="csrf" value="{e(token)}">{textbox('Usuario','username',required=True,extra='autocomplete="username"')}{textbox('Contraseña','password',type='password',required=True,extra='autocomplete="current-password"')}<button class="btn btn-primary btn-block">Iniciar sesión →</button><a class="btn btn-secondary btn-block" href="/registro">📷 Registrar factura sin contraseña</a><div class="login-note">El administrador configura las cuentas. El primer acceso se crea desde <code>INICIAR_ALTIVIA.bat</code>.</div></form></section></div></body></html>'''
        return self.response(body,cookies=[self.cookieheader(GUEST,token,3600)])
    def do_POST(self):
        path=urlparse(self.path).path
        c=db()
        try:
            user,sess=self._auth(c)
            form,files=self._form()
            if form is None:return
            if path=='/login':
                if not self._csrf(form,sess,user):return self.login_page('Formulario vencido. Vuelve a intentarlo.')
                uname=ident(val(form,'username'))[:80];pw=val(form,'password')
                ip=self.client_address[0]
                cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec='seconds')
                failures=c.execute('SELECT COUNT(*) FROM login_attempts WHERE success=0 AND ip=? AND attempted_at>?',(ip,cutoff)).fetchone()[0]
                if failures>=8:return self.login_page('Demasiados intentos fallidos. Espera 15 minutos.')
                found=c.execute('SELECT * FROM users WHERE username=?',(uname,)).fetchone()
                ok=bool(found and found['active'] and found['role'] in ('admin','contador') and verify_password(pw,found['password_hash']))
                c.execute('INSERT INTO login_attempts(username,ip,success,attempted_at) VALUES(?,?,?,?)',(uname,ip,int(ok),now()))
                if not ok:
                    c.commit();return self.login_page('Credenciales incorrectas o usuario desactivado.')
                token=secrets.token_urlsafe(40);th=hashlib.sha256(token.encode()).hexdigest()
                expires=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat(timespec='seconds')
                c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                          (th,found['id'],secrets.token_urlsafe(36),expires))
                audit(c,found['id'],'INICIO_SESION',ip=ip)
                c.commit();return self.redirect('/dashboard',cookies=[self.cookieheader(COOKIE,token),self.cookieheader(GUEST,'',0)])
            public_post=not user and path in ('/api/analyze','/invoices/create')
            if not user and not public_post:return self.fail('Inicia sesión para continuar.',401)
            if not self._csrf(form,sess,user):
                if public_post:return self.response(json.dumps({'error':'Formulario vencido. Vuelve a /registro.'}),403,'application/json') if path=='/api/analyze' else self.fail('Formulario vencido. Vuelve a Registrar factura.',403)
                return self.fail('Token de seguridad caducado. Actualiza la página.',403)
            if public_post:
                # Only registration, no browsing or edits. Throttle anonymous uploads and submissions.
                stage='analyze' if path=='/api/analyze' else 'create'
                cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec='seconds')
                attempts=c.execute('SELECT COUNT(*) FROM public_attempts WHERE ip=? AND stage=? AND created_at>?',(self.client_address[0],stage,cutoff)).fetchone()[0]
                if attempts>=(25 if stage=='analyze' else 12):return self.fail('Demasiados intentos. Espera 15 minutos.',429)
                c.execute('INSERT INTO public_attempts(ip,stage,created_at) VALUES(?,?,?)',(self.client_address[0],stage,now()));c.commit()
            if path=='/logout':
                c.execute('DELETE FROM sessions WHERE token_hash=?',(sess['token_hash'],))
                audit(c,user['id'],'CIERRE_SESION');c.commit()
                return self.redirect('/login',cookies=[self.cookieheader(COOKIE,'',0)])
            if path=='/api/analyze':
                if user and user['role']=='contador':return self.response(json.dumps({'error':'El contador no puede subir facturas.'}),403,'application/json')
                if not user:
                    member_id=val(form,'owner_id')
                    if not member_id.isdigit():return self.response(json.dumps({'error':'Primero selecciona tu nombre.'}),400,'application/json')
                    member=c.execute("SELECT * FROM users WHERE id=? AND role='miembro' AND active=1",(int(member_id),)).fetchone()
                    if not member:return self.response(json.dumps({'error':'Este colaborador no se encuentra habilitado.'}),403,'application/json')
                    owner_id=member['id']
                else:owner_id=user['id']
                file=files.get('file')
                if not file:return self.response(json.dumps({'error':'Selecciona una imagen o un PDF válido.'}),400,'application/json')
                filename,raw=file
                if not raw or len(raw)>MAX_UPLOAD:return self.response(json.dumps({'error':'El archivo debe tener entre 1 byte y 15 MB.'}),400,'application/json')
                ext=pathlib.Path(filename).suffix.lower()
                if raw[:4]==b'%PDF' and ext=='.pdf':mime='application/pdf'
                elif raw[:3]==b'\xff\xd8\xff' and ext in ('.jpg','.jpeg'):mime='image/jpeg'
                elif raw[:8]==b'\x89PNG\r\n\x1a\n' and ext=='.png':mime='image/png'
                elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' and ext=='.webp':mime='image/webp'
                else:return self.response(json.dumps({'error':'Formato no válido o extensión incompatible (PDF, JPG, PNG, WEBP).'}),400,'application/json')
                token=secrets.token_urlsafe(26);file_path=TEMPS/(token+ext)
                file_path.write_bytes(raw)
                data=extract(file_path,mime)
                for key in ('text',):data.pop(key,None)  # no raw extracted personal data in browser state
                c.execute('INSERT INTO uploads_pending(token,owner_id,path,filename,mime_type,extracted_json,created_at) VALUES(?,?,?,?,?,?,?)',
                          (token,owner_id,str(file_path),clean_name(filename),mime,json.dumps(data,ensure_ascii=False),now()))
                c.commit()
                return self.response(json.dumps({'draft_token':token,**data},ensure_ascii=False),200,'application/json')
            if path=='/invoices/create':
                if user and user['role']=='contador':return self.fail('El contador no puede registrar facturas.',403)
                if not user:
                    owner=val(form,'owner_id')
                    if not owner.isdigit():raise ValueError('Selecciona tu nombre antes de subir el archivo.')
                    member=c.execute("SELECT id FROM users WHERE id=? AND role='miembro' AND active=1",(int(owner),)).fetchone()
                    if not member:raise ValueError('Este colaborador está deshabilitado.')
                    owner_id=member['id']
                else:owner_id=user['id']
                token=val(form,'draft_token')
                draft=c.execute('SELECT * FROM uploads_pending WHERE token=? AND owner_id=?',(token,owner_id)).fetchone()
                if not draft or not pathlib.Path(draft['path']).exists():raise ValueError('La carga del documento ha caducado. Vuelve a subirlo.')
                a=parse_invoice(form)
                dupls=_duplicate(c,a)
                seq=0
                if dupls:
                    if not user or user['role']!='admin' or val(form,'override_duplicate')!='yes' or len(val(form,'override_reason'))<8:
                        ids=', '.join(f'#{x["id"]} ({x["full_name"]})' for x in dupls)
                        if not user:raise ValueError('Factura duplicada: el comprobante ya fue registrado. Contacta al administrador si necesitas corregirlo.')
                        raise ValueError('Factura duplicada. Ya existe: '+ids+'. Para una excepción el administrador debe justificarlo.')
                    seq=c.execute('''SELECT COALESCE(MAX(duplicate_sequence),0)+1 FROM invoices WHERE ruc=? AND receipt_type=? AND series=? AND number=? AND deleted_at IS NULL''',
                        (a['ruc'],a['receipt_type'],a['series'],a['number'])).fetchone()[0]
                if a['project_id'] and not c.execute('SELECT id FROM projects WHERE id=? AND active=1',(a['project_id'],)).fetchone():raise ValueError('Proyecto inexistente.')
                us=c.execute('SELECT folder_key,full_name FROM users WHERE id=?',(owner_id,)).fetchone()
                folder=UPLOADS/(clean_name(us['full_name'])+'_'+us['folder_key'])/fd(a['issued_on'])
                folder.mkdir(parents=True,exist_ok=True)
                original=draft['filename'];safe=(a['series']+'-'+a['number']+'_') if a['series'] else 'COMPROBANTE_'
                target=folder/(safe+secrets.token_hex(6)+'_'+clean_name(original))
                shutil.move(draft['path'],target)
                data=json.loads(draft['extracted_json'] or '{}')
                fields=[a[k] for k in ('project_id','receipt_type','series','number','issued_on','due_on','provider','ruc','description','subtotal','igv','total','currency','terms')]
                cur=c.execute('''INSERT INTO invoices(owner_id,project_id,receipt_type,series,number,issued_on,due_on,provider,ruc,description,subtotal,igv,total,currency,terms,
                   duplicate_sequence,local_path,original_filename,mime_type,drive_status,extraction_method,extraction_confidence,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  [owner_id,*fields,seq,str(target),original,draft['mime_type'],'Pendiente',data.get('method',''),
                   ', '.join(data.get('uncertain',[])),now(),now()])
                iid=cur.lastrowid
                c.execute('DELETE FROM uploads_pending WHERE token=?',(token,))
                audit(c,user['id'] if user else None,'FACTURA_REGISTRADA','invoice',iid,'Fecha emisión='+a['issued_on']+(' (registro por lista pública, sin identidad verificada)' if not user else ''),self.client_address[0])
                if seq:audit(c,user['id'],'DUPLICADO_JUSTIFICADO','invoice',iid,val(form,'override_reason'))
                c.commit()
                if drive.TOKEN_PATH.exists():self._attempt_sync(c,iid)
                return self.redirect('/registro/exito' if not user else f'/invoices/{iid}?msg=Factura+registrada+correctamente')
            m=re.fullmatch(r'/invoices/(\d+)/(edit|review|pay|delete|replace)',path)
            if m:
                iid=int(m[1]);op=m[2];a=_get_invoice(c,iid,user)
                if not a:return self.fail('Factura inexistente o acceso restringido.',404)
                if op=='replace':
                    if not (user['role']=='admin' or (user['role']=='miembro' and a['review_status']=='Observada')):return self.fail('Acceso restringido.',403)
                    f=files.get('file')
                    if not f:raise ValueError('Selecciona una imagen o PDF.')
                    filename,raw=f
                    if not raw or len(raw)>MAX_UPLOAD:raise ValueError('El nuevo archivo debe tener menos de 15 MB.')
                    ext=pathlib.Path(filename).suffix.lower()
                    if raw[:4]==b'%PDF' and ext=='.pdf':mime='application/pdf'
                    elif raw[:3]==b'\xff\xd8\xff' and ext in ('.jpg','.jpeg'):mime='image/jpeg'
                    elif raw[:8]==b'\x89PNG\r\n\x1a\n' and ext=='.png':mime='image/png'
                    elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' and ext=='.webp':mime='image/webp'
                    else:raise ValueError('Extensión o contenido no reconocido.')
                    tmp=TEMPS/(secrets.token_hex(12)+ext);tmp.write_bytes(raw)
                    result=extract(tmp,mime)
                    if any('borrosa' in w for w in result.get('warnings',[])) and len(result.get('text','').strip())<40:
                        tmp.unlink(missing_ok=True)
                        raise ValueError('La fotografía parece borrosa y no pudo leerse. Por favor, toma otra foto.')
                    archive=DATA/'archive'/str(iid);archive.mkdir(parents=True,exist_ok=True)
                    old=pathlib.Path(a['local_path'])
                    if not old.resolve().is_relative_to(UPLOADS.resolve()):raise ValueError('Archivo original fuera del almacenamiento autorizado.')
                    old_drive=a['drive_file_id']
                    if old.exists():shutil.move(old,archive/(now().replace(':','-')+'_'+old.name))
                    target=old.parent/(secrets.token_hex(6)+'_'+clean_name(filename));target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.move(tmp,target)
                    c.execute('UPDATE invoices SET local_path=?,original_filename=?,mime_type=?,drive_file_id=NULL,drive_status=?,review_status=?,review_notes=?,extraction_method=?,updated_at=? WHERE id=?',
                      (str(target),clean_name(filename),mime,'Pendiente','Pendiente','Documento reemplazado; requiere nueva revisión',result.get('method',''),now(),iid))
                    audit(c,user['id'],'DOCUMENTO_REEMPLAZADO','invoice',iid,'Drive anterior: '+str(old_drive))
                    c.commit()
                    if drive.TOKEN_PATH.exists():self._attempt_sync(c,iid)
                    return self.redirect(f'/invoices/{iid}?msg=Documento+reemplazado+y+enviado+a+revisi%C3%B3n')
                if op=='edit':
                    if user['role']!='admin' and not (user['role']=='miembro' and a['review_status']=='Observada'):return self.fail('No puedes modificar esta factura.',403)
                    new=parse_invoice(form);dupls=_duplicate(c,new,iid)
                    if dupls:raise ValueError('La corrección coincide con una factura ya registrada. Contacta al administrador.')
                    if new['project_id'] and not c.execute('SELECT id FROM projects WHERE id=? AND active=1',(new['project_id'],)).fetchone():raise ValueError('Proyecto inexistente.')
                    if new['issued_on']!=a['issued_on']:
                        if a['drive_file_id']:raise ValueError('Esta factura ya está respaldada en Drive. Para cambiar su fecha se requiere una migración documental supervisada.')
                        us=c.execute('SELECT folder_key,full_name FROM users WHERE id=?',(a['owner_id'],)).fetchone()
                        new_dir=UPLOADS/(clean_name(us['full_name'])+'_'+us['folder_key'])/fd(new['issued_on']);new_dir.mkdir(parents=True,exist_ok=True)
                        dest=new_dir/pathlib.Path(a['local_path']).name;shutil.move(a['local_path'],dest);new_local=str(dest)
                    else:new_local=a['local_path']
                    fields=list(new.keys())
                    c.execute('UPDATE invoices SET '+','.join(k+'=?' for k in fields)+',local_path=?,updated_at=?,review_status=? WHERE id=?',
                      [*(new[k] for k in fields),new_local,now(),'Pendiente' if user['role']=='miembro' else a['review_status'],iid])
                    audit(c,user['id'],'FACTURA_CORREGIDA','invoice',iid,'Campos editados: '+', '.join(fields));c.commit()
                    return self.redirect(f'/invoices/{iid}?msg=Datos+actualizados')
                if op=='review':
                    if user['role'] not in ('admin','contador'):return self.fail('Acceso restringido.',403)
                    status=val(form,'review_status')
                    if status not in (STATUSES if user['role']=='admin' else ['Observada']):raise ValueError('No tienes permiso para este estado.')
                    notes=val(form,'review_notes')[:1000]
                    c.execute('UPDATE invoices SET review_status=?,review_notes=?,updated_at=? WHERE id=?',(status,notes,now(),iid))
                    audit(c,user['id'],'ESTADO_REVISION','invoice',iid,f'{a["review_status"]} → {status}; {notes}')
                    c.commit();return self.redirect(f'/invoices/{iid}?msg=Revisión+guardada')
                if op=='pay':
                    if user['role']!='admin':return self.fail('Solo el administrador puede registrar pagos.',403)
                    paid_on=require_date(val(form,'paid_on'),'Fecha de pago');v=amount(val(form,'amount'))
                    if v<=0:raise ValueError('El pago debe ser mayor que cero.')
                    if val(form,'currency')!=a['currency']:raise ValueError('Los pagos deben usar la moneda de la factura.')
                    if round(paid_total(c,iid)+v,2)>round(a['total'],2)+0.005:raise ValueError('El abono supera el importe pendiente.')
                    c.execute('INSERT INTO payments(invoice_id,amount,currency,paid_on,method,reference,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',
                              (iid,v,a['currency'],paid_on,val(form,'method')[:80],val(form,'reference')[:100],user['id'],now()))
                    audit(c,user['id'],'PAGO_REGISTRADO','invoice',iid,f'{a["currency"]} {v:.2f} fecha {paid_on}')
                    c.commit();return self.redirect(f'/invoices/{iid}?msg=Pago+registrado')
                if op=='delete':
                    if user['role']!='admin':return self.fail('Acceso restringido.',403)
                    c.execute('UPDATE invoices SET deleted_at=?,updated_at=? WHERE id=?',(now(),now(),iid))
                    audit(c,user['id'],'FACTURA_PAPELERA','invoice',iid,'Se conservan el archivo y la auditoría.')
                    c.commit();return self.redirect('/invoices?msg=Factura+enviada+a+papelera')
            if path=='/users/create':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                name=val(form,'full_name')[:110];uname=ident(val(form,'username'));role=val(form,'role')
                if len(name)<3 or not re.fullmatch('[a-z0-9._-]{3,40}',uname) or role not in ROLES:raise ValueError('Datos de usuario inválidos.')
                pw='SIN_CONTRASENA' if role=='miembro' else hash_password(val(form,'password'))
                uid=c.execute('INSERT INTO users(username,full_name,password_hash,role,folder_key,created_at) VALUES(?,?,?,?,?,?)',
                  (uname,name,pw,role,secrets.token_hex(5),now())).lastrowid
                audit(c,user['id'],'USUARIO_CREADO','user',uid,role);c.commit()
                return self.redirect('/users?msg=Usuario+creado')
            u=re.fullmatch(r'/users/(\d+)/(update|toggle)',path)
            if u:
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                uid=int(u[1]);target=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                if not target:raise ValueError('Usuario inexistente.')
                active_admins=c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if u[2]=='toggle':
                    if target['id']==user['id'] and target['active']:raise ValueError('No puedes desactivar tu propia cuenta.')
                    if target['role']=='admin' and target['active'] and active_admins<=1:raise ValueError('No se puede desactivar al último administrador.')
                    c.execute('UPDATE users SET active=? WHERE id=?',(1-target['active'],uid))
                    c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
                    audit(c,user['id'],'USUARIO_ACTIVADO' if not target['active'] else 'USUARIO_DESACTIVADO','user',uid)
                else:
                    role=val(form,'role')
                    if role not in ROLES:raise ValueError('Rol inválido.')
                    if target['role']=='admin' and role!='admin' and target['active'] and active_admins<=1:raise ValueError('Se requiere otro administrador activo.')
                    if uid==user['id'] and role!='admin':raise ValueError('No puedes quitarte el rol administrador.')
                    pw=val(form,'new_password')
                    if role=='miembro':
                        c.execute('UPDATE users SET role=?,password_hash=? WHERE id=?',(role,'SIN_CONTRASENA',uid))
                    elif pw:
                        c.execute('UPDATE users SET role=?,password_hash=? WHERE id=?',(role,hash_password(pw),uid))
                    elif target['role']=='miembro':
                        raise ValueError('Para convertir a un miembro en administrador o contador, indica una contraseña de al menos 10 caracteres.')
                    else:c.execute('UPDATE users SET role=? WHERE id=?',(role,uid))
                    c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,sess['token_hash']))
                    audit(c,user['id'],'USUARIO_ACTUALIZADO','user',uid,f'Rol={role}; clave renovada={bool(pw)}')
                c.commit();return self.redirect('/users?msg=Usuario+actualizado')
            if path=='/projects/create':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                name=val(form,'name')[:120]
                if len(name)<2:raise ValueError('Ingresa un nombre de proyecto.')
                cur=c.execute('INSERT INTO projects(name,active,created_at) VALUES(?,?,?)',(name,1,now()))
                audit(c,user['id'],'PROYECTO_CREADO','project',cur.lastrowid,name);c.commit();return self.redirect('/projects?msg=Proyecto+creado')
            p=re.fullmatch(r'/projects/(\d+)/toggle',path)
            if p:
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                c.execute('UPDATE projects SET active=1-active WHERE id=?',(int(p[1]),))
                audit(c,user['id'],'PROYECTO_ACTUALIZADO','project',int(p[1]));c.commit();return self.redirect('/projects')
            if path=='/drive/sync':
                if user['role']!='admin':return self.fail('Acceso restringido.',403)
                if not drive.TOKEN_PATH.exists():return self.fail('Primero conecta Google Drive.')
                batch=c.execute('SELECT id FROM invoices WHERE deleted_at IS NULL AND drive_file_id IS NULL ORDER BY id LIMIT 12').fetchall()
                success=0;errors=0
                for x in batch:
                    if self._attempt_sync(c,x['id']):success+=1
                    else:errors+=1
                return self.redirect('/drive?msg='+quote(f'Sincronizadas: {success}. Pendientes con error: {errors}. Repite si hay más facturas.'))
            return self.fail('Ruta inexistente.',404)
        except (ValueError,sqlite3.IntegrityError) as exc:
            return self.fail(str(exc),400)
        except Exception as exc:
            traceback.print_exc();return self.fail('Ocurrió un error interno. Consulta la consola del servidor para obtener detalles.',500)
        finally:c.close()
    def _attempt_sync(self,c,iid):
        r=c.execute('SELECT * FROM invoices WHERE id=? AND deleted_at IS NULL',(iid,)).fetchone()
        if not r:return False
        try:
            drive_id=drive.sync_invoice(c,r)
            c.execute('UPDATE invoices SET drive_file_id=?,drive_status=?,updated_at=? WHERE id=?',(drive_id,'Sincronizada',now(),iid))
            audit(c,None,'RESPALDO_DRIVE','invoice',iid,drive_id)
            c.commit();return True
        except Exception as exc:
            c.execute('UPDATE invoices SET drive_status=? WHERE id=?',('Error',iid))
            audit(c,None,'ERROR_DRIVE','invoice',iid,str(exc)[:250]);c.commit();return False

def serve(host='127.0.0.1',port=8765):
    init_db()
    if not db().execute('SELECT COUNT(*) FROM users').fetchone()[0]:
        raise RuntimeError('No existe administrador. Ejecuta primero launcher.py para crear la cuenta.')
    server=ThreadingHTTPServer((host,port),App)
    print(f'\nALTIVIA Gestión de Facturas · http://localhost:{port}\nCtrl+C para cerrar el servidor.\n',flush=True)
    try:server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:pass
    finally:server.server_close()
