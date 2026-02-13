"use client";

import type { TableInfoData } from "@/types/layout-data";

export const layoutId = "table-info";
export const layoutName = "表格数据";
export const layoutDescription = "结构化表格展示，适合对比、参数、功能矩阵";

export default function TableInfoLayout({ data }: { data: TableInfoData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-8">
        {data.title}
      </h2>
      <div className="flex-1 flex flex-col">
        <div className="rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--primary-color,#3b82f6)]">
                {data.headers.map((h, i) => (
                  <th key={i} style={{ fontSize: 16, fontWeight: 600, padding: "14px 20px" }} className="text-[var(--primary-text,#ffffff)] text-left">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  {row.map((cell, j) => (
                    <td key={j} style={{ fontSize: 15, padding: "12px 20px" }} className="text-[var(--background-text,#111827)]/80 border-t border-gray-100">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.caption && (
          <p style={{ fontSize: 13 }} className="text-[var(--background-text,#111827)]/40 mt-3 text-center">
            {data.caption}
          </p>
        )}
      </div>
    </div>
  );
}
