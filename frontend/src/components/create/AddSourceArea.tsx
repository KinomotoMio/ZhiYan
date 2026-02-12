"use client";

import { useRef, useState } from "react";
import { Plus, Link } from "lucide-react";

const ACCEPTED_TYPES = ".pdf,.doc,.docx,.pptx,.ppt,.md,.markdown,.txt,.csv,.json,.png,.jpg,.jpeg,.gif,.webp";

interface AddSourceAreaProps {
  onFilesSelected: (files: File[]) => void;
  onUrlSubmit: (url: string) => void;
}

export default function AddSourceArea({
  onFilesSelected,
  onUrlSubmit,
}: AddSourceAreaProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [urlValue, setUrlValue] = useState("");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFilesSelected(files);
    e.target.value = "";
  };

  const handleUrlSubmit = () => {
    const trimmed = urlValue.trim();
    if (!trimmed) return;
    onUrlSubmit(trimmed);
    setUrlValue("");
    setShowUrlInput(false);
  };

  const handleUrlKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleUrlSubmit();
    if (e.key === "Escape") {
      setShowUrlInput(false);
      setUrlValue("");
    }
  };

  return (
    <div className="space-y-2">
      {/* 添加文件按钮 */}
      <button
        onClick={() => fileInputRef.current?.click()}
        className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border px-4 py-3 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
      >
        <Plus className="h-4 w-4" />
        添加来源
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES}
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* URL 输入 */}
      {showUrlInput ? (
        <div className="flex gap-2">
          <input
            type="url"
            value={urlValue}
            onChange={(e) => setUrlValue(e.target.value)}
            onKeyDown={handleUrlKeyDown}
            placeholder="https://..."
            className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            autoFocus
          />
          <button
            onClick={handleUrlSubmit}
            disabled={!urlValue.trim()}
            className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
          >
            添加
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowUrlInput(true)}
          className="flex w-full items-center justify-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <Link className="h-3 w-3" />
          或粘贴网址链接
        </button>
      )}
    </div>
  );
}
