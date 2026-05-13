import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))


class FileHandler:
    def __init__(self):
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async def handle_upload(self, file: UploadFile) -> tuple[str, int]:
        """Validate and save file. Returns (saved_path, file_size)."""
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат '{ext}'. Только PDF и DOCX."
            )

        content = await file.read()

        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Файл пустой.")
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Файл превышает 15 МБ.")

        file_uuid = uuid.uuid4().hex
        save_path = UPLOAD_DIR / f"{file_uuid}{ext}"

        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)

        return str(save_path), len(content)

    def cleanup(self, path: str):
        """Delete temp file safely."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
