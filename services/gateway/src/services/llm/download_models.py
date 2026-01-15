"""Download data models."""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DownloadStatus(str, Enum):
    """Download status enum."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Download:
    """Represents a download task."""
    id: str
    repo_id: str
    filename: str
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0  # 0-100
    bytes_downloaded: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0  # bytes per second
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": round(self.progress, 1),
            "bytes_downloaded": self.bytes_downloaded,
            "total_bytes": self.total_bytes,
            "speed_bps": round(self.speed_bps, 0),
            "speed_mbps": round(self.speed_bps / 1024 / 1024, 2),
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "model_path": self.model_path,
            "eta_seconds": self._calculate_eta(),
        }
    
    def _calculate_eta(self) -> Optional[int]:
        """Calculate estimated time remaining in seconds."""
        if self.speed_bps <= 0 or self.total_bytes <= 0:
            return None
        remaining_bytes = self.total_bytes - self.bytes_downloaded
        if remaining_bytes <= 0:
            return 0
        return int(remaining_bytes / self.speed_bps)

