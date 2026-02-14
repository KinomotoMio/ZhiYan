"use client";

import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface RenameDialogProps {
  open: boolean;
  currentTitle: string;
  onConfirm: (newTitle: string) => void;
  onClose: () => void;
}

export default function RenameDialog({
  open,
  currentTitle,
  onConfirm,
  onClose,
}: RenameDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      {open ? (
        <RenameDialogBody
          currentTitle={currentTitle}
          onConfirm={onConfirm}
          onClose={onClose}
        />
      ) : null}
    </Dialog>
  );
}

function RenameDialogBody({
  currentTitle,
  onConfirm,
  onClose,
}: Omit<RenameDialogProps, "open">) {
  const [value, setValue] = useState(currentTitle);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, []);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (trimmed && trimmed !== currentTitle) {
      onConfirm(trimmed);
    }
    onClose();
  };

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>重命名会话</DialogTitle>
        <DialogDescription>输入新的会话名称</DialogDescription>
      </DialogHeader>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") handleSubmit();
        }}
        className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          取消
        </Button>
        <Button onClick={handleSubmit} disabled={!value.trim()}>
          确认
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
