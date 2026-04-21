export type Chat = {
  id: string;
  title: string;
  selected_provider: string;
  selected_model: string;
  created_at: string;
  updated_at: string;
};

export type ModelInfo = {
  id: string;
  display_name: string;
  provider: string;
  source_type: string;
  context_window: number | null;
  supports_streaming: boolean;
  supports_tools: boolean;
  is_active: boolean;
};

export type ProviderHealth = {
  provider: string;
  status: string;
  latency_ms: number;
  details: string;
};

export type UiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
};
