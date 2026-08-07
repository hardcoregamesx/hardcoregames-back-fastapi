import os
from pathlib import Path

from fastapi import UploadFile

# Directory where invoice files are persisted. Mounted from a host volume
# in production so files survive container restarts/recreation.
INVOICES_DIR = Path(os.getenv("INVOICES_DIR", "/data/invoices"))


class LocalStorageError(RuntimeError):
    """Raised when an invoice file could not be saved to local disk."""


async def upload_invoice_file(file: UploadFile, object_name: str) -> str:
    """Save an invoice file to local disk.

    Returns the relative path (servable under /invoices/<object_name> once
    the app mounts INVOICES_DIR as static files) suitable for persisting as
    file_path in the database.
    """

    try:
        dest = INVOICES_DIR / object_name
        dest.parent.mkdir(parents=True, exist_ok=True)

        file_bytes = await file.read()
        dest.write_bytes(file_bytes)
    except Exception as exc:
        raise LocalStorageError(f"Could not save invoice file locally: {exc}") from exc

    return f"invoices/{object_name}"
