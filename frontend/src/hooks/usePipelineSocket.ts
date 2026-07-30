import { useEffect } from "react";
import { io } from "socket.io-client";
import { useProcessingStore } from "../stores/processingStore";
import { PipelineEvent } from "../types/processing";

export function usePipelineSocket() {
  const addLog = useProcessingStore((state) => state.addLog);
  const applyEvent = useProcessingStore((state) => state.applyEvent);
  const setStatus = useProcessingStore((state) => state.setStatus);

  useEffect(() => {
    const socket = io("http://localhost:3001");

    socket.on("connect", () => addLog("Connected to backend updates."));
    socket.on("pipeline:event", (event: PipelineEvent) => applyEvent(event));
    socket.on("pipeline:log", ({ message }: { message: string }) => addLog(message));
    socket.on("pipeline:error", ({ message }: { message: string }) => {
      addLog(message);
      setStatus("failed");
    });
    socket.on("pipeline:exit", ({ code }: { code: number | null }) => {
      if (code === 0) {
        setStatus("complete");
      } else if (code !== null) {
        setStatus("failed");
      }
    });
    socket.on("pipeline:cancelled", ({ jobId }: { jobId: string }) => {
      addLog(`Cancelled ${jobId}.`);
      setStatus("cancelled");
    });

    return () => {
      socket.disconnect();
    };
  }, [addLog, applyEvent, setStatus]);
}
