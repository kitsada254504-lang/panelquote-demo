"""Small dependency-free OOXML exporter with typed values and cached totals."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import re
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile, ZIP_DEFLATED

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
VAT_RATE = Decimal('0.07')


def money(value):
    v = Decimal(str(value))
    if not v.is_finite() or v < 0:
        raise ValueError('Quote amounts must be finite and nonnegative.')
    return v.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def quote_values(bom, pricing=None):
    """คืน (แถว, ยอดก่อน VAT, VAT, สุทธิ) ตามค่าตั้งราคา pricing (None = ค่าตั้งต้น)"""
    rows, totals = quote_breakdown(bom, pricing)
    return rows, totals['before_vat'], totals['vat'], totals['total']


def quote_breakdown(bom, pricing=None):
    from pricing_settings import breakdown
    if bom.empty:
        raise ValueError('Quote requires at least one item.')
    result=[]
    for _, row in bom.iterrows():
        qty=Decimal(str(row['จำนวน']))
        if not qty.is_finite() or qty <= 0:
            raise ValueError('Quantity must be finite and positive.')
        price=money(row['ราคาต่อหน่วย'])
        result.append((row, qty, price, money(qty*price)))
    return result, breakdown(sum((r[3] for r in result), Decimal(0)), pricing)


def export_quote_xlsx(bom, quote_id, project_name, customer, quote_date, *, status='draft', valid_until=None, scope='', payment_terms='', totals_complete=True, pricing=None) -> bytes:
    from pricing_settings import BREAKDOWN_LABELS, vat_label
    rows,totals=quote_breakdown(bom, pricing)
    root=Element('worksheet', xmlns=NS)
    SubElement(SubElement(root,'sheetPr'),'pageSetUpPr',fitToPage='1')
    views=SubElement(root,'sheetViews'); view=SubElement(views,'sheetView',workbookViewId='0')
    SubElement(view,'pane',ySplit='7',topLeftCell='A8',activePane='bottomLeft',state='frozen')
    cols=SubElement(root,'cols')
    for n,width in enumerate([25,48,12,12,19,19,24,18],1):
        SubElement(cols,'col',min=str(n),max=str(n),width=str(width),customWidth='1')
    sheet=SubElement(root,'sheetData')
    def append(n,values,style='0',formulas=None):
        rr=SubElement(sheet,'row',r=str(n),ht='28',customHeight='1')
        for i,v in enumerate(values):
            ref=f'{chr(65+i)}{n}'; numeric=isinstance(v,(Decimal,int,float))
            cell=SubElement(rr,'c',r=ref,s=('2' if numeric else style))
            if numeric:
                if formulas and i in formulas: SubElement(cell,'f').text=formulas[i]
                SubElement(cell,'v').text=str(v)
            else:
                text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(v))[:32767]
                cell.set('t','inlineStr'); SubElement(SubElement(cell,'is'),'t').text=text
    append(1,['PanelQuote | ใบเสนอราคา'], '1')
    append(2,['เลขที่',quote_id]);append(3,['โครงการ',project_name]);append(4,['ลูกค้า',customer]);append(5,['วันที่',quote_date.isoformat()])
    append(6,['ฉบับจริง' if status=='issued' else 'ฉบับร่าง - ตรวจข้อมูลก่อนเสนอขาย'])
    append(7,['รหัส','รายการ','หน่วย','จำนวน','ราคาต่อหน่วย','รวม','ที่มาของราคา','สถานะราคา'], '1')
    for n,(row,qty,price,line) in enumerate(rows,8):
        source={'sell_price':'ราคาขายที่ระบุ','cost_markup':'ต้นทุน + ส่วนเพิ่ม','pending':'รอราคา'}.get(row.get('price_source'),'ไม่ระบุ')
        append(n,[row['รหัส'],row['รายการ'],row['หน่วย'],qty,price,line,source,{'pending':'รอราคา','reference':'ราคาอ้างอิง','confirmed':'ยืนยันแล้ว','expired':'หมดอายุ'}.get(row.get('price_status'),'ราคาอ้างอิง')],formulas={5:f'ROUND(D{n}*E{n},2)'})
    end=7+len(rows)
    n=end+2
    append(n,[BREAKDOWN_LABELS['items'],'','','','',totals['items']], formulas={5:f'SUM(F8:F{end})'})
    for key in ['contingency','labor','shipping','discount']:
        if totals[key]:
            n+=1; append(n,[BREAKDOWN_LABELS[key],'','','','',-totals[key] if key=='discount' else totals[key]])
    append(n+1,['รวมก่อน VAT','','','','',totals['before_vat']])
    append(n+2,[vat_label(pricing),'','','','',totals['vat']])
    append(n+3,['ยอดสุทธิ','','','','',totals['total']], '1')
    append(n+4,['อายุราคา',valid_until.isoformat() if valid_until else 'ยังไม่ระบุ'])
    append(n+5,['ขอบเขตงาน',scope]);append(n+6,['เงื่อนไขชำระเงิน',payment_terms])
    if not totals_complete:append(n+7,['ยอดเฉพาะรายการมีราคา - ยังไม่ใช่ยอดครบถ้วน'])
    SubElement(root,'autoFilter',ref=f'A7:H{end}')
    merges=SubElement(root,'mergeCells',count='1');SubElement(merges,'mergeCell',ref='A1:H1')
    SubElement(root,'pageMargins',left='.3',right='.3',top='.5',bottom='.5',header='.2',footer='.2')
    SubElement(root,'pageSetup',paperSize='9',orientation='landscape',fitToWidth='1',fitToHeight='0')
    styles=f'''<styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Tahoma"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Tahoma"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF136956"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment vertical="center"/></xf><xf fontId="0" fillId="0" borderId="0" xfId="0" numFmtId="4" applyNumberFormat="1"><alignment vertical="center"/></xf></cellXfs></styleSheet>'''
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml',f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ใบเสนอราคา" sheetId="1" r:id="rId1"/></sheets><calcPr fullCalcOnLoad="1"/></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml',styles);archive.writestr('xl/worksheets/sheet1.xml',tostring(root,encoding='utf-8',xml_declaration=True))
    return out.getvalue()
