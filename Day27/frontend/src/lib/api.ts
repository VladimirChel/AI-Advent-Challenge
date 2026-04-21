import { Chat, ModelInfo, ProviderHealth } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function createChat(payload: {
  title?: string;
  selected_provider: string;
  selected_model: string;
}): Promise<Chat> {
  return request<Chat>("/chats", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getModels(): Promise<ModelInfo[]> {
  const response = await request<{ items: ModelInfo[] }>("/models");
  return response.items;
}

export async function getProviderHealth(): Promise<ProviderHealth[]> {
  const response = await request<{ items: ProviderHealth[] }>("/providers/health");
  return response.items;
}

export async function streamMessage(params: {
  chatId: string;
  content: string;
  provider: string;
  model: string;
  onToken: (delta: string) => void;
  onEnd: () => void;
  onError: (error: string) => void;
}): Promise<void> {
  const response = await fetch(`${API_BASE}/chats/${params.chatId}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: params.content,
      provider: params.provider,
      model: params.model,
      settings: {
        temperature: 0.7,
        max_tokens: 1024,
        system_prompt: "",
      },
    }),
  });

  if (!response.ok || !response.body) {
    params.onError(`Unable to connect: ${response.status}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const eventLine = part.split("\n").find((line) => line.startsWith("event: "));
      const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
      if (!eventLine || !dataLine) {
        continue;
      }
      const event = eventLine.replace("event: ", "").trim();
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(dataLine.replace("data: ", ""));
      } catch (error) {
        params.onError("Invalid SSE payload from server");
        return;
      }

      if (event === "token") {
        params.onToken(String(payload.delta ?? ""));
      }
      if (event === "end") {
        params.onEnd();
      }
      if (event === "error") {
        params.onError(String(payload.message ?? "Unknown streaming error"));
        return;
      }
    }
  }

  params.onEnd();
}
