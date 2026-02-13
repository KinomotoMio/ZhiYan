import assert from "node:assert/strict";
import test from "node:test";

import type { ChatMessage } from "@/lib/store";
import {
  buildHistoryForApi,
  shouldDisableChatActions,
} from "@/components/chat/FloatingChatPanel";

test("buildHistoryForApi excludes current user message duplication", () => {
  const messages: ChatMessage[] = [
    { id: "u-1", role: "user", content: "请优化当前页", timestamp: 1 },
    { id: "a-1", role: "assistant", content: "好的，我来处理", timestamp: 2 },
    { id: "u-2", role: "user", content: "请优化当前页", timestamp: 3 },
    { id: "reply", role: "assistant", content: "", timestamp: 4 },
  ];
  const history = buildHistoryForApi(messages, "reply", "请优化当前页");
  assert.equal(history.length, 2);
  assert.deepEqual(history.map((m) => m.role), ["user", "assistant"]);
});

test("shouldDisableChatActions returns true when streaming or pending", () => {
  assert.equal(shouldDisableChatActions(true, false), true);
  assert.equal(shouldDisableChatActions(false, true), true);
  assert.equal(shouldDisableChatActions(false, false), false);
});

