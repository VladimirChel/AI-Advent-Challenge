/**
 * Typed SDK contract for LLM Gateway via ProxyAPI.
 * Generated from app.py behavior and the OpenAPI-ready contract.
 */

export type MemoryStrategy =
  | "none"
  | "window"
  | "summary"
  | "retrieval"
  | "hybrid"
  | "facts"
  | "hybrid_facts";

export type ChatRole = "system" | "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ResponseValidationRules {
  min_output_length?: number | null;
  max_output_length?: number | null;
  must_contain?: string[];
  forbid_phrases?: string[];
  require_json?: boolean;
}

export interface LLMRequest {
  model?: string;
  messages: ChatMessage[];
  conversation_id?: string | null;
  branch_id?: string;
  fork_from_branch_id?: string | null;
  fork_from_message_uuid?: string | null;
  use_memory?: boolean;
  memory_strategy?: MemoryStrategy;
  history_limit?: number;
  retrieval_enabled?: boolean;
  retrieval_limit?: number;
  sticky_facts_enabled?: boolean;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  presence_penalty?: number;
  frequency_penalty?: number;
  user_id?: string | null;
  metadata?: Record<string, unknown>;
  validation?: ResponseValidationRules | null;
  stop?: string[] | null;
}

export interface StickyFact {
  key: string;
  value: string;
  source: string;
  last_observed_seq_no?: number | null;
  updated_at?: string | null;
}

export interface LLMResponse {
  request_id: string;
  conversation_id: string;
  branch_id: string;
  created_at: string;
  model: string;
  content: string;
  finish_reason?: string | null;
  latency_ms: number;
  usage: Record<string, unknown>;
  validation: Record<string, unknown>;
  raw_response_id?: string | null;
  context_messages_used: number;
  messages_saved: number;
  summary_used: boolean;
  summary_updated: boolean;
  retrieval_used: boolean;
  retrieval_messages_used: number;
  retrieval_query?: string | null;
  sticky_facts_used: boolean;
  sticky_facts_updated: boolean;
  sticky_facts_count: number;
}

export interface ConversationMessageMeta {
  message_uuid: string;
  role: ChatRole;
  content: string;
  seq_no: number;
  created_at?: string | null;
}

export interface ConversationMessagesResponse {
  conversation_id: string;
  branch_id: string;
  messages: ConversationMessageMeta[];
  count: number;
}

export interface ConversationSummaryResponse {
  conversation_id: string;
  branch_id: string;
  summary?: string | null;
  source_upto_seq_no: number;
  updated_at?: string | null;
  exists: boolean;
}

export interface ConversationFactsResponse {
  conversation_id: string;
  branch_id: string;
  facts: StickyFact[];
  count: number;
}

export interface RefreshFactsResponse extends ConversationFactsResponse {
  updated: boolean;
  upserted: number;
}

export interface RefreshSummaryResponse {
  conversation_id: string;
  branch_id: string;
  updated: boolean;
  summary?: string | null;
  source_upto_seq_no: number;
  updated_at?: string | null;
}

export interface BranchInfo {
  branch_id: string;
  messages_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BranchListResponse {
  conversation_id: string;
  branches: BranchInfo[];
  count: number;
}

export interface BranchCreateResponse {
  conversation_id: string;
  branch_id: string;
  source_branch_id: string;
  fork_from_message_uuid: string;
  created: boolean;
  copied_messages: number;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  base_url: string;
  default_model: string;
  database: "ok" | "error";
  database_error?: string | null;
  retrieval_enabled_by_default: boolean;
  time: string;
}

export interface ModelListItem {
  id?: string | null;
  created?: number | null;
  object?: string | null;
  owned_by?: string | null;
  [key: string]: unknown;
}

export interface ModelListResponse {
  data: ModelListItem[];
}

export interface LLMGatewayClientOptions {
  baseUrl: string;
  headers?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

export class LLMGatewayClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly fetchImpl: typeof fetch;

  constructor(options: LLMGatewayClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.headers = {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    };
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        ...this.headers,
        ...(init?.headers ?? {}),
      },
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    return (await response.json()) as T;
  }

  health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health", { method: "GET" });
  }

  generate(payload: LLMRequest): Promise<LLMResponse> {
    return this.request<LLMResponse>("/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  getConversationMessages(
    conversationId: string,
    params?: { branch_id?: string; limit?: number }
  ): Promise<ConversationMessagesResponse> {
    const search = new URLSearchParams();
    if (params?.branch_id) search.set("branch_id", params.branch_id);
    if (params?.limit !== undefined) search.set("limit", String(params.limit));
    const qs = search.toString() ? `?${search.toString()}` : "";
    return this.request<ConversationMessagesResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/messages${qs}`,
      { method: "GET" }
    );
  }

  getConversationSummary(
    conversationId: string,
    params?: { branch_id?: string }
  ): Promise<ConversationSummaryResponse> {
    const search = new URLSearchParams();
    if (params?.branch_id) search.set("branch_id", params.branch_id);
    const qs = search.toString() ? `?${search.toString()}` : "";
    return this.request<ConversationSummaryResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/summary${qs}`,
      { method: "GET" }
    );
  }

  refreshConversationSummary(
    conversationId: string,
    params?: { branch_id?: string; model?: string; user_id?: string | null }
  ): Promise<RefreshSummaryResponse> {
    const search = new URLSearchParams();
    if (params?.branch_id) search.set("branch_id", params.branch_id);
    if (params?.model) search.set("model", params.model);
    if (params?.user_id) search.set("user_id", params.user_id);
    const qs = search.toString() ? `?${search.toString()}` : "";
    return this.request<RefreshSummaryResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/summary/refresh${qs}`,
      { method: "POST" }
    );
  }

  getConversationFacts(
    conversationId: string,
    params?: { branch_id?: string }
  ): Promise<ConversationFactsResponse> {
    const search = new URLSearchParams();
    if (params?.branch_id) search.set("branch_id", params.branch_id);
    const qs = search.toString() ? `?${search.toString()}` : "";
    return this.request<ConversationFactsResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/facts${qs}`,
      { method: "GET" }
    );
  }

  refreshConversationFacts(
    conversationId: string,
    params?: { branch_id?: string; model?: string; user_id?: string | null }
  ): Promise<RefreshFactsResponse> {
    const search = new URLSearchParams();
    if (params?.branch_id) search.set("branch_id", params.branch_id);
    if (params?.model) search.set("model", params.model);
    if (params?.user_id) search.set("user_id", params.user_id);
    const qs = search.toString() ? `?${search.toString()}` : "";
    return this.request<RefreshFactsResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/facts/refresh${qs}`,
      { method: "POST" }
    );
  }

  listConversationBranches(conversationId: string): Promise<BranchListResponse> {
    return this.request<BranchListResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/branches`,
      { method: "GET" }
    );
  }

  createConversationBranch(
    conversationId: string,
    params: { branch_id: string; fork_from_message_uuid: string; source_branch_id?: string }
  ): Promise<BranchCreateResponse> {
    const search = new URLSearchParams();
    search.set("branch_id", params.branch_id);
    search.set("fork_from_message_uuid", params.fork_from_message_uuid);
    if (params.source_branch_id) search.set("source_branch_id", params.source_branch_id);
    return this.request<BranchCreateResponse>(
      `/conversations/${encodeURIComponent(conversationId)}/branches?${search.toString()}`,
      { method: "POST" }
    );
  }

  listModels(): Promise<ModelListResponse> {
    return this.request<ModelListResponse>("/models", { method: "GET" });
  }
}
