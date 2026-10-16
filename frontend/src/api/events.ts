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

        // Single-job cache
        queryClient.setQueryData(["job", job.id], job);

        // The app keeps ONE job list (queryKey ["jobs"]) and filters client-side,
        // so updating it in place (or prepending new jobs) is always correct.
        queryClient.setQueryData<Job[]>(["jobs"], (old) => {
          if (!old) return old; // not loaded yet — the next fetch will include it
          const exists = old.some((item) => item.id === job.id);
          if (!exists) return [job, ...old];
          return old.map((item) => (item.id === job.id ? job : item));
        });
      } catch (err) {
        console.error("Failed to parse job.updated event:", err);
      }
    });

    es.addEventListener("chapter.updated", (event) => {
      try {
        const ch = JSON.parse(event.data) as { id: string; project_id: string };
        queryClient.invalidateQueries({ queryKey: ["chapter", ch.id] });
        queryClient.invalidateQueries({ queryKey: ["pages", ch.id] });
        queryClient.invalidateQueries({ queryKey: ["frames", ch.id] });
        queryClient.invalidateQueries({ queryKey: ["chapters", ch.project_id] });
      } catch (err) {
        console.error("Failed to parse chapter.updated event:", err);
      }
    });

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [chapterId, queryClient]);

  return { isConnected };
}
