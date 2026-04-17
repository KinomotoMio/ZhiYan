"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  Info,
  Loader2,
  Settings,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getSettings,
  updateSettings,
  validateApiKey,
  type AppSettings,
  type ModelStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ModelRoleField = "default_model" | "strong_model" | "vision_model" | "fast_model";
type KnownProvider = "openai" | "anthropic" | "google-gla" | "deepseek" | "openrouter";
type DraftProvider = KnownProvider | "custom";
type ApiKeyProvider = "openai" | "anthropic" | "google" | "deepseek" | "openrouter";

interface ProviderKeyDraft {
  draftValue: string;
  maskedValue: string;
  showMasked: boolean;
}

interface ProviderStatus {
  has_openai_key: boolean;
  has_anthropic_key: boolean;
  has_google_key: boolean;
  has_deepseek_key: boolean;
  has_openrouter_key: boolean;
}

interface ModelDraft {
  provider: DraftProvider;
  customProvider: string;
  modelName: string;
}

const API_KEY_FIELDS: Record<
  ApiKeyProvider,
  "openai_api_key" | "anthropic_api_key" | "google_api_key" | "deepseek_api_key" | "openrouter_api_key"
> = {
  openai: "openai_api_key",
  anthropic: "anthropic_api_key",
  google: "google_api_key",
  deepseek: "deepseek_api_key",
  openrouter: "openrouter_api_key",
};

const PROVIDER_CONFIG = [
  { value: "openai", label: "OpenAI", keyFlag: "has_openai_key" as const },
  { value: "anthropic", label: "Anthropic", keyFlag: "has_anthropic_key" as const },
  { value: "google-gla", label: "Google", keyFlag: "has_google_key" as const },
  { value: "deepseek", label: "DeepSeek", keyFlag: "has_deepseek_key" as const },
  { value: "openrouter", label: "OpenRouter", keyFlag: "has_openrouter_key" as const },
] as const;

const MODEL_ROLE_CONFIG = [
  { field: "default_model", label: "默认模型", hint: "主要生成" },
  { field: "strong_model", label: "高级模型", hint: "更高质量" },
  { field: "vision_model", label: "多模态模型", hint: "图片理解" },
  { field: "fast_model", label: "快速模型", hint: "轻量任务" },
] as const;

const MODEL_SUGGESTIONS: Record<KnownProvider, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4o"],
  anthropic: ["claude-sonnet-4-5-20250929"],
  "google-gla": ["gemini-2.0-flash"],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  openrouter: [
    "moonshotai/kimi-k2.5",
    "deepseek/deepseek-chat-v3-0324",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash-001",
    "openai/gpt-4o",
  ],
};

const EMPTY_PROVIDER_STATUS: ProviderStatus = {
  has_openai_key: false,
  has_anthropic_key: false,
  has_google_key: false,
  has_deepseek_key: false,
  has_openrouter_key: false,
};

const EMPTY_MODEL_STATUS: ModelStatus = {
  model: "",
  provider: "",
  ready: false,
  message: "请先配置模型",
};

const EMPTY_MODEL_DRAFTS: Record<ModelRoleField, ModelDraft> = {
  default_model: { provider: "openrouter", customProvider: "", modelName: "moonshotai/kimi-k2.5" },
  strong_model: { provider: "openrouter", customProvider: "", modelName: "moonshotai/kimi-k2.5" },
  vision_model: { provider: "openrouter", customProvider: "", modelName: "moonshotai/kimi-k2.5" },
  fast_model: { provider: "openrouter", customProvider: "", modelName: "deepseek/deepseek-chat-v3-0324" },
};

const EMPTY_PROVIDER_KEY_DRAFTS: Record<ApiKeyProvider, ProviderKeyDraft> = {
  openai: { draftValue: "", maskedValue: "", showMasked: false },
  anthropic: { draftValue: "", maskedValue: "", showMasked: false },
  google: { draftValue: "", maskedValue: "", showMasked: false },
  deepseek: { draftValue: "", maskedValue: "", showMasked: false },
  openrouter: { draftValue: "", maskedValue: "", showMasked: false },
};

