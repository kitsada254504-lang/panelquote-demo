"""Session-only PanelQuote demonstration; no credentials or business data."""
from datetime import date, timedelta
from uuid import uuid4
import pandas as pd
import streamlit as st
from quote_excel import export_quote_xlsx, quote_breakdown
from pricing import price_item
from pricing_settings import DEFAULTS

st.set_page_config(page_title='PanelQuote Demo', page_icon='⚡', layout='wide')
st.title('⚡ PanelQuote')
st.caption('ออกแบบต้นทุนตู้ไฟ • จัดรายการ BOM • ทดลองใบเสนอราคา')
st.info('เวอร์ชันสาธิต: อุปกรณ์และราคาทั้งหมดเป็นข้อมูลจำลอง ใช้ทดสอบเท่านั้น ประวัติแยกตามผู้ทดลองและหายเมื่อเริ่มเซสชันใหม่ กรุณาใช้ชื่อลูกค้าสมมติ')

CATALOG = [
    {'sku':'DEMO-MAIN','name':'Main Breaker 250A 3P (ตัวอย่าง)','unit':'ตัว','cost_price':6000,'sell_price':8500},
    {'sku':'DEMO-MCB','name':'MCB 32A 3P (ตัวอย่าง)','unit':'ตัว','cost_price':650,'sell_price':950},
    {'sku':'DEMO-BOX','name':'ตู้เหล็ก 800 × 600 × 250 mm (ตัวอย่าง)','unit':'ตู้','cost_price':3500,'sell_price':None},
    {'sku':'DEMO-BUS','name':'Busbar ทองแดง (ตัวอย่าง)','unit':'ชุด','cost_price':2200,'sell_price':None},
    {'sku':'DEMO-METER','name':'มิเตอร์และ CT (ตัวอย่าง)','unit':'ชุด','cost_price':1800,'sell_price':2600},
    {'sku':'DEMO-WIRE','name':'สายไฟและอุปกรณ์ประกอบ (ตัวอย่าง)','unit':'ชุด','cost_price':1200,'sell_price':None},
]
st.session_state.setdefault('demo_history', [])
quote_tab, catalog_tab, history_tab = st.tabs(['ทำใบเสนอราคา','แคตตาล็อกตัวอย่าง','ประวัติใบเสนอราคา'])
with quote_tab:
    left, right = st.columns(2)
    project = left.text_input('ชื่อโครงการ', 'โครงการตู้ MDB ตัวอย่าง')
    customer = right.text_input('ลูกค้า', 'ลูกค้าทดสอบ')
    quote_date = left.date_input('วันที่', date.today())
    valid_until = right.date_input('ใช้ได้ถึง', date.today() + timedelta(days=30))
    choices = {p['sku']: p for p in CATALOG}
    selected = st.multiselect('เลือกอุปกรณ์', list(choices), default=list(choices), format_func=lambda s: choices[s]['name'])
    with st.expander('ตั้งค่าราคา', expanded=True):
        a,b,c,d = st.columns(4)
        markup = a.number_input('ส่วนเพิ่มจากต้นทุน (%)', min_value=0.0, max_value=200.0, value=25.0)
        labor = b.number_input('ค่าแรง (บาท)', min_value=0.0, value=2500.0)
        shipping = c.number_input('ขนส่ง (บาท)', min_value=0.0, value=500.0)
        discount = d.number_input('ส่วนลด (%)', min_value=0.0, max_value=100.0, value=0.0)
        vat = st.checkbox('คิด VAT 7% สำหรับการทดสอบ', value=True)
    pricing = {**DEFAULTS,'markup_percent':markup,'labor_amount':labor,'labor_marked_up':False,'shipping_amount':shipping,'discount_percent':discount,'vat_enabled':vat}
    rows = []
    for sku in selected:
        part = choices[sku]
        qty = st.number_input(f"จำนวน · {part['name']}", min_value=1, max_value=1000, value=1, key=f'qty_{sku}')
        price = price_item({**part,'price_status':'reference'},markup)
        rows.append({'รหัส':sku,'รายการ':part['name'],'หน่วย':part['unit'],'จำนวน':qty,'ราคาต่อหน่วย':float(price['unit_price']),'ที่มาของราคา':'ราคาขายจำลอง' if price['price_source']=='sell_price' else 'ต้นทุนจำลอง + ส่วนเพิ่ม','price_source':price['price_source'],'price_status':'reference'})
    bom = pd.DataFrame(rows)
    if rows:
        st.dataframe(bom.drop(columns=['price_source','price_status']), hide_index=True, width='stretch')
        _, totals = quote_breakdown(bom, pricing)
        a,b,c = st.columns(3)
        a.metric('ก่อน VAT', f"{totals['before_vat']:,.2f} บาท")
        b.metric('VAT', f"{totals['vat']:,.2f} บาท")
        c.metric('สุทธิ', f"{totals['total']:,.2f} บาท")
    status = st.radio('สถานะเอกสารทดสอบ',['ฉบับร่าง','ฉบับจริงจำลอง'],horizontal=True)
    scope = st.text_area('ขอบเขตงาน','ประกอบตู้ เดินสาย และทดสอบ (ข้อมูลจำลอง)')
    terms = st.text_input('เงื่อนไขการชำระเงิน','สำหรับทดสอบเท่านั้น ไม่มีการรับชำระเงินจริง')
    invalid = not rows or not project.strip() or not customer.strip() or valid_until < quote_date or not scope.strip() or not terms.strip()
    if st.button('บันทึกใบเสนอราคาทดสอบ', type='primary', disabled=invalid):
        quote_id = f'DEMO-{quote_date:%Y%m%d}-{uuid4().hex[:8].upper()}'
        excel = export_quote_xlsx(bom,quote_id,f'[DEMO] {project}',customer,quote_date,status='draft' if status=='ฉบับร่าง' else 'issued',valid_until=valid_until,scope='เอกสารทดสอบเท่านั้น | '+scope,payment_terms=terms,pricing=pricing)
        st.session_state.demo_history.insert(0,{'id':quote_id,'project':project,'customer':customer,'status':status,'items':bom.copy(deep=True),'total':str(totals['total']),'excel':excel})
        st.success('บันทึกแล้ว เปิดแท็บประวัติเพื่อดูรายการและดาวน์โหลด')
    if st.session_state.demo_history:
        newest = st.session_state.demo_history[0]
        st.download_button('ดาวน์โหลด Excel ล่าสุด',newest['excel'],file_name=f"{newest['id']}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='latest_excel')
with catalog_tab:
    st.subheader('อุปกรณ์สำหรับทดลอง')
    st.caption('ตัวเลขสมมติสำหรับทดสอบสูตร ไม่ใช่ราคากลางหรือราคาที่ผู้ขายยืนยัน')
    st.dataframe(pd.DataFrame(CATALOG).rename(columns={'sku':'รหัส','name':'อุปกรณ์','unit':'หน่วย','cost_price':'ต้นทุนจำลอง','sell_price':'ราคาขายจำลอง'}),hide_index=True,width='stretch')
with history_tab:
    st.subheader('ประวัติของคุณในรอบการทดลองนี้')
    if not st.session_state.demo_history:
        st.caption('ยังไม่มีใบเสนอราคา ลองสร้างในแท็บแรก')
    for record in st.session_state.demo_history:
        with st.expander(f"{record['id']} · {record['status']} · {record['project']}"):
            st.write(f"ลูกค้า: {record['customer']} | สุทธิ: {float(record['total']):,.2f} บาท")
            st.dataframe(record['items'].drop(columns=['price_source','price_status']),hide_index=True,width='stretch')
            st.download_button('ดาวน์โหลด Excel',record['excel'],file_name=f"{record['id']}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=record['id'])
