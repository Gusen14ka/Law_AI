import os
import re
from fastapi import HTTPException


class DocumentParser:
    # Класс для извлечения и очистки текста из документов PDF и DOCX
    
    def extract_text(self, file_path: str, filename: str) -> str:
        """Извлечение и очистка текста из PDF или DOCX файла."""
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == ".pdf":
            text = self._extract_pdf(file_path)
        elif ext == ".docx":
            text = self._extract_docx(file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format.")
        
        return self._clean_text(text)

    def _extract_pdf(self, path: str) -> str:
        """Извлечение текста из PDF с использованием PyPDF2."""
        try:
            import PyPDF2
            import PyPDF2.errors
        except ImportError:
            raise HTTPException(status_code=500, detail="PyPDF2 not installed. Run: pip install PyPDF2")
        
        text_parts = []
        try:
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                if len(reader.pages) == 0:
                    raise HTTPException(status_code=422, detail="PDF has no pages.")
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
        except PyPDF2.errors.PdfReadError as e:
            raise HTTPException(status_code=422, detail=f"Cannot read PDF: {str(e)}")
        
        return "\n".join(text_parts)

    def _extract_docx(self, path: str) -> str:
        """Извлечение текста из DOCX с использованием python-docx."""
        try:
            from docx import Document
        except ImportError:
            raise HTTPException(status_code=500, detail="python-docx not installed. Run: pip install python-docx")
        
        try:
            doc = Document(path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            # Также извлечение таблиц
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        paragraphs.append(row_text)
            return "\n".join(paragraphs)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Cannot read DOCX: {str(e)}")

    def _clean_text(self, text: str) -> str:
        """Очистка извлеченного текста: удаление мусора, нормализация пробелов."""
        if not text:
            return ""
        
        # Удаление нулевых байтов и управляющих символов (кроме новых строк и табуляций)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Сжатие множественных пробелов
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Сжатие более чем 3 последовательных новых строк
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Удаление строк, состоящих только из пунктуации или цифр (обычные артефакты PDF)
        lines = text.split('\n')
        cleaned = [line for line in lines if len(line.strip()) > 2 or line.strip().isalpha()]
        
        return '\n'.join(cleaned).strip()
