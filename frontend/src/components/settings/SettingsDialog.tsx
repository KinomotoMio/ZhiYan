"use client";

import { useState, useEffect } from "react";
import { Settings, Eye, EyeOff, Check, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
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
  type AppSettings,
} from "@/lib/api";

// ---------- 模型预设（按 Provider 分组）----------

const MODEL_PRESET_GROUPS = [
  {
    provider: "openai",
    label: "OpenAI",
    hasKeyField: "has_openai_key" as const,
    presets: [
      { label: "GPT-4o Mini", value: "openai:gpt-4o-mini" },
      { label: "GPT-4o", value: "openai:gpt-4o" },
    ],
  },
  {
    provider: "anthropic",
    label: "Anthropic",
    hasKeyField: "has_anthropic_key" as const,
    presets: [
      { label: "Claude Sonnet 4.5", value: "anthropic:claude-sonnet-4-5-20250929" },
    ],
  },
  {
    provider: "google",
    label: "Google",
    hasKeyField: "has_google_key" as const,
    presets: [
      { label: "Gemini 2.0 Flash", value: "google-gla:gemini-2.0-flash" },
    ],
  },
  {
    provider: "deepseek",
    label: "DeepSeek",
    hasKeyField: "has_deepseek_key" as const,
    presets: [
      { label: "DeepSeek-V3", value: "deepseek:deepseek-chat" },
      { label: "DeepSeek-R1", value: "deepseek:deepseek-reasoner" },
    ],
  },
  {
    provider: "openrouter",
    label: "OpenRouter",
    hasKeyField: "has_openrouter_key" as const,
    presets: [
      { label: "DeepSeek V3", value: "openrouter:deepseek/deepseek-chat-v3-0324" },
      { label: "Claude Sonnet 4", value: "openrouter:anthropic/claude-sonnet-4" },
      { label: "Gemini 2.0 Flash", value: "openrouter:google/gemini-2.0-flash-001" },
      { label: "GPT-4o", value: "openrouter:openai/gpt-4o" },
    ],
  },
];

// Vision 模型预设（排除不支持图片输入的 DeepSeek）
const VISION_MODEL_PRESET_GROUPS = [
  {
    provider: "openai",
    label: "OpenAI",
    hasKeyField: "has_openai_key" as const,
    presets: [
      { label: "GPT-4o Mini", value: "openai:gpt-4o-mini" },
      { label: "GPT-4o", value: "openai:gpt-4o" },
    ],
  },
  {
    provider: "anthropic",
    label: "Anthropic",
    hasKeyField: "has_anthropic_key" as const,
    presets: [
      { label: "Claude Sonnet 4.5", value: "anthropic:claude-sonnet-4-5-20250929" },
    ],
  },
  {
    provider: "google",
    label: "Google",
    hasKeyField: "has_google_key" as const,
    presets: [
      { label: "Gemini 2.0 Flash", value: "google-gla:gemini-2.0-flash" },
    ],
  },
  {
    provider: "openrouter",
    label: "OpenRouter",
    hasKeyField: "has_openrouter_key" as const,
    presets: [
      { label: "GPT-4o", value: "openrouter:openai/gpt-4o" },
      { label: "Claude Sonnet 4", value: "openrouter:anthropic/claude-sonnet-4" },
      { label: "Gemini 2.0 Flash", value: "openrouter:google/gemini-2.0-flash-001" },
    ],
  },
];

// ---------- KeyField ----------

interface KeyFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  provider: string;
  baseUrl?: string;
  placeholder?: string;
  configured?: boolean;
}

function KeyField({ label, value, onChange, provider, baseUrl, placeholder, configured }: KeyFieldProps) {
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
            placeholder={!value && configured ? "已配置 · 输入新值可覆盖" : (placeholder || "sk-...")}
            className="pr-8"
          />
          <button
            type="button"
            onClick={() => setVisible(!visible)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
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
            <Check className="h-3.5 w-3.5 text-green-500" />
          ) : status === "invalid" ? (
            <X className="h-3.5 w-3.5 text-red-500" />
          ) : null}
          验证
        </button>
      </div>
    </div>
  );
}

// ---------- ProviderCard ----------

interface ProviderCardProps {
  name: string;
  hasKey: boolean;
  children: React.ReactNode;
}

function ProviderCard({ name, hasKey, children }: ProviderCardProps) {
  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">{name}</h4>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
            hasKey
              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {hasKey ? "已配置" : "未配置"}
        </span>
      </div>
      {children}
    </div>
  );
}

// ---------- SettingsDialogContent ----------

