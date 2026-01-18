from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import cm
from io import BytesIO
from datetime import datetime

def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_date(date_str):
    if not date_str:
        return "-"
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%d/%m/%Y")
    except:
        return date_str

def generate_receipts_pdf(data, filters):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title = Paragraph("<b>Relatório de Recebimentos</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.5*cm))
    
    # Informações do filtro
    info_text = f"""
    <b>Período:</b> {filters.get('period', 'Todos')}<br/>
    <b>Beneficiário:</b> {filters.get('beneficiario', 'Todos')}<br/>
    <b>Tipo:</b> {filters.get('type', 'Todos')}<br/>
    <b>Data de emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}
    """
    info_para = Paragraph(info_text, styles['Normal'])
    elements.append(info_para)
    elements.append(Spacer(1, 0.5*cm))
    
    # KPIs
    kpis = data.get('kpis', {})
    kpi_data = [
        ['Total Recebido', format_currency(kpis.get('total_received', 0))],
        ['Beneficiário 31', format_currency(kpis.get('total_31', 0))],
        ['Beneficiário 14', format_currency(kpis.get('total_14', 0))],
        ['Parcelas', format_currency(kpis.get('total_parcelas', 0))],
        ['Alvarás', format_currency(kpis.get('total_alvaras', 0))],
        ['Casos com Recebimentos', str(kpis.get('cases_with_receipts', 0))],
    ]
    
    kpi_table = Table(kpi_data, colWidths=[8*cm, 8*cm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 0.8*cm))
    
    # Tabela de recebimentos
    elements.append(Paragraph("<b>Recebimentos Detalhados</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.3*cm))
    
    receipts = data.get('receipts', [])
    if receipts:
        table_data = [['Data', 'Devedor', 'Tipo', 'Valor', 'Benef.']]
        
        for receipt in receipts[:50]:  # Limitar a 50 linhas
            table_data.append([
                format_date(receipt.get('date', '')),
                receipt.get('debtor', '')[:20],
                receipt.get('type', ''),
                format_currency(receipt.get('value', 0)),
                receipt.get('beneficiario', '-')
            ])
        
        receipt_table = Table(table_data, colWidths=[2.5*cm, 5*cm, 3*cm, 3*cm, 2*cm])
        receipt_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        elements.append(receipt_table)
    else:
        elements.append(Paragraph("Nenhum recebimento encontrado no período.", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer
