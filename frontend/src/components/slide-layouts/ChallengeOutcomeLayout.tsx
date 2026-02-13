"use client";

import { AlertTriangle, CheckCircle } from "lucide-react";
import type { ChallengeOutcomeData } from "@/types/layout-data";

export const layoutId = "challenge-outcome";
export const layoutName = "问题→方案";
export const layoutDescription = "挑战和解决方案对比，适合痛点分析、项目成果";

export default function ChallengeOutcomeLayout({ data }: { data: ChallengeOutcomeData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-8">
        {data.title}
      </h2>
      <div className="flex-1 flex flex-col gap-5 justify-center">
        {data.items.map((item, i) => (
          <div key={i} className="flex items-stretch gap-4">
            <div className="flex-1 rounded-xl bg-red-50 p-5 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
              <span style={{ fontSize: 17, lineHeight: 1.5 }} className="text-red-700/80">{item.challenge}</span>
            </div>
            <div className="flex items-center shrink-0">
              <div className="w-8 h-0.5 bg-[var(--primary-color,#3b82f6)]/30" />
              <div className="w-0 h-0 border-y-4 border-y-transparent border-l-8 border-l-[var(--primary-color,#3b82f6)]/30" />
            </div>
            <div className="flex-1 rounded-xl bg-green-50 p-5 flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-green-500 mt-0.5 shrink-0" />
              <span style={{ fontSize: 17, lineHeight: 1.5 }} className="text-green-700/80">{item.outcome}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
