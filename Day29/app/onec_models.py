from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PrintFormRequest:
    document_type: str
    document_number: str
    document_date: str | None = None
    organization: str | None = None
    print_form: str | None = None
    output_format: str = "pdf"
    save_to_file: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PrintFormRequest":
        return cls(
            document_type=str(payload.get("document_type", "")).strip(),
            document_number=str(payload.get("document_number", "")).strip(),
            document_date=_normalize_optional_string(payload.get("document_date")),
            organization=_normalize_optional_string(payload.get("organization")),
            print_form=_normalize_optional_string(payload.get("print_form")),
            output_format=str(payload.get("output_format", "pdf")).strip().lower() or "pdf",
            save_to_file=bool(payload.get("save_to_file", False)),
        )


@dataclass(slots=True)
class PrintFormResult:
    ok: bool
    document_type: str
    document_number: str
    print_form: str | None
    mime_type: str | None
    filename: str | None
    content_base64: str | None
    saved_path: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "document_type": self.document_type,
            "document_number": self.document_number,
            "print_form": self.print_form,
            "mime_type": self.mime_type,
            "filename": self.filename,
            "content_base64": self.content_base64,
            "saved_path": self.saved_path,
            "source": self.source,
        }


@dataclass(slots=True)
class PrintFormErrorPayload:
    ok: bool
    error_code: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


@dataclass(slots=True)
class SavedPrintForm:
    path: Path
    filename: str


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
