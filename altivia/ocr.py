"""OCR local para comprobantes peruanos: PDFs digitales y fotografías.
Los valores extraídos son propuestas de lectura: requieren confirmación humana.
"""
import os, re, shutil
from functools import lru_cache
from pathlib import Path
from datetime import datetime

TARGET_FIELDS=('receipt_type','series','number','issued_on','provider','ruc','total')

def _money(s):
    s=re.sub(r'[^0-9,.-]','',str(s).strip())
    if not s:return None
    if ',' in s and '.' in s:
        s=s.replace(',','') if s.rfind('.')>s.rfind(',') else s.replace('.','').replace(',','.')
    elif ',' in s:
        s=s.replace(',','.') if len(s.split(',')[-1])==2 else s.replace(',','')
    try:return round(float(s),2)
    except ValueError:return None

def normal_date(s):
    s=str(s).strip().replace('.','/').replace('-','/')
    for fmt in ('%d/%m/%Y','%Y/%m/%d','%d/%m/%y'):
        try:return datetime.strptime(s,fmt).date().isoformat()
        except ValueError:pass
    return ''

def parse_text(text):
    raw=(text or '').replace('\r','\n')
    lines=[re.sub(r'\s+',' ',line).strip() for line in raw.splitlines() if line.strip()]
    u=raw.upper()
    ret={'receipt_type':'','series':'','number':'','issued_on':'','provider':'','ruc':'',
         'subtotal':'','igv':'','total':'','currency':'PEN','description':'','due_on':'','terms':''}
    if 'NOTA DE CR' in u:ret['receipt_type']='Nota de crédito'
    elif 'BOLETA' in u:ret['receipt_type']='Boleta'
    elif 'FACTURA' in u:ret['receipt_type']='Factura'
    elif re.search(r'F\d{3}\s*[-–]\s*\d+',u):ret['receipt_type']='Factura'
    # Incluye saltos, espacios, punto y guiones usados en comprobantes escaneados.
    match=re.search(r'\b([FBE][A-Z0-9]{3})\s*[-–—\s]\s*(\d{1,12})\b',u)
    if match:
        series,number=match.groups()
        # OCR confunde frecuentemente la letra O con el dígito 0 en series F001.
        fixed=series[0]+series[1:].replace('O','0')
        ret['series']=fixed if fixed[1:].isdigit() else series
        ret['number']=number
    else:
        match=re.search(r'(?:SERIE\s*[:#]?\s*)([FBE][A-Z0-9]{3}).{0,40}?(?:N[°ºO.]?\s*|NUMERO\s*[:#]?\s*)(\d{1,12})',u,re.S)
        if match:ret['series'],ret['number']=match.groups()
    # Prefiere el RUC asociado al emisor, habitualmente ubicado en el encabezado.
    for line in lines[:25]:
        if re.search(r'\bR\s*\.?\s*U\s*\.?\s*C\b',line,re.I):
            match=re.search(r'(?<!\d)(\d{11})(?!\d)',line)
            if match:ret['ruc']=match.group(1);break
    if not ret['ruc']:
        all_rucs=re.findall(r'(?<!\d)(\d{11})(?!\d)',raw)
        if all_rucs:ret['ruc']=all_rucs[0]
    # Priorizar FECHA DE EMISIÓN sobre la de vencimiento y la de impresión.
    date_pattern=r'(?<!\d)(?:\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})(?!\d)'
    date_candidates=[]
    for i,line in enumerate(lines):
        if re.search(r'FECHA\s*(?:DE\s*)?EMISI[OÓ]N|F\.\s*EMISI[OÓ]N|FECHA\s*EMITIDA',line,re.I):
            date_candidates.append(line)
            if i+1<len(lines):date_candidates.append(lines[i+1])
    for line in date_candidates+lines:
        dates=re.findall(date_pattern,line)
        if dates:
            norm=normal_date(dates[0])
            if norm:ret['issued_on']=norm;break
    # Proveedor = emisor, no el cliente. Evitar usar "adquirente" y cabeceras genéricas.
    bad=re.compile(r'^(CLIENTE|ADQUIRIENTE|RECEPTOR|DIRECCI[OÓ]N|DOCUMENTO|FACTURA|BOLETA|RUC|FECHA|TELEFONO|TEL[ÉE]FONO|COMPROBANTE|SE[ÑN]OR)',re.I)
    for i,line in enumerate(lines[:23]):
        m=re.search(r'^(?:RAZ[OÓ]N\s+SOCIAL|PROVEEDOR|EMISOR)\s*[:\-]\s*(.+)$',line,re.I)
        if m:
            candidate=m.group(1).strip()
            if len(candidate)>3 and not bad.match(candidate):ret['provider']=candidate[:180];break
    if not ret['provider']:
        corp=re.compile(r'\b(?:S\s*\.?A\s*\.?C\.?|S\s*\.?A\.?|E\s*\.?I\s*\.?R\s*\.?L\.?|S\s*\.?R\s*\.?L\.?|SAC|EIRL|SRL|LIMITADA)\b',re.I)
        rucline=next((i for i,x in enumerate(lines[:15]) if ret['ruc'] and ret['ruc'] in x),None)
        # Busca cerca del RUC, típicamente donde está el nombre del emisor.
        indices=list(range(max(0,(rucline or 0)-6),min(len(lines), (rucline or 0)+6))) if rucline is not None else []
        indices+=list(range(min(len(lines),14)))
        for idx in dict.fromkeys(indices):
            candidate=lines[idx]
            if 5<len(candidate)<181 and corp.search(candidate) and not bad.match(candidate) and not re.search(r'CLIENTE|ADQUIRIENTE',candidate,re.I):
                ret['provider']=candidate[:180];break
    if not ret['provider']:
        # Último recurso: encabezado inmediato antes del RUC, si parece razón social.
        for i,line in enumerate(lines[:11]):
            if ret['ruc'] in line and i>=1:
                candidate=lines[i-1]
                if len(candidate)>5 and not bad.match(candidate) and not re.search(r'\d{8,}',candidate):ret['provider']=candidate[:180]
                break
    def find_total(patterns):
        for pattern in patterns:
            for line in reversed(lines):
                if not re.search(pattern,line,re.I):continue
                # El importe se sitúa normalmente al final de la línea.
                matches=re.findall(r'(?:S/\s*|US\$\s*|USD\s*|\$\s*)?\d{1,3}(?:[,.]\d{3})*[,.]\d{2}|\d+[,.]\d{2}|\b\d+\b',line)
                for candidate in reversed(matches):
                    money=_money(candidate)
                    if money is not None and money>=0:return money
        return None
    amounts={'subtotal':find_total([r'BASE\s+IMPONIBLE',r'SUB\s*TOTAL',r'VALOR\s+DE\s+VENTA']),
             'igv':find_total([r'\bIGV\b']),
             'total':find_total([r'IMPORTE\s+TOTAL',r'TOTAL\s+A\s+PAGAR',r'MONTO\s+TOTAL',r'TOTAL\s+GENERAL',r'^(?:\s*TOTAL)\s*[:S/$\d]'])}
    for k,v in amounts.items():
        if v is not None:ret[k]=f'{v:.2f}'
    if re.search(r'US\$|USD|D[OÓ]LARES|DOLAR\s+AMERICANO',u):ret['currency']='USD'
    if re.search(r'\bCR[EÉ]DITO\b',u):ret['terms']='Crédito'
    elif re.search(r'\bCONTADO\b',u):ret['terms']='Contado'
    return ret

