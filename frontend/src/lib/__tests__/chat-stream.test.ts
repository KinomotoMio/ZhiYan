import assert from "node:assert/strict";
import test from "node:test";

import { chatStream } from "@/lib/api";

test("chatStream parses assistant status and tool events", async () => {
  const originalFetch = globalThis.fetch;
  const encoder = new TextEncoder();
  const chunks: string[] = [];
  const statuses: string[] = [];
  const toolCalls: string[] = [];
  const toolResults: string[] = [];
  let done = false;

  globalThis.fetch = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode(
              [
                'data: {"type":"assistant_status","assistant_status":"thinking"}\n',
                'data: {"type":"tool_call","tool_name":"get_current_slide_info","call_id":"call-1","summary":"读取当前页详细结构"}\n',
                'data: {"type":"tool_result","tool_name":"get_current_slide_info","call_id":"call-1","ok":true,"summary":"已读取所需上下文"}\n',
                'data: {"type":"text","content":"最终回复"}\n',
                "data: [DONE]\n",
              ].join("\n")
            )
          );
          controller.close();
        },
      })
    );

  try {
    await chatStream(
      {
        message: "你好",
        action_hint: "free_text",
      },
      (chunk) => chunks.push(chunk),
      () => {
        done = true;
      },
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      (event) => statuses.push(event.assistant_status),
      (event) => toolCalls.push(event.summary),
      (event) => toolResults.push(event.summary)
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(statuses, ["thinking"]);
  assert.deepEqual(toolCalls, ["读取当前页详细结构"]);
  assert.deepEqual(toolResults, ["已读取所需上下文"]);
  assert.deepEqual(chunks, ["最终回复"]);
  assert.equal(done, true);
});
