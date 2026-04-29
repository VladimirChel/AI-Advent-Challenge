from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any

import requests

from app.config import AppConfig
from app.onec_models import PrintFormRequest, PrintFormResult


DEFAULT_SOURCE = "1c_http_service"
ALLOWED_OUTPUT_FORMATS = {"pdf", "html", "raw"}


class OneCPrintFormsError(RuntimeError):
    def __init__(self, error_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


@dataclass(slots=True)
class OneCPreparedRequest:
    document_type_1c: str
    print_form_1c: str | None
    payload: dict[str, Any]


class OneCPrintFormClient:
    def __init__(self, config: AppConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def fetch_print_form(self, request: PrintFormRequest) -> PrintFormResult:
        self._validate_request(request)
        prepared = self._prepare_request(request)
        headers = self._build_headers()

        try:
            response = self.session.post(
                self.config.onec_print_service_url,
                json=prepared.payload,
                headers=headers,
                timeout=self.config.onec_print_service_timeout_seconds,
            )
        except requests.Timeout as exc:
            raise OneCPrintFormsError("upstream_timeout", "Timed out while requesting 1C print form.") from exc
        except requests.RequestException as exc:
            raise OneCPrintFormsError("upstream_unavailable", f"1C print service request failed: {exc}") from exc

        if response.status_code >= 400:
            raise self._build_http_error(response, request)

        filename: str | None = None
        mime_type: str | None = None
        content_bytes: bytes | None = None
        content_base64: str | None = None

        if self._looks_like_json(response):
            payload = self._parse_json_response(response)
            success = payload.get("success", True)
            if not success:
                raise OneCPrintFormsError(
                    str(payload.get("errorCode", "unexpected_response")),
                    str(payload.get("message", "1C service returned an unsuccessful response.")),
                    {"response": payload},
                )
            mime_type = self._read_json_string(payload, "mimeType") or self._guess_mime_type(request.output_format)
            filename = self._read_json_string(payload, "fileName") or self._build_default_filename(
                request.document_type,
                request.document_number,
                mime_type,
            )
            content_base64 = self._read_json_string(payload, "contentBase64")
            if content_base64:
                try:
                    content_bytes = base64.b64decode(content_base64, validate=True)
                except ValueError as exc:
                    raise OneCPrintFormsError(
                        "unexpected_response",
                        "1C service returned invalid base64 content.",
                        {"filename": filename},
                    ) from exc
            else:
                raw_content = self._read_json_string(payload, "content")
                if raw_content is not None:
                    content_bytes = raw_content.encode("utf-8")
                    content_base64 = base64.b64encode(content_bytes).decode("ascii")
        else:
            content_bytes = response.content
            mime_type = self._normalize_mime_type(response.headers.get("Content-Type")) or self._guess_mime_type(request.output_format)
            filename = self._extract_filename(response.headers.get("Content-Disposition")) or self._build_default_filename(
                request.document_type,
                request.document_number,
                mime_type,
            )
            content_base64 = base64.b64encode(content_bytes).decode("ascii")

        if not content_bytes:
            raise OneCPrintFormsError(
                "unexpected_response",
                "1C print service returned an empty body.",
                {"document_type": request.document_type, "document_number": request.document_number},
            )

        saved_path: str | None = None
        if request.save_to_file:
            target = self._save_file(filename, content_bytes)
            saved_path = str(target)
            content_base64 = None

        return PrintFormResult(
            ok=True,
            document_type=request.document_type,
            document_number=request.document_number,
            print_form=request.print_form,
            mime_type=mime_type,
            filename=filename,
            content_base64=content_base64,
            saved_path=saved_path,
            source=DEFAULT_SOURCE,
        )

    def _validate_request(self, request: PrintFormRequest) -> None:
        if not self.config.onec_print_service_url.strip():
            raise OneCPrintFormsError("validation_error", "ONEC_PRINT_SERVICE_URL is not configured.")
        if not request.document_type:
            raise OneCPrintFormsError("validation_error", "document_type is required.")
        if not request.document_number:
            raise OneCPrintFormsError("validation_error", "document_number is required.")
        if request.output_format not in ALLOWED_OUTPUT_FORMATS:
            raise OneCPrintFormsError(
                "validation_error",
                f"Unsupported output_format: {request.output_format}",
                {"allowed_output_formats": sorted(ALLOWED_OUTPUT_FORMATS)},
            )
        if self.config.onec_print_allowed_document_types and request.document_type not in self.config.onec_print_allowed_document_types:
            raise OneCPrintFormsError(
                "unsupported_document_type",
                f"Unsupported document_type: {request.document_type}",
                {"allowed_document_types": list(self.config.onec_print_allowed_document_types)},
            )

    def _prepare_request(self, request: PrintFormRequest) -> OneCPreparedRequest:
        document_type_1c = self._map_document_type(request.document_type)
        print_form_1c = self._map_print_form(request.document_type, request.print_form)
        payload = {
            "documentType": document_type_1c,
            "documentNumber": request.document_number,
            "format": request.output_format,
        }
        if request.document_date:
            payload["documentDate"] = request.document_date
        if request.organization:
            payload["organization"] = request.organization
        if print_form_1c:
            payload["printForm"] = print_form_1c
        return OneCPreparedRequest(document_type_1c=document_type_1c, print_form_1c=print_form_1c, payload=payload)

    def _map_document_type(self, document_type: str) -> str:
        mapping = self.config.onec_document_type_map
        mapped = mapping.get(document_type, document_type)
        if not isinstance(mapped, str):
            raise OneCPrintFormsError(
                "validation_error",
                f"ONEC_DOCUMENT_TYPE_MAP contains a non-string value for {document_type}.",
            )
        return mapped

    def _map_print_form(self, document_type: str, print_form: str | None) -> str | None:
        if not print_form:
            return None
        mapping = self.config.onec_print_form_map
        raw_mapping = mapping.get(document_type)
        if raw_mapping is None:
            return print_form
        if not isinstance(raw_mapping, dict):
            raise OneCPrintFormsError(
                "validation_error",
                f"ONEC_PRINT_FORM_MAP contains a non-object value for {document_type}.",
            )
        mapped = raw_mapping.get(print_form)
        if mapped is None:
            raise OneCPrintFormsError(
                "unsupported_print_form",
                f"Unsupported print_form {print_form} for document_type {document_type}.",
                {"allowed_print_forms": sorted(str(key) for key in raw_mapping.keys())},
            )
        if not isinstance(mapped, str):
            raise OneCPrintFormsError(
                "validation_error",
                f"ONEC_PRINT_FORM_MAP contains a non-string value for {document_type}.{print_form}.",
            )
        return mapped

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, application/pdf, text/html", "Content-Type": "application/json"}
        auth_type = self.config.onec_print_service_auth_type.strip().lower()
        if auth_type == "basic" and self.config.onec_print_service_username:
            token = f"{self.config.onec_print_service_username}:{self.config.onec_print_service_password}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(token).decode('ascii')}"
        elif auth_type in {"bearer", "token"} and self.config.onec_print_service_token:
            prefix = "Bearer" if auth_type == "bearer" else "Token"
            headers["Authorization"] = f"{prefix} {self.config.onec_print_service_token}"
        return headers

    def _build_http_error(self, response: requests.Response, request: PrintFormRequest) -> OneCPrintFormsError:
        status_map = {
            400: "validation_error",
            401: "authentication_failed",
            403: "authentication_failed",
            404: "document_not_found",
            409: "multiple_documents_found",
            422: "print_form_not_available",
            503: "upstream_unavailable",
        }
        error_code = status_map.get(response.status_code, "upstream_error")
        message = f"1C print service returned HTTP {response.status_code}."
        details: dict[str, Any] = {
            "status_code": response.status_code,
            "document_type": request.document_type,
            "document_number": request.document_number,
        }
        if self._looks_like_json(response):
            try:
                payload = self._parse_json_response(response)
            except OneCPrintFormsError:
                payload = None
            if isinstance(payload, dict):
                details["response"] = payload
                message = str(payload.get("message") or payload.get("error") or message)
                if payload.get("errorCode"):
                    error_code = str(payload["errorCode"])
        return OneCPrintFormsError(error_code, message, details)

    def _parse_json_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OneCPrintFormsError("unexpected_response", "1C service returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise OneCPrintFormsError("unexpected_response", "1C service returned a JSON value instead of an object.")
        return payload

    def _looks_like_json(self, response: requests.Response) -> bool:
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type.lower():
            return True
        body = response.content.lstrip()
        return body.startswith(b"{") or body.startswith(b"[")

    def _save_file(self, filename: str | None, content_bytes: bytes) -> Path:
        safe_filename = self._sanitize_filename(filename or "print_form.bin")
        target = self.config.onec_print_forms_dir / safe_filename
        target.write_bytes(content_bytes)
        return target

    def _guess_mime_type(self, output_format: str) -> str:
        return {
            "pdf": "application/pdf",
            "html": "text/html; charset=utf-8",
        }.get(output_format, "application/octet-stream")

    def _build_default_filename(self, document_type: str, document_number: str, mime_type: str | None) -> str:
        extension = mimetypes.guess_extension((mime_type or "").split(";", 1)[0].strip()) or ".bin"
        return self._sanitize_filename(f"{document_type}_{document_number}{extension}")

    def _extract_filename(self, content_disposition: str | None) -> str | None:
        if not content_disposition:
            return None
        message = Message()
        message["content-disposition"] = content_disposition
        filename = message.get_param("filename", header="content-disposition")
        if not filename:
            return None
        return self._sanitize_filename(filename)

    def _sanitize_filename(self, filename: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", filename).strip().strip(".")
        return sanitized or "print_form.bin"

    def _normalize_mime_type(self, content_type: str | None) -> str | None:
        if not content_type:
            return None
        return content_type.strip()

    def _read_json_string(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise OneCPrintFormsError("unexpected_response", f"1C service returned non-string field {key}.")
        return value
