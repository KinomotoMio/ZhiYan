"use client";

import { useState, useEffect, useCallback } from "react";
import { getSettings } from "@/lib/api";

type SettingsStatus = "loading" | "configured" | "unconfigured" | "error";

export function useSettingsStatus() {
  const [status, setStatus] = useState<SettingsStatus>("loading");
  const [message, setMessage] = useState("");
  const [refreshTick, setRefreshTick] = useState(1);

  const refresh = useCallback(() => {
    setStatus("loading");
    setMessage("");
    setRefreshTick((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((s) => {
        if (cancelled) return;
        if (s.default_model_status?.ready) {
          setStatus("configured");
          setMessage("默认模型可用");
        } else {
          setStatus("unconfigured");
          setMessage(
            s.default_model_status?.message || "默认模型当前不可用，请检查设置"
          );
        }
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
        setMessage("加载设置失败");
      });

    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  useEffect(() => {
    const onUpdated = () => refresh();
    window.addEventListener("settings:updated", onUpdated);
    return () => window.removeEventListener("settings:updated", onUpdated);
  }, [refresh]);

  return { status, message, refresh };
}