@lru_cache(maxsize=1)
def ocr_status():
    """Locate executable and usable Tesseract languages on Windows/Linux."""
    cmd=os.getenv('TESSERACT_CMD','').strip()
    if not cmd:
        cmd=shutil.which('tesseract') or ''
    if not cmd and os.name=='nt':
        for base in (os.getenv('ProgramFiles',''),os.getenv('ProgramFiles(x86)',''),os.getenv('LOCALAPPDATA','')):
            if not base:continue
            candidate=Path(base)/'Tesseract-OCR'/'tesseract.exe'
            if candidate.is_file():cmd=str(candidate);break
    if not cmd:return False,'','No se encontró Tesseract. Ejecuta INSTALAR_OCR.bat una sola vez.'
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd=cmd
        pytesseract.get_tesseract_version()
        langs=set(pytesseract.get_languages(config=''))
        pref=os.getenv('TESSERACT_LANG','spa+eng').split('+')
        active=[x for x in pref if x in langs]
        if not active:active=['eng'] if 'eng' in langs else list(langs)[:1]
        if not active:return False,'','Tesseract está instalado, pero no encuentra archivos de idioma.'
        note='' if 'spa' in active else 'Se recomienda instalar idioma español (spa) para mejores resultados.'
        return True,'+'.join(active),note
    except ImportError:
        return False,'','Falta la biblioteca pytesseract. Ejecuta INSTALAR_OCR.bat.'
    except Exception as exc:
        return False,'','No fue posible iniciar Tesseract: '+str(exc)[:140]

