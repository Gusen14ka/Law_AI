import os
import uuid
import aiofiles
from fastapi import UploadFile, HTTPException

# Разрешенные расширения файлов
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
# Максимальный размер файла в МБ
MAX_FILE_SIZE_MB = 10
# Максимальный размер файла в байтах
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
# Директория для временных загрузок
TEMP_DIR = "/tmp/legal_ai_uploads"


class FileHandler:
    # Класс для обработки загрузки файлов
    
    def __init__(self):
        os.makedirs(TEMP_DIR, exist_ok=True)

    async def handle_upload(self, file: UploadFile) -> str:
        """Валидация и сохранение загруженного файла. Возвращает путь к сохраненному файлу."""
        
        # Валидация расширения
        filename = file.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '{ext}'. Only PDF and DOCX are accepted."
            )
        
        # Чтение содержимого
        content = await file.read()
        
        # Валидация размера
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds {MAX_FILE_SIZE_MB}MB limit."
            )
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty.")
        
        # Сохранение с уникальным именем
        unique_name = f"{uuid.uuid4().hex}{ext}"
        save_path = os.path.join(TEMP_DIR, unique_name)
        
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)
        
        return save_path

    def cleanup(self, path: str):
        """Удаление временного файла."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
