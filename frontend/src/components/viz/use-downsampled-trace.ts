import { useEffect, useMemo, useState } from "react";

export type TraceData = {
  x: number[];
  y: number[];
};

export function useDownsampledTrace(trace: TraceData, maxPoints = 8_000) {
  const [data, setData] = useState(trace);

  useEffect(() => {
    if (trace.x.length <= maxPoints) {
      setData(trace);
      return;
    }

    const worker = new Worker(new URL("./downsample.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<TraceData>) => setData(event.data);
    worker.postMessage({ ...trace, maxPoints });
    return () => worker.terminate();
  }, [maxPoints, trace]);

  return useMemo(() => data, [data]);
}
