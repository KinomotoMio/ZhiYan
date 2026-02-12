"use client";

import { useState, useEffect, useCallback } from "react";
import { getSettings } from "@/lib/api";

type SettingsStatus = "loading" | "configured" | "unconfigured" | "error";

export function useSettingsStatus() {
  const [status, setStatus] = useState<SettingsStatus>("loading");

  const refresh = useCallback(() => {
    setStatus("loading");
    getSettings()
      .then((s) => {
        if (
          s.has_openai_key ||
          s.has_anthropic_key ||
          s.has_google_key ||
          s.has_deepseek_key ||
          s.has_openrouter_key
        ) {
          setStatus("configured");
        } else {
          setStatus("unconfigured");
        }
      })
      .catch(() => {
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { status, refresh };
}
