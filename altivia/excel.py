"""Small self-contained Excel Open XML exporter. Excel-readable .xlsx with filters and summaries.
No third-party spreadsheet dependencies are needed on Windows.
"""
import io,zipfile,collections,datetime,decimal
from xml.sax.saxutils import escape

HEADERS=['ID','Fecha de emisión','Fecha registro','Tipo','Serie','Número','RUC','Proveedor','Descripción',
 'Base imponible','IGV','Importe total','Moneda','Proyecto','Responsable','Revisión','Pago','Pagado',
 'Fecha vencimiento','Condición de pago','Sincronización','Enlace Drive']

def _letters(n):
    s=''
    while n:n,x=divmod(n-1,26);s=chr(65+x)+s
    return s

def _xmltext(s):
    return escape(str(s),{'"':'&quot;',"'":'&apos;'})

def _cell(v,r,c,style=0,formula=None):
    ref=f'{_letters(c)}{r}';style_attr=f' s="{style}"' if style else ''
    if formula is not None:return f'<c r="{ref}"{style_attr}><f>{_xmltext(formula.lstrip("="))}</f></c>'
    if v is None:return ''
    if isinstance(v,(int,float,decimal.Decimal)) and not isinstance(v,bool):
        return f'<c r="{ref}"{style_attr}><v>{v}</v></c>'
    s=str(v)
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{_xmltext(s)}</t></is></c>'

def _sheet(headers, rows, money_cols=(), date_cols=(), title='', formulas=None):
    xml=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
         '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
         '<sheetFormatPr defaultRowHeight="17"/>','<cols>']
    for c,h in enumerate(headers,1):
        w=min(39,max(13,len(str(h))+4))
        if h in ('Descripción','Proveedor','Enlace Drive'):w=34
        xml.append(f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>')
    xml+=['</cols>','<sheetData>']
    xml.append('<row r="1" ht="25" customHeight="1">'+''.join(_cell(h,1,c,1) for c,h in enumerate(headers,1))+'</row>')
    for idx,row in enumerate(rows,2):
        cells=[]
        for c,v in enumerate(row,1):
            if isinstance(v,dict) and 'formula' in v:cells.append(_cell(None,idx,c,3,formula=v['formula']))
            else:cells.append(_cell(v,idx,c,4 if c in date_cols and v is not None else (3 if c in money_cols and v is not None else (2 if idx%2==0 else 0))))
        xml.append(f'<row r="{idx}">'+''.join(cells)+'</row>')
    xml.append('</sheetData>')
    end=max(1,len(rows)+1)
    xml.append(f'<autoFilter ref="A1:{_letters(len(headers))}{end}"/>')
    xml.append(f'<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>')
    xml.append('</worksheet>');return ''.join(xml).encode('utf-8')

def workbook(invoices):
    """invoices list of mapping/dict; records should be filtered before calling."""
    data=[];by_month=collections.defaultdict(lambda:[0,0.0]);by_vendor=collections.defaultdict(lambda:[0,0.0]);by_project=collections.defaultdict(lambda:[0,0.0]);by_status=collections.defaultdict(lambda:[0,0.0]);
    def serial(v):
        try:return (datetime.date.fromisoformat(v[:10])-datetime.date(1899,12,30)).days if v else None
        except (ValueError,TypeError):return None
    for x in invoices:
        d=dict(x);total=float(d.get('total') or 0); moneda=d.get('currency') or 'PEN'
        issued=d.get('issued_on') or ''; reg=d.get('created_at','')[:10]
        val=lambda k:float(d.get(k) or 0)
        data.append([d['id'],serial(issued),serial(reg),d.get('receipt_type'),d.get('series'),d.get('number'),d.get('ruc'),
            d.get('provider'),d.get('description'),(val('subtotal') if val('subtotal') or val('igv') else None),(val('igv') if val('subtotal') or val('igv') else None),total,moneda,d.get('project_name') or '',d.get('owner_name') or '',
            d.get('review_status'),d.get('payment_status') or '',val('paid'),serial(d.get('due_on') or ''),d.get('terms'),
            d.get('drive_status'),'https://drive.google.com/file/d/'+d['drive_file_id']+'/view' if d.get('drive_file_id') else ''])
        for key,field in [((issued[:7],moneda),by_month),((d.get('provider') or 'Sin proveedor',moneda),by_vendor),
                         ((d.get('project_name') or 'Sin proyecto',moneda),by_project),((d.get('review_status') or '',moneda),by_status)]:
            field[key][0]+=1;field[key][1]+=total
    def agg(items,first):return [[x[0][0],x[0][1],x[1][0],round(x[1][1],2)] for x in sorted(items.items(),key=lambda i:(i[0][1],-i[1][1],i[0][0]))]
    sheets=[('Detalle',HEADERS,data,(10,11,12,18)),('Resumen mensual',['Mes','Moneda','Comprobantes','Total'],agg(by_month,'Mes'),(4,)),
        ('Proveedores',['Proveedor','Moneda','Comprobantes','Total'],agg(by_vendor,'Proveedor'),(4,)),
        ('Proyectos',['Proyecto','Moneda','Comprobantes','Total'],agg(by_project,'Proyecto'),(4,)),
        ('Estados',['Estado de revisión','Moneda','Comprobantes','Total'],agg(by_status,'Estado'),(4,)),
        ('Totales por moneda',['Moneda','Comprobantes','Importe facturado','Importe pagado','Pendiente'],
          [[cur,{'formula':f'COUNTIF(Detalle!$M$2:$M$10000,A{i})'},
                 {'formula':f'SUMIF(Detalle!$M$2:$M$10000,A{i},Detalle!$L$2:$L$10000)'},
                 {'formula':f'SUMIF(Detalle!$M$2:$M$10000,A{i},Detalle!$R$2:$R$10000)'},
                 {'formula':f'C{i}-D{i}'}] for i,cur in enumerate(('PEN','USD'),2)],(3,4,5))]
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        paths=[]
        for i,(name,heads,rows,money) in enumerate(sheets,1):
            paths.append(f'xl/worksheets/sheet{i}.xml')
            z.writestr(paths[-1],_sheet(heads,rows,money,(2,3,19) if name=='Detalle' else ()))
        types=['<?xml version="1.0" encoding="UTF-8"?>',
           '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
           '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
           '<Default Extension="xml" ContentType="application/xml"/>',
           '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
           '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        types += [f'<Override PartName="/{p}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for p in paths]
        z.writestr('[Content_Types].xml',''.join(types)+'</Types>')
        z.writestr('_rels/.rels','''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        wb='<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        wb+=''.join(f'<sheet name="{_xmltext(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,*_) in enumerate(sheets,1))+'</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
        z.writestr('xl/workbook.xml',wb)
        rel='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        rel+=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))
        rel+=f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
        z.writestr('xl/_rels/workbook.xml.rels',rel)
        z.writestr('xl/styles.xml','''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="dd-mm-yyyy"/></numFmts><fonts count="2"><font><sz val="10"/><name val="Aptos"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF15345C"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>''')
    return b.getvalue()
