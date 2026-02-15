import { getJob, runJob } from "@/lib/api";

export interface ResumeGenerationJobResult {
  eventsSeq: number;
  resumedStatus: string;
  resumedStage: string | null;
  resumedJobId: string;
  requestNumPages: number;
  requestTitle: string;
}

export async function resumeGenerationJob(
  jobId: string,
  deps?: {
    getJobFn?: typeof getJob;
    runJobFn?: typeof runJob;
  }
): Promise<ResumeGenerationJobResult> {
  const getJobFn = deps?.getJobFn ?? getJob;
  const runJobFn = deps?.runJobFn ?? runJob;

  const latest = await getJobFn(jobId);
  const resumed = await runJobFn(jobId);
  return {
    eventsSeq: typeof latest.events_seq === "number" ? latest.events_seq : 0,
    resumedStatus: resumed.status,
    resumedStage: resumed.current_stage,
    resumedJobId: resumed.job_id,
    requestNumPages:
      typeof latest.request?.num_pages === "number"
        ? Math.max(1, Math.trunc(latest.request.num_pages))
        : 5,
    requestTitle:
      typeof latest.request?.title === "string" && latest.request.title.trim()
        ? latest.request.title
        : "生成中...",
  };
}
