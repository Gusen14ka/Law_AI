import os
import uuid
from datetime import datetime

REPORT_DIR = "/tmp/legal_ai_reports"


class ReportGenerator:
    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def generate_pdf(self, data: dict, request_meta: dict = None) -> str: # type: ignore
        """Generate a PDF report from analysis data. Returns path to file."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        except ImportError:
            raise RuntimeError("reportlab не установлен. Запустите: pip install reportlab")

        analysis = data.get("analysis") or data  # support both formats
        filename = (request_meta or {}).get("filename", "document")
        analyzed_at = (request_meta or {}).get("analyzed_at", datetime.utcnow().isoformat())
        lawyer = (request_meta or {}).get("lawyer", None)

        output_path = os.path.join(REPORT_DIR, f"report_{uuid.uuid4().hex}.pdf")
        doc = SimpleDocTemplate(output_path, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        gold = colors.HexColor('#c9a84c')
        dark_blue = colors.HexColor('#2d4a8a')
        red = colors.HexColor('#e05c5c')
        orange = colors.HexColor('#e08a3c')
        green = colors.HexColor('#4cae7e')
        purple = colors.HexColor('#7c6af7')
        grey = colors.HexColor('#888888')

        title_s = ParagraphStyle('T', parent=styles['Title'], fontSize=22, textColor=gold, spaceAfter=6)
        h2_s = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, textColor=dark_blue, spaceBefore=16, spaceAfter=6)
        body_s = ParagraphStyle('B', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=4)
        small_s = ParagraphStyle('S', parent=styles['Normal'], fontSize=8, textColor=grey)
        indent_s = ParagraphStyle('I', parent=body_s, leftIndent=16, textColor=colors.HexColor('#555555'))

        story = []
        story.append(Paragraph("⚖ Lex Analytica — Юридический анализ", title_s))
        story.append(Paragraph(f"Документ: {filename}", small_s))
        story.append(Paragraph(f"Дата анализа: {analyzed_at[:10]}", small_s))
        if lawyer:
            story.append(Paragraph(f"Проверил юрист: {lawyer}", small_s))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1, color=gold))
        story.append(Spacer(1, 12))

        if analysis.get("document_type"):
            story.append(Paragraph(f"<b>Тип документа:</b> {analysis['document_type']}", body_s))
        if analysis.get("parties"):
            story.append(Paragraph(f"<b>Стороны:</b> {', '.join(analysis['parties'])}", body_s))
        story.append(Spacer(1, 8))

        if analysis.get("summary"):
            story.append(Paragraph("Краткое описание", h2_s))
            story.append(Paragraph(analysis["summary"], body_s))

        if analysis.get("plain_language_summary"):
            story.append(Paragraph("Объяснение простым языком", h2_s))
            story.append(Paragraph(analysis["plain_language_summary"], body_s))

        if analysis.get("lawyer_comment"):
            story.append(Paragraph("Комментарий юриста", h2_s))
            story.append(Paragraph(analysis["lawyer_comment"], body_s))

        if analysis.get("risks"):
            story.append(Paragraph("Выявленные риски", h2_s))
            level_colors = {"high": red, "medium": orange, "low": green}
            level_labels = {"high": "ВЫСОКИЙ", "medium": "СРЕДНИЙ", "low": "НИЗКИЙ"}
            for risk in analysis["risks"]:
                level = risk.get("level", "medium")
                c = level_colors.get(level, grey)
                lbl = level_labels.get(level, "СРЕДНИЙ")
                story.append(Paragraph(f'<font color="#{c.hexval()[1:]}"><b>[{lbl}]</b></font> {risk.get("title", "")}', body_s))
                story.append(Paragraph(risk.get("description", ""), indent_s))
                if risk.get("recommendation"):
                    story.append(Paragraph(f"<i>→ {risk['recommendation']}</i>",
                        ParagraphStyle('rec', parent=indent_s, textColor=purple)))
                story.append(Spacer(1, 4))

        if analysis.get("key_terms"):
            story.append(Paragraph("Ключевые условия", h2_s))
            for term in analysis["key_terms"]:
                story.append(Paragraph(f"<b>[{term.get('category', '')}]</b> {term.get('title', '')}", body_s))
                story.append(Paragraph(term.get("description", ""), indent_s))
                story.append(Spacer(1, 4))

        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=grey))
        story.append(Spacer(1, 6))
        story.append(Paragraph("Сформировано Lex Analytica. Не является официальной юридической консультацией.", small_s))

        doc.build(story)
        return output_path