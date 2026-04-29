from __future__ import annotations

from typing import Any, Mapping

from app.config import AppConfig, load_config
from app.onec_models import PrintFormRequest
from app.onec_print_forms import OneCPrintFormClient, OneCPrintFormsError


GET_DOCUMENT_PRINT_FORM_TOOL = {
    "name": "get_document_print_form",
    "description": "Получить печатную форму документа из 1С по типу и номеру документа.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "document_type": {"type": "string", "description": "Внешний тип документа, например sales_invoice."},
            "document_number": {"type": "string", "description": "Номер документа в 1С."},
            "document_date": {"type": "string", "description": "Дата документа в формате YYYY-MM-DD."},
            "organization": {"type": "string", "description": "Организация или другое уточнение для поиска."},
            "print_form": {"type": "string", "description": "Тип печатной формы, например invoice или updk."},
            "output_format": {
                "type": "string",
                "enum": ["pdf", "html", "raw"],
                "description": "Желаемый формат ответа от 1С.",
            },
            "save_to_file": {"type": "boolean", "description": "Сохранить результат в output/print_forms и вернуть путь."},
        },
        "required": ["document_type", "document_number"],
        "additionalProperties": False,
    },
}


def get_mcp_tools() -> list[dict[str, Any]]:
    return [GET_DOCUMENT_PRINT_FORM_TOOL]


def handle_get_document_print_form(
    arguments: Mapping[str, Any],
    *,
    config: AppConfig | None = None,
    client: OneCPrintFormClient | None = None,
) -> dict[str, Any]:
    request = PrintFormRequest.from_dict(dict(arguments))
    if client is None:
        client = OneCPrintFormClient(config or load_config())
    try:
        return client.fetch_print_form(request).to_dict()
    except OneCPrintFormsError as exc:
        return exc.to_dict()


def call_mcp_tool(
    name: str,
    arguments: Mapping[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    if name != GET_DOCUMENT_PRINT_FORM_TOOL["name"]:
        return {
            "ok": False,
            "error_code": "unknown_tool",
            "message": f"Unknown tool: {name}",
            "details": {"available_tools": [GET_DOCUMENT_PRINT_FORM_TOOL["name"]]},
        }
    return handle_get_document_print_form(arguments, config=config)
