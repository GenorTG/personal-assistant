"""File upload routes."""
import logging
from pathlib import Path
from datetime import datetime
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File

from ...config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["files"])


@router.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload file to data/files/ directory."""
    files_dir = settings.data_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    
    filename = file.filename or "uploaded_file"
    filename = Path(filename).name
    safe_filename = "".join(c for c in filename if c.isalnum() or c in ('-', '_', '.')).strip()
    
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    file_path = files_dir / safe_filename
    
    counter = 1
    original_path = file_path
    while file_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        file_path = files_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    
    try:
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        return {
            "status": "success",
            "filename": file_path.name,
            "path": str(file_path.relative_to(settings.base_dir)),
            "size": len(content)
        }
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}") from e


@router.get("/api/files")
async def list_files():
    """List files in data/files/ directory."""
    files_dir = settings.data_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        files = []
        for file_path in files_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"Error listing files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}") from e


@router.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """Delete file from data/files/ directory."""
    files_dir = settings.data_dir / "files"
    
    safe_filename = Path(filename).name
    file_path = files_dir / safe_filename
    
    try:
        file_path.resolve().relative_to(files_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        file_path.unlink()
        return {"status": "success", "message": f"File {filename} deleted"}
    except Exception as e:
        logger.error(f"Error deleting file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}") from e
