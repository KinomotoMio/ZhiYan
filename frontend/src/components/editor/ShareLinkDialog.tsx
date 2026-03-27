"use client";

import { Copy, ExternalLink, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ShareLinkDialogProps {
  open: boolean;
  shareUrl: string;
  loading?: boolean;
  onCopy: () => void;
  onClose: () => void;
}

export function ShareLinkDialogBody({
  shareUrl,
  loading = false,
  onCopy,
  onClose,
}: Omit<ShareLinkDialogProps, "open">) {
  return (
    <DialogContent className="max-w-xl border-slate-200 bg-white shadow-[0_26px_70px_-42px_rgba(15,23,42,0.65)]">
      <DialogHeader>
        <DialogTitle>分享播放链接</DialogTitle>
        <DialogDescription>
          这个链接会长期固定可用，访问者只能打开公开播放页，看到当前最新保存的演示内容。
        </DialogDescription>
      </DialogHeader>
      <ShareLinkDialogPanel shareUrl={shareUrl} loading={loading} onCopy={onCopy} onClose={onClose} />
    </DialogContent>
  );
}

export function ShareLinkDialogPanel({
  shareUrl,
  loading = false,
  onCopy,
  onClose,
}: Omit<ShareLinkDialogProps, "open">) {
  return (
    <>
      <div className="space-y-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          {loading ? (
            <div className="flex min-h-10 items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在生成分享链接...
            </div>
          ) : (
            <p className="break-all font-mono text-sm leading-6 text-slate-700">{shareUrl}</p>
          )}
        </div>
        <p className="text-xs leading-5 text-slate-500">
          你后续继续编辑并保存后，这个链接会自动展示最新版本，不需要重新分享。
        </p>
      </div>

      <DialogFooter className="sm:justify-between">
        <Button variant="outline" onClick={onClose}>
          关闭
        </Button>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onCopy} disabled={loading || !shareUrl}>
            <Copy className="h-4 w-4" />
            复制链接
          </Button>
          <Button
            onClick={() => {
              if (!shareUrl) return;
              window.open(shareUrl, "_blank", "noopener,noreferrer");
            }}
            disabled={loading || !shareUrl}
          >
            <ExternalLink className="h-4 w-4" />
            打开链接
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}

export default function ShareLinkDialog({
  open,
  shareUrl,
  loading = false,
  onCopy,
  onClose,
}: ShareLinkDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      {open ? (
        <ShareLinkDialogBody
          shareUrl={shareUrl}
          loading={loading}
          onCopy={onCopy}
          onClose={onClose}
        />
      ) : null}
    </Dialog>
  );
}
