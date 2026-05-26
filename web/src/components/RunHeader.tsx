import { RefreshCw } from "lucide-react";
import type { RunSnapshot } from "../app/types";

export function RunHeader({
  runId,
  onRunIdChange,
  snapshot,
  onRefresh
}: {
  runId: string;
  onRunIdChange: (runId: string) => void;
  snapshot: RunSnapshot | null;
  onRefresh: () => void;
}) {
  return (
    <header className="run-header">
      <div className="run-title">
        <span className="eyebrow">pWPS Agent Workbench</span>
        <h1>焊接工艺草案运行台</h1>
      </div>
      <label className="run-id-control">
        <span>Run ID</span>
        <input value={runId} onChange={(event) => onRunIdChange(event.target.value)} />
      </label>
      <div className="status-cluster">
        <span className={`status-chip status-${snapshot?.status ?? "unknown"}`}>
          {snapshot?.status ?? "not loaded"}
        </span>
        <span className="mode-chip">{snapshot?.mode ?? "mode unknown"}</span>
      </div>
      <button className="icon-button" type="button" onClick={onRefresh} aria-label="刷新运行状态">
        <RefreshCw size={17} />
      </button>
    </header>
  );
}
