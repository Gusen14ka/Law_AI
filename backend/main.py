from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from modules.file_handler import FileHandler
from modules.document_parser import DocumentParser
from modules.ai_module import AIModule
from modules.response_builder import ResponseBuilder
from modules.report_generator import ReportGenerator

# Создание экземпляра FastAPI приложения с заголовком и версией
app = FastAPI(title="Legal AI Assistant", version="1.0.0")

# Добавление middleware для обработки CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация экземпляров классов для обработки файлов, парсинга документов, AI анализа и т.д.
file_handler = FileHandler()
doc_parser = DocumentParser()
ai_module = AIModule()
response_builder = ResponseBuilder()
report_generator = ReportGenerator()


@app.post("/api/upload")
async def upload_and_analyze(file: UploadFile = File(...)):
    """Загрузка документа и его анализ."""
    
    # 1. Валидация и сохранение файла
    saved_path = await file_handler.handle_upload(file)
    
    # 2. Извлечение текста из документа
    raw_text = doc_parser.extract_text(saved_path, file.filename) # type: ignore
    
    if not raw_text or len(raw_text.strip()) < 50:
        raise HTTPException(status_code=422, detail="Document is empty or too short to analyze.")
    
    # 3. Отправка текста на анализ в AI
    ai_response = await ai_module.analyze(raw_text)
    
    # 4. Парсинг и структурирование ответа AI
    structured = response_builder.parse_ai_response(ai_response)
    
    # 5. Построение финального JSON ответа
    result = response_builder.build_response(
        filename=file.filename, #type: ignore
        text_length=len(raw_text),
        structured=structured
    )
    
    # 6. Очистка временного файла
    file_handler.cleanup(saved_path)
    
    return result


@app.post("/api/report")
async def generate_report(data: dict):
    """Генерация скачиваемого PDF отчета."""
    report_path = report_generator.generate_pdf(data)
    return FileResponse(
        report_path,
        media_type="application/pdf",
        filename="legal_analysis_report.pdf"
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
