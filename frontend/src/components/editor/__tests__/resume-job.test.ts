import assert from "node:assert/strict";
import test from "node:test";

import { resumeGenerationJob } from "@/components/editor/resume-job";

test("resumeGenerationJob calls getJob before runJob and returns normalized payload", async () => {
  const order: string[] = [];

  const result = await resumeGenerationJob("job-1", {
    getJobFn: async () => {
      order.push("getJob");
      return {
        job_id: "job-1",
        status: "failed",
        current_stage: "verify",
        events_seq: 42,
        request: {
          topic: "请基于以下内容生成一个关于人工智能对未来工作影响的10页PPT，需要适合管理层汇报。",
        },
        outline: {},
        layouts: [],
        slides: [],
        issues: [],
        failed_slide_indices: [],
        error: null,
      };
    },
    runJobFn: async () => {
      order.push("runJob");
      return {
        job_id: "job-1",
        status: "running",
        current_stage: "verify",
      };
    },
  });

  assert.deepEqual(order, ["getJob", "runJob"]);
  assert.equal(result.eventsSeq, 42);
  assert.equal(result.resumedStatus, "running");
  assert.equal(result.resumedStage, "verify");
  assert.equal(result.resumedJobId, "job-1");
  assert.equal(result.requestNumPages, 5);
  assert.equal(result.requestTitle, "人工智能对未来工作影响");
});

test("resumeGenerationJob keeps running flow when shell already exists (events_seq fallback)", async () => {
  const result = await resumeGenerationJob("job-2", {
    getJobFn: async () => ({
      job_id: "job-2",
      status: "failed",
      current_stage: "verify",
      request: {
        num_pages: 7,
        topic: "准备一个关于供应链优化的演示文稿，突出冷链、仓配协同和损耗控制。",
        title: "准备一个关于供应链优化的演示文稿，突出冷链、仓配协同和损耗控制。",
      },
      outline: {},
      layouts: [],
      slides: [],
      issues: [],
      failed_slide_indices: [],
      error: null,
    }),
    runJobFn: async () => ({
      job_id: "job-2",
      status: "running",
      current_stage: "verify",
    }),
  });

  assert.equal(result.eventsSeq, 0);
  assert.equal(result.resumedStatus, "running");
  assert.equal(result.requestNumPages, 7);
  assert.equal(result.requestTitle, "供应链优化");
});
