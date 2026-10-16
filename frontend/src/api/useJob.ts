import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

/** Job state: pushed by SSE into ["job", id]; polling is only a fallback. */
export function useJob(jobId: string | null | undefined) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId as string),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && TERMINAL.has(q.state.data.status) ? false : 2000),
  });
}