function createProviderKeyDraft(maskedValue: string): ProviderKeyDraft {
  return {
    draftValue: "",
    maskedValue,
    showMasked: Boolean(maskedValue),
  };
}

function createProviderKeyDraftsFromSettings(settings: AppSettings): Record<ApiKeyProvider, ProviderKeyDraft> {
  return {
    openai: createProviderKeyDraft(settings.openai_api_key || ""),
    anthropic: createProviderKeyDraft(settings.anthropic_api_key || ""),
    google: createProviderKeyDraft(settings.google_api_key || ""),
    deepseek: createProviderKeyDraft(settings.deepseek_api_key || ""),
    openrouter: createProviderKeyDraft(settings.openrouter_api_key || ""),
  };
}

function clearProviderPlaintextDrafts(
  drafts: Record<ApiKeyProvider, ProviderKeyDraft>
): Record<ApiKeyProvider, ProviderKeyDraft> {
  return {
    openai: { ...drafts.openai, draftValue: "", showMasked: Boolean(drafts.openai.maskedValue) },
    anthropic: { ...drafts.anthropic, draftValue: "", showMasked: Boolean(drafts.anthropic.maskedValue) },
    google: { ...drafts.google, draftValue: "", showMasked: Boolean(drafts.google.maskedValue) },
    deepseek: { ...drafts.deepseek, draftValue: "", showMasked: Boolean(drafts.deepseek.maskedValue) },
    openrouter: { ...drafts.openrouter, draftValue: "", showMasked: Boolean(drafts.openrouter.maskedValue) },
  };
}

function isKnownProvider(value: string): value is KnownProvider {
  return PROVIDER_CONFIG.some((provider) => provider.value === value);
}

function getProviderLabel(value: string): string {
  return PROVIDER_CONFIG.find((provider) => provider.value === value)?.label ?? value;
}

function parseModelDraft(raw: string): ModelDraft {
  const value = raw.trim();
  if (!value) return { provider: "openai", customProvider: "", modelName: "" };
  if (!value.includes(":")) return { provider: "custom", customProvider: "", modelName: value };

  const [providerPart, ...rest] = value.split(":");
  const provider = providerPart.trim();
  const modelName = rest.join(":").trim();
  if (isKnownProvider(provider)) return { provider, customProvider: "", modelName };
  return { provider: "custom", customProvider: provider, modelName };
}

function getDraftProviderValue(draft: ModelDraft): string {
  return draft.provider === "custom" ? draft.customProvider.trim() : draft.provider;
}

function composeModelValue(draft: ModelDraft): string {
  const provider = getDraftProviderValue(draft);
  const modelName = draft.modelName.trim();
  if (!provider) return modelName;
  if (!modelName) return `${provider}:`;
  return `${provider}:${modelName}`;
}

function buildDraftStatus(model: string, providerStatus: ProviderStatus): ModelStatus {
  const value = model.trim();
  if (!value) return { model: "", provider: "", ready: false, message: "还没有设置模型" };
  if (!value.includes(":")) {
    return { model: value, provider: "", ready: true, message: "将按原始模型名尝试调用" };
  }

  const [provider, ...rest] = value.split(":");
  const providerName = provider.trim();
  const modelName = rest.join(":").trim();
  if (!modelName) {
    return { model: value, provider: providerName, ready: false, message: "格式应为 provider:model-name" };
  }
  if (!isKnownProvider(providerName)) {
    return { model: value, provider: providerName, ready: true, message: "自定义 Provider 将在运行时尝试调用" };
  }

  const keyFlag = PROVIDER_CONFIG.find((item) => item.value === providerName)?.keyFlag;
  const hasKey = keyFlag ? providerStatus[keyFlag] : false;
  return {
    model: value,
    provider: providerName,
    ready: hasKey,
    message: hasKey ? "可以直接使用" : `需要先配置 ${getProviderLabel(providerName)} 的 API Key`,
  };
}

