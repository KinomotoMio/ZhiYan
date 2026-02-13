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
  updateSettings,
  validateApiKey,
  type ModelStatus,
} from "@/lib/api";

type ModelRoleField = "default_model" | "strong_model" | "vision_model" | "fast_model";
type KnownProvider = "openai" | "anthropic" | "google-gla" | "deepseek" | "openrouter";
type DraftProvider = KnownProvider | "custom";

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
  configured?: boolean;
}

function KeyField({
  label,
  value,
  onChange,
  provider,
  baseUrl,
  placeholder,
  configured,
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
            placeholder={!value && configured ? "已配置 · 输入新值可覆盖" : placeholder || "sk-..."}
            className="pr-8"
          />
          <button
            type="button"
            onClick={() => setVisible(!visible)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label={visible ? "隐藏 API Key" : "显示 API Key"}
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <button
          type="button"
          onClick={handleValidate}
          disabled={validating || !value}
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

  const [providerStatus, setProviderStatus] = useState<ProviderStatus>(DEFAULT_PROVIDER_STATUS);

  const [openaiKey, setOpenaiKey] = useState("");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("https://api.openai.com/v1");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [deepseekKey, setDeepseekKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [enableVisionVerification, setEnableVisionVerification] = useState(true);

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
        const unmask = (value: string) => (value.includes("...") ? "" : value);
        setOpenaiKey(unmask(settings.openai_api_key));
        setOpenaiBaseUrl(settings.openai_base_url || "https://api.openai.com/v1");
        setAnthropicKey(unmask(settings.anthropic_api_key));
        setGoogleKey(unmask(settings.google_api_key));
        setDeepseekKey(unmask(settings.deepseek_api_key));
        setOpenrouterKey(unmask(settings.openrouter_api_key));
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

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await updateSettings({
        openai_base_url: openaiBaseUrl,
        default_model: modelValues.default_model,
        strong_model: modelValues.strong_model,
        vision_model: modelValues.vision_model,
        fast_model: modelValues.fast_model,
        enable_vision_verification: enableVisionVerification,
        ...(openaiKey && { openai_api_key: openaiKey }),
        ...(anthropicKey && { anthropic_api_key: anthropicKey }),
        ...(googleKey && { google_api_key: googleKey }),
        ...(deepseekKey && { deepseek_api_key: deepseekKey }),
        ...(openrouterKey && { openrouter_api_key: openrouterKey }),
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
    } catch {
      toast.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
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

      <Dialog open={providerEditorOpen} onOpenChange={setProviderEditorOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>API 信息</DialogTitle>
            <DialogDescription>统一管理各 Provider 的 API Key，修改后点击外层“保存设置”生效</DialogDescription>
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
                value={openaiKey}
                onChange={setOpenaiKey}
                provider="openai"
                baseUrl={openaiBaseUrl}
                placeholder="sk-..."
                configured={providerStatus.has_openai_key}
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
                value={anthropicKey}
                onChange={setAnthropicKey}
                provider="anthropic"
                placeholder="sk-ant-..."
                configured={providerStatus.has_anthropic_key}
              />
            </TabsContent>

            <TabsContent value="google-gla" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={googleKey}
                onChange={setGoogleKey}
                provider="google"
                placeholder="AIza..."
                configured={providerStatus.has_google_key}
              />
            </TabsContent>

            <TabsContent value="deepseek" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={deepseekKey}
                onChange={setDeepseekKey}
                provider="deepseek"
                placeholder="sk-..."
                configured={providerStatus.has_deepseek_key}
              />
            </TabsContent>

            <TabsContent value="openrouter" className="space-y-3 mt-4">
              <KeyField
                label="API Key"
                value={openrouterKey}
                onChange={setOpenrouterKey}
                provider="openrouter"
                placeholder="sk-or-..."
                configured={providerStatus.has_openrouter_key}
              />
            </TabsContent>
          </Tabs>
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
