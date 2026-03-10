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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getSettings,
  getSettingsProviderKey,
  updateSettings,
  validateApiKey,
  type ModelStatus,
} from "@/lib/api";

type ModelRoleField = "default_model" | "strong_model" | "vision_model" | "fast_model";
type KnownProvider = "openai" | "anthropic" | "google-gla" | "deepseek" | "openrouter";
type DraftProvider = KnownProvider | "custom";
type ApiKeyProvider = "openai" | "anthropic" | "google" | "deepseek" | "openrouter";

interface ProviderKeyDraft {
  draftValue: string;
  maskedValue: string;
  showMasked: boolean;
  cachedPlainValue: string | null;
}

const API_KEY_FIELDS: Record<ApiKeyProvider, "openai_api_key" | "anthropic_api_key" | "google_api_key" | "deepseek_api_key" | "openrouter_api_key"> = {
  openai: "openai_api_key",
  anthropic: "anthropic_api_key",
  google: "google_api_key",
  deepseek: "deepseek_api_key",
  openrouter: "openrouter_api_key",
};

const EMPTY_PROVIDER_KEY_DRAFTS: Record<ApiKeyProvider, ProviderKeyDraft> = {
  openai: { draftValue: "", maskedValue: "", showMasked: false, cachedPlainValue: null },
  anthropic: { draftValue: "", maskedValue: "", showMasked: false, cachedPlainValue: null },
  google: { draftValue: "", maskedValue: "", showMasked: false, cachedPlainValue: null },
  deepseek: { draftValue: "", maskedValue: "", showMasked: false, cachedPlainValue: null },
  openrouter: { draftValue: "", maskedValue: "", showMasked: false, cachedPlainValue: null },
};

function createProviderKeyDraft(maskedValue: string): ProviderKeyDraft {
  return {
    draftValue: "",
    maskedValue,
    showMasked: Boolean(maskedValue),
    cachedPlainValue: null,
  };
}