function getStatusBadgeClasses(ready: boolean): string {
  return ready
    ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300"
    : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300";
}

interface KeyFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  provider: "openai" | "anthropic" | "google" | "deepseek" | "openrouter" | "minimax";
  baseUrl?: string;
  placeholder?: string;
  configured?: boolean;
  showValidate?: boolean;
}

function KeyField({
  label,
  value,
  onChange,
  provider,
  baseUrl,
  placeholder,
  configured,
  showValidate = true,
}: KeyFieldProps) {
  const [visible, setVisible] = useState(false);
  const [validating, setValidating] = useState(false);
  const [status, setStatus] = useState<"idle" | "valid" | "invalid">("idle");

  const handleValidate = async () => {
    if (!value || value.includes("...")) {
      toast.error("请先输入完整的 API Key");
      return;
    }
    setValidating(true);
    setStatus("idle");
    try {
      const result = await validateApiKey(provider, value, baseUrl);
      setStatus(result.valid ? "valid" : "invalid");
      if (result.valid) toast.success(result.message);
      else toast.error(result.message);
    } catch {
      setStatus("invalid");
      toast.error("验证失败");
    } finally {
      setValidating(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <Label className="text-sm">{label}</Label>
        {configured && !value ? (
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
            已保存
          </span>
        ) : null}
      </div>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            type={visible ? "text" : "password"}
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setStatus("idle");
            }}
            placeholder={!value && configured ? "已配置，输入新值可覆盖" : placeholder || "sk-..."}
            className="h-10 rounded-xl pr-10"
          />
          <button
            type="button"
            onClick={() => setVisible((prev) => !prev)}
            disabled={!value}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 disabled:opacity-50"
            aria-label={visible ? "隐藏 API Key" : "显示 API Key"}
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {showValidate ? (
          <Button
            type="button"
            variant="outline"
            onClick={handleValidate}
            disabled={validating || !value}
            className="h-10 rounded-xl px-3"
          >
            {validating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : status === "valid" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : status === "invalid" ? (
              <AlertTriangle className="h-4 w-4 text-red-600" />
            ) : null}
            验证
          </Button>
        ) : null}
      </div>
    </div>
  );
}

