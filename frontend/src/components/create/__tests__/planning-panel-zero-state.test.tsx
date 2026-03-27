import assert from "node:assert/strict";
import test from "node:test";

import { shouldShowTopicSuggestionTemplate } from "@/components/create/PlanningPanel";
import type { ChatMessage } from "@/lib/store";

const assistantMessage: ChatMessage = {
  id: "a-1",
  role: "assistant",
  content: "我可以先给你几个方向。",
  timestamp: 1,
  phase: "planning",
};

const userMessage: ChatMessage = {
  id: "u-1",
  role: "user",
  content: "先讲现状问题吧",
  timestamp: 2,
  phase: "planning",
};

test("shows topic suggestion template only in true zero state", () => {
  assert.equal(
    shouldShowTopicSuggestionTemplate({
      selectedSourceCount: 0,
      planningMessages: [assistantMessage],
      hasOutline: false,
      isGeneratingPhase: false,
    }),
    true
  );
});

test("hides topic suggestion template after selecting sources", () => {
  assert.equal(
    shouldShowTopicSuggestionTemplate({
      selectedSourceCount: 1,
      planningMessages: [assistantMessage],
      hasOutline: false,
      isGeneratingPhase: false,
    }),
    false
  );
});

test("hides topic suggestion template after first user turn", () => {
  assert.equal(
    shouldShowTopicSuggestionTemplate({
      selectedSourceCount: 0,
      planningMessages: [assistantMessage, userMessage],
      hasOutline: false,
      isGeneratingPhase: false,
    }),
    false
  );
});

test("hides topic suggestion template once outline exists or generation starts", () => {
  assert.equal(
    shouldShowTopicSuggestionTemplate({
      selectedSourceCount: 0,
      planningMessages: [assistantMessage],
      hasOutline: true,
      isGeneratingPhase: false,
    }),
    false
  );
  assert.equal(
    shouldShowTopicSuggestionTemplate({
      selectedSourceCount: 0,
      planningMessages: [assistantMessage],
      hasOutline: false,
      isGeneratingPhase: true,
    }),
    false
  );
});

test("keeps topic suggestion template hidden after it has been dismissed in-session", () => {
  assert.equal(
    shouldShowTopicSuggestionTemplate({
      selectedSourceCount: 0,
      planningMessages: [assistantMessage],
      hasOutline: false,
      isGeneratingPhase: false,
      hasBeenDismissed: true,
    }),
    false
  );
});
