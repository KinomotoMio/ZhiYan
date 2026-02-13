"use client";

import { AlertTriangle } from "lucide-react";

interface LayoutErrorFallbackProps {
  layoutId: string;
  reason?: string | null;
}

export default function LayoutErrorFallback({ layoutId, reason }: LayoutErrorFallbackProps) {
  return (
    <div
      style={{ width: 1280, height: 720, transformOrigin: "top left" }}
      className="bg-white flex items-center justify-center"
    >
      <div className="w-[760px] rounded-2xl border border-amber-200 bg-amber-50/70 p-10 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-600">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <h3 className="text-xl font-semibold text-amber-900">该页数据异常，可重新生成</h3>
        <p className="mt-2 text-sm text-amber-800/90">
          布局: {layoutId}
          {reason ? ` | 原因: ${reason}` : ""}
        </p>
      </div>
    </div>
  );
}