interface SettingsDialogContentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialogContent({ open, onOpenChange }: SettingsDialogContentProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // API Keys
  const [openaiKey, setOpenaiKey] = useState("");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [deepseekKey, setDeepseekKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");

  // 模型
  const [defaultModel, setDefaultModel] = useState("");
  const [strongModel, setStrongModel] = useState("");
  const [visionModel, setVisionModel] = useState("");

  // Provider 状态
  const [providerStatus, setProviderStatus] = useState({
    has_openai_key: false,
    has_anthropic_key: false,
    has_google_key: false,
    has_deepseek_key: false,
    has_openrouter_key: false,
  });

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getSettings()
      .then((s) => {
        const unmask = (v: string) => (v.includes("...") ? "" : v);
        setOpenaiKey(unmask(s.openai_api_key));
        setOpenaiBaseUrl(s.openai_base_url);
        setAnthropicKey(unmask(s.anthropic_api_key));
        setGoogleKey(unmask(s.google_api_key));
        setDeepseekKey(unmask(s.deepseek_api_key));
        setOpenrouterKey(unmask(s.openrouter_api_key));
        setDefaultModel(s.default_model);
        setStrongModel(s.strong_model);
        setVisionModel(s.vision_model);
        setProviderStatus({
          has_openai_key: s.has_openai_key,
          has_anthropic_key: s.has_anthropic_key,
          has_google_key: s.has_google_key,
          has_deepseek_key: s.has_deepseek_key,
          has_openrouter_key: s.has_openrouter_key,
        });
      })
      .catch(() => toast.error("加载设置失败"))
      .finally(() => setLoading(false));
  }, [open]);

  const handleSave = async () => {
    setSaving(true);
    try {
      // 空字符串的 key 不发送，避免覆盖后端已存储的值
      const res = await updateSettings({
        openai_base_url: openaiBaseUrl,
        default_model: defaultModel,
        strong_model: strongModel,
        vision_model: visionModel,
        ...(openaiKey && { openai_api_key: openaiKey }),
        ...(anthropicKey && { anthropic_api_key: anthropicKey }),
        ...(googleKey && { google_api_key: googleKey }),
        ...(deepseekKey && { deepseek_api_key: deepseekKey }),
        ...(openrouterKey && { openrouter_api_key: openrouterKey }),
      });
      setProviderStatus({
        has_openai_key: res.has_openai_key,
        has_anthropic_key: res.has_anthropic_key,
        has_google_key: res.has_google_key,
        has_deepseek_key: res.has_deepseek_key,
        has_openrouter_key: res.has_openrouter_key,
      });
      toast.success("设置已保存");
      onOpenChange(false);
    } catch {
      toast.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const renderModelPresets = (
    currentValue: string,
    onSelect: (v: string) => void,
    groups: typeof MODEL_PRESET_GROUPS = MODEL_PRESET_GROUPS,
  ) => (
    <div className="space-y-2 mt-2">
      {groups.map((group) => {
        const enabled = providerStatus[group.hasKeyField];
        return (
          <div key={group.provider}>
            <p className="text-xs text-muted-foreground mb-1">{group.label}</p>
            <div className="flex flex-wrap gap-1.5">
              {group.presets.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => onSelect(p.value)}
                  disabled={!enabled}
                  className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                    currentValue === p.value
                      ? "bg-primary text-primary-foreground border-primary"
                      : enabled
                        ? "hover:bg-muted"
                        : "opacity-50 cursor-not-allowed"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>设置</DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <Tabs defaultValue="providers">
              <TabsList className="w-full">
                <TabsTrigger value="providers">服务商</TabsTrigger>
                <TabsTrigger value="models">模型</TabsTrigger>
              </TabsList>

              {/* 服务商 Tab */}
              <TabsContent value="providers" className="space-y-3 mt-3">
                <ProviderCard name="OpenAI" hasKey={providerStatus.has_openai_key}>
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
                    <p className="text-xs text-muted-foreground">
                      兼容 OpenAI 接口的服务可修改此地址
                    </p>
                  </div>
                </ProviderCard>

                <ProviderCard name="Anthropic" hasKey={providerStatus.has_anthropic_key}>
                  <KeyField
                    label="API Key"
                    value={anthropicKey}
                    onChange={setAnthropicKey}
                    provider="anthropic"
                    configured={providerStatus.has_anthropic_key}
                  />
                </ProviderCard>

                <ProviderCard name="Google" hasKey={providerStatus.has_google_key}>
                  <KeyField
                    label="API Key"
                    value={googleKey}
                    onChange={setGoogleKey}
                    provider="google"
                    placeholder="AIza..."
                    configured={providerStatus.has_google_key}
                  />
                </ProviderCard>

                <ProviderCard name="DeepSeek" hasKey={providerStatus.has_deepseek_key}>
                  <KeyField
                    label="API Key"
                    value={deepseekKey}
                    onChange={setDeepseekKey}
                    provider="deepseek"
                    placeholder="sk-..."
                    configured={providerStatus.has_deepseek_key}
                  />
                </ProviderCard>

                <ProviderCard name="OpenRouter" hasKey={providerStatus.has_openrouter_key}>
                  <KeyField
                    label="API Key"
                    value={openrouterKey}
                    onChange={setOpenrouterKey}
                    provider="openrouter"
                    placeholder="sk-or-..."
                    configured={providerStatus.has_openrouter_key}
                  />
                </ProviderCard>
              </TabsContent>

              {/* 模型 Tab */}
              <TabsContent value="models" className="space-y-4 mt-3">
                <div className="space-y-1.5">
                  <Label className="text-sm">默认模型</Label>
                  <Input
                    value={defaultModel}
                    onChange={(e) => setDefaultModel(e.target.value)}
                    placeholder="openai:gpt-4o-mini"
                  />
                  {renderModelPresets(defaultModel, setDefaultModel)}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm">高级模型</Label>
                  <Input
                    value={strongModel}
                    onChange={(e) => setStrongModel(e.target.value)}
                    placeholder="openai:gpt-4o"
                  />
                  {renderModelPresets(strongModel, setStrongModel)}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm">多模态模型</Label>
                  <Input
                    value={visionModel}
                    onChange={(e) => setVisionModel(e.target.value)}
                    placeholder="openai:gpt-4o-mini"
                  />
                  {renderModelPresets(visionModel, setVisionModel, VISION_MODEL_PRESET_GROUPS)}
                  <p className="text-xs text-muted-foreground mt-2">
                    用于视觉审美评估，需支持图片输入。格式: <code className="bg-muted px-1 rounded">provider:model-name</code>
                  </p>
                </div>
              </TabsContent>
            </Tabs>

            {/* 保存 */}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="w-full py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              保存设置
            </button>
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
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title="设置"
      >
        <Settings className="h-4 w-4" />
      </button>
      <SettingsDialogContent open={open} onOpenChange={setOpen} />
    </>
  );
}
