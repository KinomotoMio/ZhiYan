import assert from "node:assert/strict";
import test from "node:test";

import { buildJobEventsUrl } from "@/lib/api";

test("buildJobEventsUrl omits after_seq by default", () => {
  const url = buildJobEventsUrl("job-123");
  assert.equal(url.endsWith("/api/v2/generation/jobs/job-123/events"), true);
});

test("buildJobEventsUrl appends after_seq when positive", () => {
  const url = buildJobEventsUrl("job-123", 12);
  assert.match(url, /after_seq=12$/);
});

test("buildJobEventsUrl normalizes invalid after_seq", () => {
  const url = buildJobEventsUrl("job-123", -9);
  assert.equal(url.endsWith("/api/v2/generation/jobs/job-123/events"), true);
});
