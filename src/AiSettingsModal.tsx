import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { AiConnectionTest, AiSettings, AiSettingsInput, ProviderName } from "./types";

type ProviderOption = { id: ProviderName; label: string; description: string; baseUrl: string; models: string[]; keyLabel?: string };
const providers: ProviderOption[] = [
  { id: "openai", label: "OpenAI", description: "Hosted frontier and general-purpose GPT models.", baseUrl: "https://api.openai.com/v1", keyLabel: "OpenAI API key", models: ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-4.1-mini"] },
  { id: "deepseek", label: "DeepSeek", description: "OpenAI-compatible hosted reasoning and fast models.", baseUrl: "https://api.deepseek.com", keyLabel: "DeepSeek API key", models: ["deepseek-flash", "deepseek-v4-pro"] },
  { id: "gemini", label: "Google Gemini", description: "Google's hosted Gemini generation API.", baseUrl: "https://generativelanguage.googleapis.com/v1beta", keyLabel: "Gemini API key", models: ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-pro-preview", "gemini-2.5-flash"] },
  { id: "anthropic", label: "Anthropic Claude", description: "Claude models through Anthropic's Messages API.", baseUrl: "https://api.anthropic.com", keyLabel: "Anthropic API key", models: ["claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"] },
  { id: "ollama", label: "Ollama (local)", description: "Run models locally without a hosted API key.", baseUrl: "http://127.0.0.1:11434", models: ["gemma4", "llama3.3", "qwen3", "deepseek-r1"] },
  { id: "lmstudio", label: "LM Studio (local)", description: "Use models served by LM Studio's local OpenAI-compatible API.", baseUrl: "http://127.0.0.1:1234/v1", keyLabel: "LM Studio API token (optional)", models: ["openai/gpt-oss-20b"] }
];

export function AiSettingsModal({ settings, onClose, onSaved }: { settings: AiSettings; onClose: () => void; onSaved: (settings: AiSettings) => void }) {
  const [form, setForm] = useState<AiSettingsInput>({ provider: settings.provider, model: settings.model, baseUrl: settings.baseUrl, apiKey: "" });
  const [busy, setBusy] = useState<"save" | "test">();
  const [feedback, setFeedback] = useState<AiConnectionTest | { message: string; error: true }>();
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const option = useMemo(() => providers.find(item => item.id === form.provider) || providers[0], [form.provider]);
  const models = useMemo(() => Array.from(new Set([...option.models, ...availableModels, form.model].filter(Boolean))), [availableModels, form.model, option.models]);
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; window.addEventListener("keydown", close); return () => window.removeEventListener("keydown", close); }, [onClose]);
  function chooseProvider(provider: ProviderName) { const next = providers.find(item => item.id === provider)!; setForm({ provider, model: next.models[0], baseUrl: next.baseUrl, apiKey: "" }); setAvailableModels([]); setFeedback(undefined); }
  async function testConnection() { setBusy("test"); setFeedback(undefined); try { const tested = await api.testAiProvider(form); setForm(current => ({ ...current, model: tested.model, baseUrl: tested.baseUrl })); setFeedback(tested); setAvailableModels(tested.availableModels); } catch (error) { setFeedback({ message: error instanceof Error ? error.message : String(error), error: true }); } finally { setBusy(undefined); } }
  async function save(event: FormEvent) { event.preventDefault(); setBusy("save"); setFeedback(undefined); try { const saved = await api.saveAiSettings(form); onSaved(saved); setFeedback({ provider: saved.provider, model: saved.model, baseUrl: saved.baseUrl, message: "Settings saved. New chats will use this provider.", availableModels }); } catch (error) { setFeedback({ message: error instanceof Error ? error.message : String(error), error: true }); } finally { setBusy(undefined); } }
  return <div className="app-modal-backdrop" role="dialog" aria-modal="true" aria-label="AI provider settings">
    <form className="app-modal ai-settings-modal" onSubmit={save}>
      <div className="app-modal-header"><div><p className="eyebrow">AI CONNECTION</p><h2>Provider and model</h2><p>Keys are saved to the local application-data .env file and are never displayed again.</p></div><button type="button" className="icon" onClick={onClose} aria-label="Close AI settings">×</button></div>
      <div className="provider-grid">{providers.map(provider => <button type="button" key={provider.id} className={form.provider === provider.id ? "provider-card active" : "provider-card"} onClick={() => chooseProvider(provider.id)}><strong>{provider.label}</strong><small>{provider.description}</small></button>)}</div>
      <div className="ai-form-grid">
        <label>Model<select value={form.model} onChange={event => setForm({ ...form, model: event.target.value })}>{models.map(model => <option key={model}>{model}</option>)}</select></label>
        <label>Custom model ID<input value={form.model} onChange={event => setForm({ ...form, model: event.target.value })} placeholder="Enter an exact provider model ID" /></label>
        <label className="full">{form.provider === "lmstudio" ? "Detected local server" : "Base URL"}<input value={form.baseUrl} onChange={event => setForm({ ...form, baseUrl: event.target.value })} /></label>
        {form.provider !== "ollama" && <label className="full">{option.keyLabel}<input type="password" autoComplete="new-password" value={form.apiKey || ""} onChange={event => setForm({ ...form, apiKey: event.target.value })} placeholder={form.provider === "lmstudio" ? "Leave blank unless LM Studio authentication is enabled" : settings.provider === form.provider && settings.configured ? "A key is saved — leave blank to keep it" : "Paste API key"} /></label>}
      </div>
      <div className="credential-note"><span>●</span><div><strong>{form.provider === "ollama" || form.provider === "lmstudio" ? "Local connection" : settings.provider === form.provider && settings.configured ? "Saved credential available" : "Credential required"}</strong><small>{form.provider === "ollama" ? "Start Ollama before testing. Installed models will be discovered automatically." : form.provider === "lmstudio" ? "agentSQL detects the local server and starts it when needed. LM Link device names do not need to be entered." : "A blank key keeps the previously saved key for this provider."}</small></div></div>
      {feedback && <div className={`connection-feedback ${"error" in feedback ? "error" : "success"}`}>{feedback.message}{!("error" in feedback) && feedback.availableModels.length > 0 && <small>{feedback.availableModels.length} models discovered</small>}</div>}
      <div className="app-modal-actions"><button type="button" onClick={() => void testConnection()} disabled={!!busy}>{busy === "test" ? "Connecting…" : form.provider === "lmstudio" ? "Connect LM Studio" : "Test connection"}</button><button className="primary" disabled={!!busy}>{busy === "save" ? "Saving…" : "Save settings"}</button></div>
      <small className="config-path">Configuration file: {settings.configPath}</small>
    </form>
  </div>;
}