def _recognize_image(img,lang):
    """One bounded OCR pass; Render Free has little CPU. Never upscale huge photos."""
    from PIL import Image, ImageOps, ImageEnhance
    import pytesseract
    img=ImageOps.exif_transpose(img).convert('RGB')
    img.thumbnail((1700,1700),Image.Resampling.LANCZOS)
    gray=ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(1.35)
    try:
        return pytesseract.image_to_string(gray,lang=lang,config='--oem 3 --psm 6',timeout=10)
    except RuntimeError:
        return ''


def extract(path,mime):
    result={'fields':{},'text':'','method':'Sin OCR','warnings':[],'uncertain':[]}
    p=Path(path)
    ready,lang,notice=ocr_status()
    text_chunks=[]
    if mime=='application/pdf':
        try:
            import fitz
            with fitz.open(str(p)) as document:
                if len(document)>2:result['warnings'].append('Se analizaron solo las primeras 2 páginas.')
                for index in range(min(2,len(document))):
                    page=document[index]
                    raw=page.get_text('text',sort=True)
                    if len(raw.strip())<30 and ready:
                        from PIL import Image
                        from io import BytesIO
                        pix=page.get_pixmap(matrix=fitz.Matrix(1.45,1.45),alpha=False)
                        raw=_recognize_image(Image.open(BytesIO(pix.tobytes('png'))),lang)
                    text_chunks.append(raw)
                result['method']='PDF digital / OCR local' if ready else 'PDF digital'
        except ImportError:
            result['warnings'].append('Para analizar PDF instala PyMuPDF mediante INSTALAR_OCR.bat.')
        except Exception as exc:
            result['warnings'].append('No se pudo analizar el PDF: '+str(exc)[:120])
        if ready and notice:result['warnings'].append(notice)
        if not ready and not any(len(t.strip())>30 for t in text_chunks):result['warnings'].append(notice)
    else:
        try:
            from PIL import Image
            with Image.open(p) as image:
                image.load();width,height=image.size
                if min(width,height)<650:result['warnings'].append('Fotografía de baja resolución. Acércate y vuelve a tomarla si no se leen los datos.')
                try:
                    import cv2,numpy as np
                    from PIL import ImageOps
                    preview=ImageOps.exif_transpose(image).convert('L')
                    score=cv2.Laplacian(np.array(preview),cv2.CV_64F).var()
                    if score<35:result['warnings'].append('La imagen parece borrosa. Si falta información, toma otra fotografía nítida.')
                except ImportError:pass
                if ready:
                    text_chunks.append(_recognize_image(image,lang));result['method']='Tesseract local ('+lang+')'
                    if notice:result['warnings'].append(notice)
                else:result['warnings'].append(notice)
        except ImportError:
            result['warnings'].append('Falta Pillow para leer imágenes. Ejecuta INSTALAR_OCR.bat.')
        except Exception as exc:
            result['warnings'].append('No se pudo procesar la fotografía: '+str(exc)[:120])
    result['text']='\n'.join(text_chunks)
    result['fields']=parse_text(result['text'])
    # Hybrid: local OCR first; AI is an opt-in fallback, never a second mandatory pass.
    use_ai=os.getenv('OPENAI_VISION_ENABLED','0')=='1'
    core=('series','number','issued_on','provider','ruc','total')
    required_missing=[field for field in core if not result['fields'].get(field)]
    if use_ai and len(required_missing)>=int(os.getenv('ALTIVIA_AI_FALLBACK_MISSING','2')):
        try:
            from .vision import extract_vision
            fields,method=extract_vision(p,mime)
            if fields:
                # Retain OCR values only for keys which the AI did not provide.
                for key,value in fields.items():
                    if value:result['fields'][key]=value
                result['method']='OCR local + '+method if result['text'].strip() else method
                result['warnings'].append('Datos propuestos por IA: confirma los siete campos contra el original.')
        except Exception as exc:
            result['warnings'].append('IA no disponible; puedes completar los datos manualmente: '+str(exc)[:100])
    elif use_ai:
        result['warnings'].append('OCR local suficiente: se omitió la llamada de IA para ahorrar tiempo y costo.')
    for field in TARGET_FIELDS:
        if not result['fields'].get(field):result['uncertain'].append(field)
    if len(result['text'].strip())<30 and not use_ai:
        result['warnings'].append('No se pudieron leer suficientes datos. Revisa que el OCR esté instalado o toma una foto más clara.')
    return result