interface SettingsDialogContentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialogContent({ open, onOpenChange }: SettingsDialogContentProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeRole, setActiveRole] = useState<ModelRoleField>("default_model");
  const [providerEditorTab, setProviderEditorTab] = useState<KnownProvider>("openrouter");
  const [providerStatus, setProviderStatus] = useState<ProviderStatus>(EMPTY_PROVIDER_STATUS);
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("https://api.openai.com/v1");
  const [providerKeyDrafts, setProviderKeyDrafts] =
    useState<Record<ApiKeyProvider, ProviderKeyDraft>>(EMPTY_PROVIDER_KEY_DRAFTS);
  const [modelDrafts, setModelDrafts] =
    useState<Record<ModelRoleField, ModelDraft>>(EMPTY_MODEL_DRAFTS);
  const [ttsProvider, setTtsProvider] = useState("minimax");
  const [ttsBaseUrl, setTtsBaseUrl] = useState("https://api.minimaxi.com");
  const [ttsModel, setTtsModel] = useState("speech-2.8-hd");
  const [ttsVoiceId, setTtsVoiceId] = useState("male-qn-qingse");
  const [ttsKeyDraft, setTtsKeyDraft] = useState<ProviderKeyDraft>(createProviderKeyDraft(""));
  const [enableVisionVerification, setEnableVisionVerification] = useState(true);

  const modelValues = useMemo(
    () => ({
      default_model: composeModelValue(modelDrafts.default_model),
      strong_model: composeModelValue(modelDrafts.strong_model),
      vision_model: composeModelValue(modelDrafts.vision_model),
      fast_model: composeModelValue(modelDrafts.fast_model),
    }),
    [modelDrafts]
  );

  const modelStatuses = useMemo(
    () => ({
      default_model: buildDraftStatus(modelValues.default_model, providerStatus),
      strong_model: buildDraftStatus(modelValues.strong_model, providerStatus),
      vision_model: buildDraftStatus(modelValues.vision_model, providerStatus),
      fast_model: buildDraftStatus(modelValues.fast_model || modelValues.default_model, providerStatus),
    }),
    [modelValues, providerStatus]
  );

  const readyModelCount = useMemo(
    () => MODEL_ROLE_CONFIG.filter((role) => modelStatuses[role.field]?.ready).length,
    [modelStatuses]
  );

  const configuredProviderCount = useMemo(
    () => PROVIDER_CONFIG.filter((provider) => providerStatus[provider.keyFlag]).length,
    [providerStatus]
  );

  const activeDraft = modelDrafts[activeRole];
  const activeStatus = modelStatuses[activeRole] || EMPTY_MODEL_STATUS;
  const activeProviderValue = getDraftProviderValue(activeDraft);
  const activeKnownProvider = isKnownProvider(activeProviderValue) ? activeProviderValue : null;
  const activeProviderKeyDraft =
    providerKeyDrafts[
      providerEditorTab === "google-gla" ? "google" : (providerEditorTab as Exclude<KnownProvider, "google-gla"> | "google")
    ];
  const activeProviderConfigured = providerStatus[
    PROVIDER_CONFIG.find((provider) => provider.value === providerEditorTab)?.keyFlag || "has_openai_key"
  ];
  const ttsConfigured = Boolean(ttsKeyDraft.maskedValue || ttsKeyDraft.draftValue);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getSettings()
      .then((settings) => {
        setOpenaiBaseUrl(settings.openai_base_url || "https://api.openai.com/v1");
        setProviderKeyDrafts(createProviderKeyDraftsFromSettings(settings));
        setProviderStatus({
          has_openai_key: settings.has_openai_key,
          has_anthropic_key: settings.has_anthropic_key,
          has_google_key: settings.has_google_key,
          has_deepseek_key: settings.has_deepseek_key,
          has_openrouter_key: settings.has_openrouter_key,
        });
        setModelDrafts({
          default_model: parseModelDraft(settings.default_model),
          strong_model: parseModelDraft(settings.strong_model),
          vision_model: parseModelDraft(settings.vision_model),
          fast_model: parseModelDraft(settings.fast_model),
        });
        setTtsProvider(settings.tts_provider || "minimax");
        setTtsBaseUrl(settings.tts_base_url || "https://api.minimaxi.com");
        setTtsModel(settings.tts_model || "speech-2.8-hd");
        setTtsVoiceId(settings.tts_voice_id || "male-qn-qingse");
        setTtsKeyDraft(createProviderKeyDraft(settings.tts_api_key || ""));
        setEnableVisionVerification(settings.enable_vision_verification);
      })
      .catch(() => toast.error("加载设置失败"))
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (open) return;
    setProviderKeyDrafts((prev) => clearProviderPlaintextDrafts(prev));
    setTtsKeyDraft((prev) => ({
      ...prev,
      draftValue: "",
      showMasked: Boolean(prev.maskedValue),
    }));
  }, [open]);

  const updateDraft = (field: ModelRoleField, patch: Partial<ModelDraft>) => {
    setModelDrafts((prev) => ({
      ...prev,
      [field]: { ...prev[field], ...patch },
    }));
  };

  const updateProviderKeyDraft = (provider: ApiKeyProvider, value: string) => {
    setProviderKeyDrafts((prev) => ({
      ...prev,
      [provider]: { ...prev[provider], draftValue: value, showMasked: false },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await updateSettings({
        openai_base_url: openaiBaseUrl,
        default_model: modelValues.default_model,
        strong_model: modelValues.strong_model,
        vision_model: modelValues.vision_model,
        fast_model: modelValues.fast_model,
        tts_provider: ttsProvider,
        tts_base_url: ttsBaseUrl,
        tts_model: ttsModel,
        tts_voice_id: ttsVoiceId,
        enable_vision_verification: enableVisionVerification,
        ...Object.entries(providerKeyDrafts).reduce<Record<string, string>>((acc, [provider, state]) => {
          if (state.showMasked || !state.draftValue || state.draftValue.includes("...")) return acc;
          acc[API_KEY_FIELDS[provider as ApiKeyProvider]] = state.draftValue;
          return acc;
        }, {}),
        ...(!ttsKeyDraft.showMasked && ttsKeyDraft.draftValue && !ttsKeyDraft.draftValue.includes("...")
          ? { tts_api_key: ttsKeyDraft.draftValue }
          : {}),
      });

      setOpenaiBaseUrl(response.openai_base_url || "https://api.openai.com/v1");
      setProviderKeyDrafts(createProviderKeyDraftsFromSettings(response));
      setProviderStatus({
        has_openai_key: response.has_openai_key,
        has_anthropic_key: response.has_anthropic_key,
        has_google_key: response.has_google_key,
        has_deepseek_key: response.has_deepseek_key,
        has_openrouter_key: response.has_openrouter_key,
      });
      setModelDrafts({
        default_model: parseModelDraft(response.default_model),
        strong_model: parseModelDraft(response.strong_model),
        vision_model: parseModelDraft(response.vision_model),
        fast_model: parseModelDraft(response.fast_model),
      });
      setTtsProvider(response.tts_provider || "minimax");
      setTtsBaseUrl(response.tts_base_url || "https://api.minimaxi.com");
      setTtsModel(response.tts_model || "speech-2.8-hd");
      setTtsVoiceId(response.tts_voice_id || "male-qn-qingse");
      setTtsKeyDraft(createProviderKeyDraft(response.tts_api_key || ""));
      setEnableVisionVerification(response.enable_vision_verification);

      toast.success("设置已保存");
      window.dispatchEvent(new Event("settings:updated"));
    } catch {
      toast.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          setProviderKeyDrafts((prev) => clearProviderPlaintextDrafts(prev));
          setTtsKeyDraft((prev) => ({ ...prev, draftValue: "", showMasked: Boolean(prev.maskedValue) }));
        }
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className="max-h-[84vh] overflow-y-auto border-slate-200 bg-white p-0 shadow-xl sm:max-w-4xl dark:border-slate-800 dark:bg-slate-950">
        <DialogHeader className="border-b border-slate-200 px-5 py-4 pr-16 text-left dark:border-slate-800 sm:pr-20">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <DialogTitle className="text-lg font-semibold text-slate-950 dark:text-white">设置</DialogTitle>
              <DialogDescription className="text-sm text-slate-500 dark:text-slate-400">
                常用项放这里，尽量保持简单。
              </DialogDescription>
            </div>
            <div className="flex flex-wrap justify-end gap-2 pr-2">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                模型 {readyModelCount}/{MODEL_ROLE_CONFIG.length}
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                API {configuredProviderCount}/{PROVIDER_CONFIG.length}
              </span>
            </div>
          </div>
        </DialogHeader>

        {loading ? (
          <div className="flex min-h-[320px] items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        ) : (
          <div className="px-5 py-4">
            <Tabs defaultValue="models" className="space-y-4">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="models">模型</TabsTrigger>
                <TabsTrigger value="api">API</TabsTrigger>
                <TabsTrigger value="tts">语音</TabsTrigger>
              </TabsList>

              <TabsContent value="models" className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {MODEL_ROLE_CONFIG.map((role) => {
                    const status = modelStatuses[role.field] || EMPTY_MODEL_STATUS;
                    return (
                      <button
                        key={role.field}
                        type="button"
                        onClick={() => setActiveRole(role.field)}
                        className={cn(
                          "rounded-full border px-3 py-2 text-xs font-medium transition-colors",
                          activeRole === role.field
                            ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                            : "border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
                        )}
                      >
                        {role.label}
                        <span className="ml-1 opacity-80">{status.ready ? "已就绪" : "未就绪"}</span>
                      </button>
                    );
                  })}
                </div>

                <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {MODEL_ROLE_CONFIG.find((role) => role.field === activeRole)?.label}
                    </p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {MODEL_ROLE_CONFIG.find((role) => role.field === activeRole)?.hint}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-sm">Provider</Label>
                    <select
                      value={activeDraft.provider}
                      onChange={(e) => updateDraft(activeRole, { provider: e.target.value as DraftProvider })}
                      className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-ring dark:border-slate-800 dark:bg-slate-950"
                    >
                      {PROVIDER_CONFIG.map((provider) => (
                        <option key={provider.value} value={provider.value}>
                          {provider.label}
                        </option>
                      ))}
                      <option value="custom">自定义</option>
                    </select>
                  </div>

                  {activeDraft.provider === "custom" ? (
                    <div className="space-y-2">
                      <Label className="text-sm">自定义 Provider</Label>
                      <Input
                        value={activeDraft.customProvider}
                        onChange={(e) => updateDraft(activeRole, { customProvider: e.target.value })}
                        placeholder="例如：moonshot"
                        className="h-10 rounded-xl"
                      />
                    </div>
                  ) : null}

                  <div className="space-y-2">
                    <Label className="text-sm">模型名称</Label>
                    <Input
                      value={activeDraft.modelName}
                      onChange={(e) => updateDraft(activeRole, { modelName: e.target.value })}
                      placeholder="例如：gpt-4o-mini"
                      className="h-10 rounded-xl"
                    />
                    {activeKnownProvider ? (
                      <div className="flex flex-wrap gap-2">
                        {MODEL_SUGGESTIONS[activeKnownProvider].map((modelName) => (
                          <button
                            key={modelName}
                            type="button"
                            onClick={() => updateDraft(activeRole, { modelName })}
                            className={cn(
                              "rounded-full border px-2.5 py-1 text-xs transition-colors",
                              activeDraft.modelName.trim() === modelName
                                ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                                : "border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
                            )}
                          >
                            {modelName}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>

                  <div className={cn("rounded-xl border px-3 py-3", getStatusBadgeClasses(activeStatus.ready))}>
                    <p className="text-sm font-medium">{composeModelValue(activeDraft) || "未配置"}</p>
                    <p className="mt-1 text-xs opacity-90">{activeStatus.message}</p>
                    {activeKnownProvider ? (
                      <button
                        type="button"
                        onClick={() => setProviderEditorTab(activeKnownProvider)}
                        className="mt-2 text-xs underline-offset-4 hover:underline"
                      >
                        去 API 设置
                      </button>
                    ) : null}
                  </div>

                  {activeDraft.provider === "custom" ? (
                    <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
                      <Info className="mt-0.5 h-4 w-4 shrink-0" />
                      自定义 Provider 需要后端环境自行处理连接。
                    </div>
                  ) : null}
                </div>
              </TabsContent>

              <TabsContent value="api" className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {PROVIDER_CONFIG.map((provider) => {
                    const ready = providerStatus[provider.keyFlag];
                    return (
                      <button
                        key={provider.value}
                        type="button"
                        onClick={() => setProviderEditorTab(provider.value)}
                        className={cn(
                          "rounded-full border px-3 py-2 text-xs font-medium transition-colors",
                          providerEditorTab === provider.value
                            ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                            : "border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
                        )}
                      >
                        {provider.label}
                        <span className="ml-1 opacity-80">{ready ? "已连接" : ""}</span>
                      </button>
                    );
                  })}
                </div>

                <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {getProviderLabel(providerEditorTab)}
                    </p>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px]",
                        getStatusBadgeClasses(activeProviderConfigured)
                      )}
                    >
                      {activeProviderConfigured ? "已连接" : "未连接"}
                    </span>
                  </div>

                  <KeyField
                    label="API Key"
                    value={activeProviderKeyDraft.showMasked ? "" : activeProviderKeyDraft.draftValue}
                    onChange={(value) =>
                      updateProviderKeyDraft(providerEditorTab === "google-gla" ? "google" : providerEditorTab, value)
                    }
                    provider={providerEditorTab === "google-gla" ? "google" : providerEditorTab}
                    baseUrl={providerEditorTab === "openai" ? openaiBaseUrl : undefined}
                    placeholder={
                      providerEditorTab === "anthropic"
                        ? "sk-ant-..."
                        : providerEditorTab === "google-gla"
                          ? "AIza..."
                          : providerEditorTab === "openrouter"
                            ? "sk-or-..."
                            : "sk-..."
                    }
                    configured={activeProviderConfigured}
                  />

                  {providerEditorTab === "openai" ? (
                    <div className="space-y-2">
                      <Label className="text-sm">Base URL</Label>
                      <Input
                        value={openaiBaseUrl}
                        onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                        placeholder="https://api.openai.com/v1"
                        className="h-10 rounded-xl"
                      />
                    </div>
                  ) : null}
                </div>

                <label className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-950">
                  <span>启用视觉验证</span>
                  <input
                    type="checkbox"
                    checked={enableVisionVerification}
                    onChange={(e) => setEnableVisionVerification(e.target.checked)}
                    className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                  />
                </label>
              </TabsContent>

              <TabsContent value="tts" className="space-y-4">
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">语音朗读</p>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px]",
                        getStatusBadgeClasses(ttsConfigured)
                      )}
                    >
                      {ttsConfigured ? "已配置" : "未配置"}
                    </span>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-sm">服务商</Label>
                    <select
                      value={ttsProvider}
                      onChange={(e) => setTtsProvider(e.target.value)}
                      className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-ring dark:border-slate-800 dark:bg-slate-950"
                    >
                      <option value="minimax">MiniMax</option>
                    </select>
                  </div>

                  <KeyField
                    label="TTS API Key"
                    value={ttsKeyDraft.showMasked ? "" : ttsKeyDraft.draftValue}
                    onChange={(value) => setTtsKeyDraft((prev) => ({ ...prev, draftValue: value, showMasked: false }))}
                    provider="minimax"
                    placeholder="Bearer API Key"
                    configured={Boolean(ttsKeyDraft.maskedValue)}
                    showValidate={false}
                  />

                  <div className="space-y-2">
                    <Label className="text-sm">Base URL</Label>
                    <Input
                      value={ttsBaseUrl}
                      onChange={(e) => setTtsBaseUrl(e.target.value)}
                      placeholder="https://api.minimaxi.com"
                      className="h-10 rounded-xl"
                    />
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label className="text-sm">模型</Label>
                      <Input
                        value={ttsModel}
                        onChange={(e) => setTtsModel(e.target.value)}
                        placeholder="speech-2.8-hd"
                        className="h-10 rounded-xl"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm">音色</Label>
                      <Input
                        value={ttsVoiceId}
                        onChange={(e) => setTtsVoiceId(e.target.value)}
                        placeholder="male-qn-qingse"
                        className="h-10 rounded-xl"
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>
            </Tabs>

            <div className="mt-4 flex flex-col gap-3 border-t border-slate-200 pt-4 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {readyModelCount === MODEL_ROLE_CONFIG.length
                  ? "模型已准备好。"
                  : `还有 ${MODEL_ROLE_CONFIG.length - readyModelCount} 个模型未准备好。`}
              </p>
              <Button
                type="button"
                onClick={() => {
                  void handleSave();
                }}
                disabled={saving}
                className="h-10 rounded-xl px-5"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                保存设置
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function SettingsDialog() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        title="设置"
      >
        <Settings className="h-4 w-4" />
      </button>
      <SettingsDialogContent open={open} onOpenChange={setOpen} />
    </>
  );
}
