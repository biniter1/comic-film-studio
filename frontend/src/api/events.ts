import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Job } from "./client";

export function useEvents(chapterId?: string) {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const url = chapterId ? `/api/events?chapter_id=${encodeURIComponent(chapterId)}` : "/api/events";
    const es = new EventSource(url);

    es.onopen = () => {
      setIsConnected(true);
    };

    es.onerror = () => {
      setIsConnected(false);
    };

    es.addEventListener("job.updated", (event) => {
      try {
        const job = JSON.parse(event.data) as Job;
        // Update any queries matching ['jobs']
        queryClient.setQueriesData<Job[]>({ queryKey: ["jobs"] }, (old) => {
          if (!old) return [job];
          const exists = old.some((item) => item.id === job.id);
          if (exists) {
            return old.map((item) => (item.id === job.id ? job : item));
          }
          return [job, ...old];
        });

        // Update single job query
        queryClient.setQueryData(["job", job.id], job);
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
