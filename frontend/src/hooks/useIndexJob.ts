import { useEffect, useState } from "react";

import { api, ApiError, type IndexJob } from "../api";

const POLL_MS = 700;

/**
 * Polls an indexing job until it reaches a final state. `seed` is the snapshot returned when the job
 * was started, shown until the first poll lands.
 */
export function useIndexJob(jobId: string | null, seed: IndexJob | null) {
  const [job, setJob] = useState<IndexJob | null>(seed);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    setJob(seed);
    setUnreachable(false);
    if (!jobId) return;

    let stopped = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const next = await api.getIndexJob(jobId);
        if (stopped) return;
        setJob(next);
        setUnreachable(false);
        if (next.status !== "running") return;
      } catch (err) {
        if (stopped) return;
        if (err instanceof ApiError && err.code === "job_not_found") {
          // The API restarted mid-run (jobs live in memory); nothing will finish it now.
          setJob((prev) =>
            prev && { ...prev, status: "error", error: "The indexing run was interrupted because the API restarted." },
          );
          return;
        }
        setUnreachable(true); // keep polling; the backend banner explains what's wrong
      }
      timer = window.setTimeout(tick, POLL_MS);
    };

    timer = window.setTimeout(tick, POLL_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [jobId, seed]);

  // State from a previous job can linger for one render after jobId changes; never expose it, or a
  // finished earlier run would be mistaken for the new one.
  return { job: job && job.id === jobId ? job : null, unreachable };
}
