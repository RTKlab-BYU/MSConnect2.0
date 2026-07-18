type DownsampleRequest = {
  x: number[];
  y: number[];
  maxPoints: number;
};

function minMaxDownsample({ x, y, maxPoints }: DownsampleRequest) {
  if (x.length <= maxPoints || maxPoints < 4) return { x, y };

  const bucketSize = Math.ceil(x.length / Math.max(1, maxPoints / 2));
  const nextX: number[] = [];
  const nextY: number[] = [];

  for (let start = 0; start < x.length; start += bucketSize) {
    const end = Math.min(start + bucketSize, x.length);
    let minIndex = start;
    let maxIndex = start;
    for (let index = start + 1; index < end; index += 1) {
      if (y[index] < y[minIndex]) minIndex = index;
      if (y[index] > y[maxIndex]) maxIndex = index;
    }
    const first = minIndex < maxIndex ? minIndex : maxIndex;
    const second = minIndex < maxIndex ? maxIndex : minIndex;
    nextX.push(x[first], x[second]);
    nextY.push(y[first], y[second]);
  }

  return { x: nextX, y: nextY };
}

self.onmessage = (event: MessageEvent<DownsampleRequest>) => {
  self.postMessage(minMaxDownsample(event.data));
};
