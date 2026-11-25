export function normalizedProgress(loaded,total) {
  if(!Number.isFinite(loaded)||!Number.isFinite(total)||total<=0)return null;
  return Math.max(0,Math.min(1,loaded/total));
}
export function loadingLabel(progress) {
  if(!Number.isFinite(progress))return 'Loading geometry…';
  const percent=Math.max(0,Math.min(100,Math.floor(progress*100)));
  return percent===100?'Loading geometry · 100% · preparing scene…':`Loading geometry · ${percent}%`;
}
