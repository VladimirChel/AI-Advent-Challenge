"use client";

import { FormEvent, useEffect, useState } from "react";

import { createChat, getModels, getProviderHealth, streamMessage } from "@/lib/api";
import { ModelInfo, ProviderHealth, UiMessage } from "@/lib/types";

import styles from "./chat-shell.module.css";

const initialMessages: UiMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content: "Choose a provider, pick a model, and start the conversation.",
  },
];

export function ChatShell() {
  const [chatId, setChatId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>(initialMessages);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [providerHealth, setProviderHealth] = useState<ProviderHealth[]>([]);
  const [provider, setProvider] = useState("proxyapi");
  const [model, setModel] = useState("gpt-4o-mini");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void Promise.all([getModels(), getProviderHealth()]).then(([availableModels, health]) => {
      setModels(availableModels);
      setProviderHealth(health);
      if (availableModels.length > 0) {
        setProvider(availableModels[0].provider);
        setModel(availableModels[0].id);
      }
    });
  }, []);

  async function ensureChat() {
    if (chatId) {
      return chatId;
    }
    const chat = await createChat({
      title: "New chat",
      selected_provider: provider,
      selected_model: model,
    });
    setChatId(chat.id);
    return chat.id;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = input.trim();
    if (!value || loading) {
      return;
    }

    setLoading(true);
    setInput("");
    const currentChatId = await ensureChat();
    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();

    setMessages((current) => [
      ...current,
      { id: userId, role: "user", content: value },
      { id: assistantId, role: "assistant", content: "", pending: true },
    ]);

    try {
      await streamMessage({
        chatId: currentChatId,
        content: value,
        provider,
        model,
        onToken: (delta) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: `${message.content}${delta}`, pending: true }
                : message,
            ),
          );
        },
        onEnd: () => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, pending: false } : message,
            ),
          );
        },
        onError: (error) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: `Error: ${error}`, pending: false }
                : message,
            ),
          );
        },
      });
    } finally {
      setLoading(false);
    }
  }

  const filteredModels = models.filter((item) => item.provider === provider);

  useEffect(() => {
    if (filteredModels.length > 0 && !filteredModels.some((item) => item.id === model)) {
      setModel(filteredModels[0].id);
    }
  }, [filteredModels, model]);

  return (
    <main className={styles.page}>
      <aside className={styles.sidebar}>
        <p className={styles.eyebrow}>LLM Chat</p>
        <h1 className={styles.title}>One interface for cloud and local models.</h1>
        <p className={styles.copy}>
          This scaffold is wired for ProxyAPI and Ollama with streaming responses, provider
          health, and a backend-first architecture.
        </p>

        <div className={styles.panel}>
          <label className={styles.label}>
            Provider
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {[...new Set(models.map((item) => item.provider))].map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.label}>
            Model
            <select value={model} onChange={(event) => setModel(event.target.value)}>
              {filteredModels.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={styles.panel}>
          <h2 className={styles.sectionTitle}>Provider status</h2>
          {providerHealth.map((item) => (
            <div key={item.provider} className={styles.healthItem}>
              <span>{item.provider}</span>
              <span>{item.status}</span>
            </div>
          ))}
        </div>
      </aside>

      <section className={styles.chatStage}>
        <div className={styles.messageList}>
          {messages.map((message) => (
            <article
              key={message.id}
              className={message.role === "user" ? styles.userBubble : styles.assistantBubble}
            >
              <p className={styles.messageRole}>{message.role}</p>
              <p className={styles.messageContent}>
                {message.content || (message.pending ? "Thinking..." : "")}
              </p>
            </article>
          ))}
        </div>

        <form className={styles.form} onSubmit={onSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask something..."
            rows={4}
          />
          <button type="submit" disabled={loading}>
            {loading ? "Generating..." : "Send"}
          </button>
        </form>
      </section>
    </main>
  );
}

