import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Job } from "./client";

export function useEvents(chapterId?: string) {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const url = chapterId
      ? `/api/events?chapter_id=${encodeURIComponent(chapterId)}`
      : "/api/events";
    const es = new EventSource(url);

    es.onopen = () => {
      setIsConnected(true);
      // N2: on reconnect, invalidate job list to sync missed events
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    };

    es.onerror = () => {
      setIsConnected(false);
    };

    es.addEventListener("job.updated", (event) => {
      try {
        const job = JSON.parse(event.data) as Job;

        // N3: update individual job cache entry
        queryClient.setQueryData(["job", job.id], job);

        // N3: update list queries — insert only if the job matches the filter,
        // or update in-place if it already exists in that list.
        // Strategy: update in-place for all lists; invalidate filtered lists so they re-fetch.
        queryClient.setQueriesData<Job[]>({ queryKey: ["jobs"] }, (old) => {
          if (!old) return [job];
          const existsAt = old.findIndex((item) => item.id === job.id);
          if (existsAt >= 0) {
            // Job already in this list — update it in-place (always safe)
            return old.map((item) => (item.id === job.id ? job : item));
          }
          // N3: job is NOT in this list. Only prepend if the list is unfiltered
          // (queryKey is exactly ["jobs"] with no extra filter key).
          // We detect "unfiltered" by checking the cache key length.
          return old;
        });

        // For the canonical unfiltered list, prepend new jobs that don't exist yet
        queryClient.setQueryData<Job[]>(["jobs"], (old) => {
          if (!old) return [job];
          const exists = old.some((item) => item.id === job.id);
          if (!exists) return [job, ...old];
          return old.map((item) => (item.id === job.id ? job : item));
        });
      } catch (err) {
        console.error("Failed to parse job.updated event:", err);
      }
    });

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [chapterId, queryClient]);

  return { isConnected };
}