function getProviderKeyDisplayValue(state: ProviderKeyDraft): string {
  return state.showMasked ? state.maskedValue : state.draftValue;
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

const PROVIDER_CONFIG = [
  { value: "openai", label: "OpenAI", keyFlag: "has_openai_key" as const },
  { value: "anthropic", label: "Anthropic", keyFlag: "has_anthropic_key" as const },
  { value: "google-gla", label: "Google", keyFlag: "has_google_key" as const },
  { value: "deepseek", label: "DeepSeek", keyFlag: "has_deepseek_key" as const },
  { value: "openrouter", label: "OpenRouter", keyFlag: "has_openrouter_key" as const },
] as const;

const MODEL_ROLE_CONFIG = [
  { field: "default_model", label: "默认模型", hint: "用于主要文本生成链路" },
  { field: "strong_model", label: "高级模型", hint: "用于高质量结构化生成" },
  { field: "vision_model", label: "多模态模型", hint: "用于视觉审美评估（需图片能力）" },
  { field: "fast_model", label: "快速模型", hint: "用于文档清洗、分块分析等简单任务，建议选非 thinking 模型" },
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

const DEFAULT_PROVIDER_STATUS: ProviderStatus = {
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

function isKnownProvider(value: string): value is KnownProvider {
  return PROVIDER_CONFIG.some((provider) => provider.value === value);
}

function parseModelDraft(raw: string): ModelDraft {
  const value = raw.trim();
  if (!value) {
    return { provider: "openai", customProvider: "", modelName: "" };
  }

  if (!value.includes(":")) {
    return { provider: "custom", customProvider: "", modelName: value };
  }

  const [providerPart, ...rest] = value.split(":");
  const provider = providerPart.trim();
  const modelName = rest.join(":").trim();

  if (isKnownProvider(provider)) {
    return { provider, customProvider: "", modelName };
  }

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
  if (!value) {
    return {
      model: "",
      provider: "",
      ready: false,
      message: "请先在当前 Tab 输入 Provider 与 Model Name",
    };
  }

  if (!value.includes(":")) {
    return {
      model: value,
      provider: "",
      ready: true,
      message: "未检测到 provider 前缀，将按原始模型名尝试调用",
    };
  }

  const [provider, ...rest] = value.split(":");
  const providerName = provider.trim();
  const modelName = rest.join(":").trim();

  if (!modelName) {
    return {
      model: value,
      provider: providerName,
      ready: false,
      message: "模型格式无效，请使用 provider:model-name",
    };
  }

  if (!isKnownProvider(providerName)) {
    return {
      model: value,
      provider: providerName,
      ready: true,
      message: `Provider ${providerName} 未内置 API Key 校验，将在运行时尝试调用`,
    };
  }

  const keyFlag = PROVIDER_CONFIG.find((p) => p.value === providerName)?.keyFlag;
  const hasKey = keyFlag ? providerStatus[keyFlag] : false;
  if (hasKey) {
    return {
      model: value,
      provider: providerName,
      ready: true,
      message: `${providerName} API Key 已配置，可直接生成`,
    };
  }

  return {
    model: value,
    provider: providerName,
    ready: false,
    message: `模型 ${value} 需要 ${providerName} API Key，请先在 API 信息中配置`,
  };
}

interface KeyFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  provider: "openai" | "anthropic" | "google" | "deepseek" | "openrouter";
  baseUrl?: string;
  placeholder?: string;
  isMaskedValue?: boolean;
  onRevealValue?: () => Promise<string>;
  onHideMask?: () => void;
}

function KeyField({
  label,
  value,
  onChange,
  provider,
  baseUrl,
  placeholder,
  isMaskedValue,
  onRevealValue,
  onHideMask,
}: KeyFieldProps) {
  const [visible, setVisible] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [validating, setValidating] = useState(false);
  const [status, setStatus] = useState<"idle" | "valid" | "invalid">("idle");

  const handleValidate = async () => {
    if (!value || isMaskedValue || value.includes("...")) {
      toast.error("当前是掩码值，请先显示明文或输入新 Key");
      return;
    }
    setValidating(true);
    setStatus("idle");
    try {
      const res = await validateApiKey(provider, value, baseUrl);
      setStatus(res.valid ? "valid" : "invalid");
      if (res.valid) toast.success(res.message);
      else toast.error(res.message);
    } catch {
      setStatus("invalid");
      toast.error("验证请求失败");
    } finally {
      setValidating(false);
    }
  };

  const handleToggleVisible = async () => {
    if (visible) {
      setVisible(false);
      onHideMask?.();
      return;
    }

    if ((isMaskedValue || !value || value.includes("...")) && onRevealValue) {
      setRevealing(true);
      try {
        const plain = await onRevealValue();
        onChange(plain || "");
      } catch {
        toast.error("获取明文 Key 失败");
        return;
      } finally {
        setRevealing(false);
      }
    }

    setStatus("idle");
    setVisible(true);
  };
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            type={visible ? "text" : "password"}
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setStatus("idle");
            }}
            placeholder={placeholder || "sk-..."}
            className="pr-8"
          />
          <button
            type="button"
            onClick={handleToggleVisible}
            disabled={revealing}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label={visible ? "隐藏 API Key" : "显示 API Key"}
          >
            {revealing ? <Loader2 className="h-4 w-4 animate-spin" /> : visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <button
          type="button"
          onClick={handleValidate}
          disabled={validating || revealing || !value}
          className="flex items-center gap-1 px-3 py-1.5 text-xs border rounded-md hover:bg-muted disabled:opacity-50 shrink-0"
        >
          {validating ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : status === "valid" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
          ) : status === "invalid" ? (
            <AlertTriangle className="h-3.5 w-3.5 text-red-600" />
          ) : null}
          验证
        </button>
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
  const [providerEditorOpen, setProviderEditorOpen] = useState(false);
  const [providerEditorTab, setProviderEditorTab] = useState<KnownProvider>("openrouter");

  const [providerStatus, setProviderStatus] = useState<ProviderStatus>(DEFAULT_PROVIDER_STATUS);  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("https://api.openai.com/v1");
  const [providerKeyDrafts, setProviderKeyDrafts] =
    useState<Record<ApiKeyProvider, ProviderKeyDraft>>(EMPTY_PROVIDER_KEY_DRAFTS);
  const [enableVisionVerification, setEnableVisionVerification] = useState(true);

  const updateProviderKeyDraft = (provider: ApiKeyProvider, nextValue: string) => {
    setProviderKeyDrafts((prev) => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        draftValue: nextValue,
        showMasked: false,
      },
    }));
  };

  const hideProviderKey = (provider: ApiKeyProvider) => {
    setProviderKeyDrafts((prev) => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        showMasked: Boolean(prev[provider].maskedValue),
      },
    }));
  };

  const revealProviderKey = async (provider: ApiKeyProvider): Promise<string> => {
    const current = providerKeyDrafts[provider];
    if (!current.showMasked && current.draftValue) {
      return current.draftValue;
    }
    if (current.cachedPlainValue !== null) {
      setProviderKeyDrafts((prev) => ({
        ...prev,
        [provider]: {
          ...prev[provider],
          draftValue: current.cachedPlainValue || "",
          showMasked: false,
        },
      }));
      return current.cachedPlainValue || "";
    }

    const response = await getSettingsProviderKey(provider);
    const plain = response.api_key || "";
    setProviderKeyDrafts((prev) => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        draftValue: plain,
        cachedPlainValue: plain,
        showMasked: false,
      },
    }));
    return plain;
  };

  const clearProviderPlaintext = () => {
    setProviderKeyDrafts((prev) => ({
      openai: { ...prev.openai, draftValue: "", cachedPlainValue: null, showMasked: Boolean(prev.openai.maskedValue) },
      anthropic: { ...prev.anthropic, draftValue: "", cachedPlainValue: null, showMasked: Boolean(prev.anthropic.maskedValue) },
      google: { ...prev.google, draftValue: "", cachedPlainValue: null, showMasked: Boolean(prev.google.maskedValue) },
      deepseek: { ...prev.deepseek, draftValue: "", cachedPlainValue: null, showMasked: Boolean(prev.deepseek.maskedValue) },
      openrouter: { ...prev.openrouter, draftValue: "", cachedPlainValue: null, showMasked: Boolean(prev.openrouter.maskedValue) },
    }));
  };

  const [modelDrafts, setModelDrafts] =
    useState<Record<ModelRoleField, ModelDraft>>(EMPTY_MODEL_DRAFTS);

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

  const activeDraft = modelDrafts[activeRole];
  const activeStatus = modelStatuses[activeRole] || EMPTY_MODEL_STATUS;
  const activeProviderValue = getDraftProviderValue(activeDraft);
  const activeKnownProvider = isKnownProvider(activeProviderValue) ? activeProviderValue : null;

  useEffect(() => {
    if (!open) return;

    setLoading(true);
    getSettings()
      .then((settings) => {
        setOpenaiBaseUrl(settings.openai_base_url || "https://api.openai.com/v1");
        setProviderKeyDrafts({
          openai: createProviderKeyDraft(settings.openai_api_key),
          anthropic: createProviderKeyDraft(settings.anthropic_api_key),
          google: createProviderKeyDraft(settings.google_api_key),
          deepseek: createProviderKeyDraft(settings.deepseek_api_key),
          openrouter: createProviderKeyDraft(settings.openrouter_api_key),
        });
        setEnableVisionVerification(settings.enable_vision_verification);
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
      })
      .catch(() => toast.error("加载设置失败"))
      .finally(() => setLoading(false));
  }, [open]);
  useEffect(() => {
    if (!open) {
      setProviderEditorOpen(false);
      clearProviderPlaintext();
    }
  }, [open]);

  const updateDraft = (field: ModelRoleField, patch: Partial<ModelDraft>) => {
    setModelDrafts((prev) => ({
      ...prev,
      [field]: {
        ...prev[field],
        ...patch,
      },
    }));
  };

  const openProviderEditor = () => {
    setProviderEditorTab(activeKnownProvider || "openrouter");
    setProviderEditorOpen(true);
  };

  const handleSave = async (): Promise<boolean> => {
    setSaving(true);
    try {
      const response = await updateSettings({
        openai_base_url: openaiBaseUrl,
        default_model: modelValues.default_model,
        strong_model: modelValues.strong_model,
        vision_model: modelValues.vision_model,
        fast_model: modelValues.fast_model,
        enable_vision_verification: enableVisionVerification,
        ...Object.entries(providerKeyDrafts).reduce<Record<string, string>>((acc, [provider, state]) => {
          if (state.showMasked || !state.draftValue || state.draftValue.includes("...")) {
            return acc;
          }
          const field = API_KEY_FIELDS[provider as ApiKeyProvider];
          acc[field] = state.draftValue;
          return acc;
        }, {}),
      });

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
      setEnableVisionVerification(response.enable_vision_verification);
      setProviderKeyDrafts({
        openai: createProviderKeyDraft(response.openai_api_key),
        anthropic: createProviderKeyDraft(response.anthropic_api_key),
        google: createProviderKeyDraft(response.google_api_key),
        deepseek: createProviderKeyDraft(response.deepseek_api_key),
        openrouter: createProviderKeyDraft(response.openrouter_api_key),
      });

      toast.success("设置已保存");
      window.dispatchEvent(new Event("settings:updated"));

      const warnings = [
        response.default_model_status,
        response.strong_model_status,
        response.vision_model_status,
        response.fast_model_status,
      ].filter((status) => !status.ready);
      if (warnings.length > 0) {
        toast("设置已保存，但有模型尚未就绪", {
          description: warnings.map((status) => status.message).join("；"),
        });
      }
      return true;
    } catch {
      toast.error("保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  };
  const handleProviderEditorSave = async () => {
    const saved = await handleSave();
    if (!saved) return;
    setProviderEditorOpen(false);
    clearProviderPlaintext();
  };
  const handleSettingsDialogOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setProviderEditorOpen(false);
      clearProviderPlaintext();
    }
    onOpenChange(nextOpen);
  };

  const handleProviderEditorOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      clearProviderPlaintext();
    }
    setProviderEditorOpen(nextOpen);
  };
  return (
    <>
      <Dialog open={open} onOpenChange={handleSettingsDialogOpenChange}>
        <DialogContent className="sm:max-w-3xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>设置</DialogTitle>
            <DialogDescription>按“默认模型 / 高级模型 / 多模态模型”分别配置 Provider、模型名与 API 信息</DialogDescription>
          </DialogHeader>

          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-4">
              <Tabs value={activeRole} onValueChange={(value) => setActiveRole(value as ModelRoleField)}>
                <TabsList className="w-full">
                  {MODEL_ROLE_CONFIG.map((role) => (
                    <TabsTrigger key={role.field} value={role.field}>
                      {role.label}
                    </TabsTrigger>
                  ))}
                </TabsList>

                {MODEL_ROLE_CONFIG.map((role) => {
                  const draft = modelDrafts[role.field];
                  const status = modelStatuses[role.field] || EMPTY_MODEL_STATUS;
                  const providerValue = getDraftProviderValue(draft);
                  const knownProvider = isKnownProvider(providerValue) ? providerValue : null;
                  const providerConfig = knownProvider
                    ? PROVIDER_CONFIG.find((provider) => provider.value === knownProvider)
                    : null;
                  const hasProviderKey = providerConfig
                    ? providerStatus[providerConfig.keyFlag]
                    : false;

                  return (
                    <TabsContent key={role.field} value={role.field} className="space-y-4 mt-4">
                      <div className="space-y-1">
                        <p className="text-sm font-medium">{role.label}</p>
                        <p className="text-xs text-muted-foreground">{role.hint}</p>
                      </div>

                      <div className="space-y-1.5">
                        <Label className="text-sm">Provider</Label>
                        <select
                          value={draft.provider}
                          onChange={(e) => updateDraft(role.field, { provider: e.target.value as DraftProvider })}
                          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                        >
                          {PROVIDER_CONFIG.map((provider) => (
                            <option key={provider.value} value={provider.value}>
                              {provider.label}
                            </option>
                          ))}
                          <option value="custom">自定义 Provider</option>
                        </select>
                      </div>

                      {draft.provider === "custom" && (
                        <div className="space-y-1.5">
                          <Label className="text-sm">自定义 Provider 名称</Label>
                          <Input
                            value={draft.customProvider}
                            onChange={(e) => updateDraft(role.field, { customProvider: e.target.value })}
                            placeholder="例如：moonshot"
                          />
                        </div>
                      )}

                      <div className="space-y-1.5">
                        <Label className="text-sm">Model Name</Label>
                        <Input
                          value={draft.modelName}
                          onChange={(e) => updateDraft(role.field, { modelName: e.target.value })}
                          placeholder="例如：gpt-4o-mini / moonshotai/kimi-k2.5"
                        />
                        {knownProvider && MODEL_SUGGESTIONS[knownProvider].length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {MODEL_SUGGESTIONS[knownProvider].map((modelName) => (
                              <button
                                key={modelName}
                                type="button"
                                onClick={() => updateDraft(role.field, { modelName })}
                                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                                  draft.modelName.trim() === modelName
                                    ? "bg-primary text-primary-foreground border-primary"
                                    : "hover:bg-muted"
                                }`}
                              >
                                {modelName}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="rounded-md border bg-muted/30 p-3 space-y-1">
                        <p className="text-xs text-muted-foreground">完整模型预览</p>
                        <code className="text-sm break-all">
                          {composeModelValue(draft) || "(空)"}
                        </code>
                      </div>

                      <div
                        className={`rounded-md border p-3 flex items-start gap-2 ${
                          status.ready
                            ? "border-green-300/70 bg-green-50/60 dark:bg-green-950/20"
                            : "border-amber-300/70 bg-amber-50/70 dark:bg-amber-950/20"
                        }`}
                      >
                        {status.ready ? (
                          <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                        )}
                        <div className="space-y-1">
                          <p className="text-sm font-medium">{status.ready ? "当前模型已就绪" : "当前模型尚未就绪"}</p>
                          <p className="text-xs text-muted-foreground">{status.message}</p>
                        </div>
                      </div>

                      <div className="rounded-lg border p-4 space-y-3">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium">API 信息</p>
                            <p className="text-xs text-muted-foreground">
                              当前 Provider：{providerValue || "(未填写)"}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={openProviderEditor}
                            className="px-3 py-1.5 text-xs rounded-md border hover:bg-muted transition-colors"
                          >
                            编辑 API 信息
                          </button>
                        </div>
                        {knownProvider ? (
                          <div className="flex items-center gap-2 text-xs">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full ${
                                hasProviderKey
                                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                              }`}
                            >
                              {hasProviderKey ? "API Key 已配置" : "API Key 未配置"}
                            </span>
                            {knownProvider === "openai" && (
                              <span className="text-muted-foreground">
                                Base URL: {openaiBaseUrl || "https://api.openai.com/v1"}
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
                            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                            <span>自定义 Provider 不走内置 Key 管理，请确保后端运行环境可直接访问该模型。</span>
                          </div>
                        )}
                      </div>
                    </TabsContent>
                  );
                })}
              </Tabs>

              <div className="rounded-lg border p-4 space-y-2">
                <p className="text-sm font-medium">生成验证</p>
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-muted-foreground">启用视觉验证（截图审美评估）</span>
                  <input
                    type="checkbox"
                    checked={enableVisionVerification}
                    onChange={(e) => setEnableVisionVerification(e.target.checked)}
                    className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                  />
                </label>
                <p className="text-xs text-muted-foreground">
                  关闭后将跳过 Playwright 截图验证，仅保留程序化与文本评估。
                </p>
              </div>

              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="w-full py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                保存设置
              </button>

              {!activeStatus.ready && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  提示：当前 Tab 模型未就绪仍可保存，系统会在生成时给出明确错误与修复提示。
                </p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={providerEditorOpen} onOpenChange={handleProviderEditorOpenChange}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>API 信息</DialogTitle>
            <DialogDescription>统一管理各 Provider 的 API Key，可在当前窗口直接保存生效</DialogDescription>
          </DialogHeader>

          <Tabs value={providerEditorTab} onValueChange={(value) => setProviderEditorTab(value as KnownProvider)}>
            <TabsList className="w-full">
              {PROVIDER_CONFIG.map((provider) => (
                <TabsTrigger key={provider.value} value={provider.value}>
                  {provider.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="openai" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={getProviderKeyDisplayValue(providerKeyDrafts.openai)}
                onChange={(value) => updateProviderKeyDraft("openai", value)}
                provider="openai"
                baseUrl={openaiBaseUrl}
                placeholder="sk-..."
                isMaskedValue={providerKeyDrafts.openai.showMasked}
                onRevealValue={() => revealProviderKey("openai")}
                onHideMask={() => hideProviderKey("openai")}
              />
              <div className="space-y-1.5">
                <Label className="text-sm">Base URL</Label>
                <Input
                  value={openaiBaseUrl}
                  onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                />
                <p className="text-xs text-muted-foreground">兼容 OpenAI 接口的服务可修改此地址</p>
              </div>
            </TabsContent>

            <TabsContent value="anthropic" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={getProviderKeyDisplayValue(providerKeyDrafts.anthropic)}
                onChange={(value) => updateProviderKeyDraft("anthropic", value)}
                provider="anthropic"
                placeholder="sk-ant-..."
                isMaskedValue={providerKeyDrafts.anthropic.showMasked}
                onRevealValue={() => revealProviderKey("anthropic")}
                onHideMask={() => hideProviderKey("anthropic")}
              />
            </TabsContent>

            <TabsContent value="google-gla" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={getProviderKeyDisplayValue(providerKeyDrafts.google)}
                onChange={(value) => updateProviderKeyDraft("google", value)}
                provider="google"
                placeholder="AIza..."
                isMaskedValue={providerKeyDrafts.google.showMasked}
                onRevealValue={() => revealProviderKey("google")}
                onHideMask={() => hideProviderKey("google")}
              />
            </TabsContent>

            <TabsContent value="deepseek" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={getProviderKeyDisplayValue(providerKeyDrafts.deepseek)}
                onChange={(value) => updateProviderKeyDraft("deepseek", value)}
                provider="deepseek"
                placeholder="sk-..."
                isMaskedValue={providerKeyDrafts.deepseek.showMasked}
                onRevealValue={() => revealProviderKey("deepseek")}
                onHideMask={() => hideProviderKey("deepseek")}
              />
            </TabsContent>

            <TabsContent value="openrouter" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={getProviderKeyDisplayValue(providerKeyDrafts.openrouter)}
                onChange={(value) => updateProviderKeyDraft("openrouter", value)}
                provider="openrouter"
                placeholder="sk-or-..."
                isMaskedValue={providerKeyDrafts.openrouter.showMasked}
                onRevealValue={() => revealProviderKey("openrouter")}
                onHideMask={() => hideProviderKey("openrouter")}
              />
            </TabsContent>
          </Tabs>

          <button
            type="button"
            onClick={handleProviderEditorSave}
            disabled={saving}
            className="w-full py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center justify-center gap-2 mt-4"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            保存 API 信息
          </button>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function SettingsDialog() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title="设置"
      >
        <Settings className="h-4 w-4" />
      </button>
      <SettingsDialogContent open={open} onOpenChange={setOpen} />
    </>
  );
}
