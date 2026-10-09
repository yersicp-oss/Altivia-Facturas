"""Optional AI-assisted extraction using a separately billed API, explicitly opt-in.
No document data leaves the machine unless OPENAI_VISION_ENABLED=1 and OPENAI_API_KEY is set.
"""
import os,json,base64,urllib.request,urllib.error
from pathlib import Path
from .ocr import normal_date,_money
FIELDS=('receipt_type','series','number','issued_on','due_on','provider','ruc','description','subtotal','igv','total','currency','terms')
PROMPT='''Analiza este comprobante peruano. Devuelve SOLO objeto JSON con claves exactas:
receipt_type,series,number,issued_on,due_on,provider,ruc,description,subtotal,igv,total,currency,terms.
- Las fechas: YYYY-MM-DD; currency: PEN o USD.
- Los montos son números como texto decimal, sin símbolos.
- Si no es legible/no figura, usa "" (cadena vacía): NO inventes datos ni calcules impuestos.
- Extrae el RUC del EMISOR/PROVEEDOR, no del cliente cuando sea distinguible.
- series y number separados, preserva ceros iniciales.
- descripcion: frase corta fiel al documento.
- Si no hay certeza usa "". No uses datos de otras fuentes.'''

def extract_vision(path,mime):
    if os.getenv('OPENAI_VISION_ENABLED','0')!='1':return {},''
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key:raise RuntimeError('IA habilitada, pero falta OPENAI_API_KEY.')
    imgs=[]
    if mime=='application/pdf':
        try:
            import fitz
            with fitz.open(str(path)) as doc:
                for i in range(min(len(doc),3)):
                    page=doc[i]
                    pix=page.get_pixmap(matrix=fitz.Matrix(1.45,1.45))
                    imgs.append(('image/png',pix.tobytes('png')))
        except ImportError:raise RuntimeError('Para analizar PDF con IA instala PyMuPDF.')
    else:imgs=[(mime,Path(path).read_bytes())]
    content=[{'type':'text','text':PROMPT}]
    content += [{'type':'image_url','image_url':{'url':'data:'+mt+';base64,'+base64.b64encode(binary).decode(), 'detail':'high'}} for mt,binary in imgs]
    payload={'model':os.getenv('OPENAI_VISION_MODEL','gpt-4.1-mini'),'temperature':0,
             'response_format':{'type':'json_object'},'messages':[{'role':'user','content':content}],'max_tokens':1200}
    request=urllib.request.Request('https://api.openai.com/v1/chat/completions',json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=55) as response:data=json.load(response)
    except urllib.error.HTTPError as exc:raise RuntimeError('Servicio de IA HTTP '+str(exc.code)) from exc
    output=json.loads(data['choices'][0]['message']['content'])
    ret={}
    for k in FIELDS:
        v=output.get(k)
        if v is None:continue
        v=str(v).strip()[:350]
        if not v:continue
        if k in ('issued_on','due_on'):
            if not normal_date(v):continue
            v=normal_date(v)
        if k in ('subtotal','igv','total'):
            value=_money(v)
            if value is None or value<0:continue
            v=f'{value:.2f}'
        if k=='currency' and v not in ('PEN','USD'):continue
        if k=='ruc' and (not v.isdigit() or len(v)!=11):continue
        ret[k]=v
    return ret,'OpenAI Vision (revisión humana obligatoria)'
