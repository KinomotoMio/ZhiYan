"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Pencil } from "lucide-react";

interface SessionTitleInlineEditorProps {
  title: string;
  onSave: (nextTitle: string) => Promise<void>;
  className?: string;
  disabled?: boolean;
}

export default function SessionTitleInlineEditor({
  title,
  onSave,
  className = "",
  disabled = false,
}: SessionTitleInlineEditorProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState(title);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!isEditing) {
      setValue(title);
    }
  }, [isEditing, title]);

  useEffect(() => {
    if (!isEditing) return;
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [isEditing]);

  const handleBlur = async () => {
    if (cancelledRef.current) {
      cancelledRef.current = false;
      setValue(title);
      setIsEditing(false);
      return;
    }

    const nextTitle = value.trim();
    setIsEditing(false);
    if (!nextTitle || nextTitle === title) {
      setValue(title);
      return;
    }

    setSaving(true);
    try {
      await onSave(nextTitle);
    } finally {
      setSaving(false);
    }
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => {
          void handleBlur();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            inputRef.current?.blur();
          }
          if (event.key === "Escape") {
            event.preventDefault();
            cancelledRef.current = true;
            inputRef.current?.blur();
          }
        }}
        className={`h-8 min-w-0 rounded-md border border-cyan-300 bg-white px-2.5 text-sm font-semibold text-slate-800 outline-none ring-2 ring-cyan-500/20 ${className}`}
      />
    );
  }

  return (
    <button
      type="button"
      onDoubleClick={() => {
        if (!disabled && !saving) setIsEditing(true);
      }}
      disabled={disabled || saving}
      title="双击重命名会话"
      className={`group inline-flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-left transition-colors hover:bg-slate-100 disabled:cursor-default disabled:hover:bg-transparent ${className}`}
    >
      <span className="min-w-0 truncate text-sm font-semibold text-slate-800">
        {title}
      </span>
      {saving ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-slate-400" />
      ) : (
        <Pencil className="h-3.5 w-3.5 shrink-0 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100" />
      )}
    </button>
  );
}
