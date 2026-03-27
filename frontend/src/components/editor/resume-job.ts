import { getJob, runJob } from "@/lib/api";
import { resolveGenerationRequestTitle } from "@/lib/loading-title";

export interface ResumeGenerationJobResult {
  eventsSeq: number;
  resumedStatus: string;
  resumedStage: string | null;
  resumedJobId: string;
  requestNumPages: number;
  requestTitle: string;
}

export async function resumeGenerationJob(
  sessionId: string,
  jobId: string,
  deps?: {
    getJobFn?: typeof getJob;
    runJobFn?: typeof runJob;
  }
): Promise<ResumeGenerationJobResult> {
  const getJobFn = deps?.getJobFn ?? getJob;
  const runJobFn = deps?.runJobFn ?? runJob;

  const latest = await getJobFn(sessionId, jobId);
  const resumed = await runJobFn(sessionId, jobId);
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
      resolveGenerationRequestTitle(latest.request),
  };
}
