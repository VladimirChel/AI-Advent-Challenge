import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import ChatCreate, ChatRead, ChatUpdate
from app.schemas.message import MessageCreate, MessageExchange, StreamEvent
from app.services.chat_service import chat_service
from app.services.message_service import message_service


router = APIRouter(tags=["chats"])


@router.post("/chats", response_model=ChatRead, status_code=201)
async def create_chat(payload: ChatCreate) -> ChatRead:
    return chat_service.create_chat(payload)


@router.get("/chats")
async def list_chats() -> dict[str, object]:
    chats = chat_service.list_chats()
    return {"items": chats, "total": len(chats)}


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str) -> dict[str, object]:
    chat = chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = message_service.list_messages(chat_id)
    return {"chat": chat, "messages": messages}


@router.patch("/chats/{chat_id}", response_model=ChatRead)
async def update_chat(chat_id: str, payload: ChatUpdate) -> ChatRead:
    chat = chat_service.update_chat(chat_id, payload)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(chat_id: str) -> None:
    deleted = chat_service.delete_chat(chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")
    message_service.delete_chat_messages(chat_id)


@router.post("/chats/{chat_id}/messages", response_model=MessageExchange)
async def create_message(chat_id: str, payload: MessageCreate) -> MessageExchange:
    chat = chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return await message_service.create_message_exchange(chat, payload)


@router.post("/chats/{chat_id}/messages/stream")
async def stream_message(chat_id: str, payload: MessageCreate) -> EventSourceResponse:
    chat = chat_service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    async def event_generator():
        try:
            async for event in message_service.stream_message_exchange(chat, payload):
                stream_event = StreamEvent(event=event["event"], data=event["data"])
                yield {
                    "event": stream_event.event,
                    "data": json.dumps(stream_event.data, ensure_ascii=False),
                }
        except HTTPException as exc:
            stream_event = StreamEvent(
                event="error",
                data={"code": "provider_error", "message": str(exc.detail)},
            )
            yield {
                "event": stream_event.event,
                "data": json.dumps(stream_event.data, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
