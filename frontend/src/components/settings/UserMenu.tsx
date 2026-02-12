"use client";

import { useState } from "react";
import { Settings, LogOut, User } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { SettingsDialogContent } from "./SettingsDialog";
import { useSettingsStatus } from "@/hooks/useSettingsStatus";

interface UserMenuProps {
  compact?: boolean;
}

export default function UserMenu({ compact }: UserMenuProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { status, message, refresh } = useSettingsStatus();
  const needsSetup = status === "unconfigured";

  const handleSettingsClose = (open: boolean) => {
    setSettingsOpen(open);
    if (!open) refresh();
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          {compact ? (
            <button
              type="button"
              className="relative p-1 rounded-full hover:bg-muted transition-colors"
            >
              <Avatar className="h-7 w-7">
                <AvatarFallback className="text-xs bg-muted">
                  <User className="h-3.5 w-3.5" />
                </AvatarFallback>
              </Avatar>
              {needsSetup && (
                <span className="absolute top-0 right-0 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-background" />
              )}
            </button>
          ) : (
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-muted transition-colors"
            >
              <div className="relative shrink-0">
                <Avatar className="h-8 w-8">
                  <AvatarFallback className="text-xs bg-muted">
                    <User className="h-4 w-4" />
                  </AvatarFallback>
                </Avatar>
                {needsSetup && (
                  <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-background" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">未登录用户</p>
                {needsSetup && (
                  <p className="truncate text-xs text-amber-600 dark:text-amber-400">
                    {message || "默认模型未就绪"}
                  </p>
                )}
              </div>
            </button>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side={compact ? "bottom" : "top"}
          align={compact ? "end" : "start"}
          className="w-48"
        >
          <DropdownMenuItem onSelect={() => setSettingsOpen(true)}>
            <Settings className="mr-2 h-4 w-4" />
            设置
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled>
            <LogOut className="mr-2 h-4 w-4" />
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <SettingsDialogContent open={settingsOpen} onOpenChange={handleSettingsClose} />
    </>
  );
}
