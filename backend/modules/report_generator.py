import os
import uuid
from datetime import datetime

# Директория для отчетов
REPORT_DIR = "/tmp/legal_ai_reports"


class ReportGenerator:
    # Класс для генерации PDF отчетов
    
    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def generate_pdf(self, data: dict) -> str:
        """Генерация PDF отчета из данных анализа."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            from reportlab.platypus import KeepTogether
        except ImportError:
            raise RuntimeError("reportlab not installed. Run: pip install reportlab")

        analysis = data.get("analysis", {})
        filename = data.get("filename", "document")
        analyzed_at = data.get("analyzed_at", datetime.utcnow().isoformat())

        output_path = os.path.join(REPORT_DIR, f"report_{uuid.uuid4().hex}.pdf")

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm
        )

        styles = getSampleStyleSheet()
        story = []

        # Стиль заголовка
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#1a1a2e'), spaceAfter=6)
        h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2d4a8a'), spaceBefore=16, spaceAfter=6)
        body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=4)
        small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, textColor=colors.grey)

        # Заголовок
        story.append(Paragraph("Юридический анализ документа", title_style))
        story.append(Paragraph(f"Документ: {filename}", small_style))
        story.append(Paragraph(f"Дата анализа: {analyzed_at[:10]}", small_style))
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#2d4a8a')))
        story.append(Spacer(1, 12))

        # Краткое описание
        if analysis.get("summary"):
            story.append(Paragraph("Краткое описание", h2_style))
            story.append(Paragraph(analysis["summary"], body_style))
            story.append(Spacer(1, 8))

        # Тип документа и стороны
        if analysis.get("document_type") or analysis.get("parties"):
            story.append(Paragraph("Общие сведения", h2_style))
            if analysis.get("document_type"):
                story.append(Paragraph(f"<b>Тип документа:</b> {analysis['document_type']}", body_style))
            if analysis.get("parties"):
                story.append(Paragraph(f"<b>Стороны:</b> {', '.join(analysis['parties'])}", body_style))
            story.append(Spacer(1, 8))

        # Объяснение простым языком
        if analysis.get("plain_language_summary"):
            story.append(Paragraph("Объяснение простым языком", h2_style))
            story.append(Paragraph(analysis["plain_language_summary"], body_style))
            story.append(Spacer(1, 8))

        # Ключевые условия
        if analysis.get("key_terms"):
            story.append(Paragraph("Ключевые условия", h2_style))
            for term in analysis["key_terms"]:
                story.append(Paragraph(f"<b>[{term.get('category', '')}]</b> {term.get('title', '')}", body_style))
                story.append(Paragraph(term.get("description", ""), ParagraphStyle('indent', parent=body_style, leftIndent=16, textColor=colors.HexColor('#444444'))))
                story.append(Spacer(1, 4))

        # Риски
        if analysis.get("risks"):
            story.append(Paragraph("Риски", h2_style))
            risk_colors = {"high": "#c0392b", "medium": "#e67e22", "low": "#27ae60"}
            risk_labels = {"high": "ВЫСОКИЙ", "medium": "СРЕДНИЙ", "low": "НИЗКИЙ"}
            for risk in analysis["risks"]:
                level = risk.get("level", "medium")
                color = risk_colors.get(level, "#888888")
                label = risk_labels.get(level, "СРЕДНИЙ")
                story.append(Paragraph(
                    f'<font color="{color}"><b>▲ {label}</b></font> — {risk.get("title", "")}',
                    body_style
                ))
                story.append(Paragraph(risk.get("description", ""), ParagraphStyle('risk_desc', parent=body_style, leftIndent=16)))
                if risk.get("recommendation"):
                    story.append(Paragraph(f"<i>Рекомендация: {risk['recommendation']}</i>", ParagraphStyle('rec', parent=body_style, leftIndent=16, textColor=colors.HexColor('#2d4a8a'))))
                story.append(Spacer(1, 6))

        # Футер
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Spacer(1, 6))
        story.append(Paragraph("Сгенерировано юридическим AI-помощником. Не является юридической консультацией.", small_style))

        doc.build(story)
        return output_path
