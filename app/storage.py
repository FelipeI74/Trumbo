import os
from pathlib import Path
from typing import Optional


class SecurityError(Exception):
    """Excepción para intentos de Path Traversal u operaciones no permitidas."""
    pass


class StoryboardStorage:
    """
    Gestor de almacenamiento de imágenes en disco local sin dependencias externas.
    Asigna y resuelve imágenes mediante 'storage_key' con protección de Path Traversal.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.join(os.getcwd(), "data", "projects")
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_key: str) -> Path:
        clean_key = storage_key.lstrip("/\\")
        target_path = (self.base_dir / clean_key).resolve()

        if not str(target_path).startswith(str(self.base_dir)):
            raise SecurityError(f"Intento de Path Traversal detectado: {storage_key}")

        return target_path

    def save_image(self, storage_key: str, data: bytes) -> str:
        file_path = self._resolve_safe_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(data)

        return storage_key

    def read_image(self, storage_key: str) -> bytes:
        file_path = self._resolve_safe_path(storage_key)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Asset no encontrado: {storage_key}")

        with open(file_path, "rb") as f:
            return f.read()

    def delete_image(self, storage_key: str) -> bool:
        if not storage_key:
            return False

        file_path = self._resolve_safe_path(storage_key)
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            return True
        return False