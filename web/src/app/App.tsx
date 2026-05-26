import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { fetchRun, respondToRun } from "./api";
import type { RunSnapshot } from "./types";
import { ConfirmationHistory } from "../components/ConfirmationHistory";
import { DraftPreview } from "../components/DraftPreview";
import { EventTimeline } from "../components/EventTimeline";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { FieldStatusPanel } from "../components/FieldStatusPanel";
import { InteractionPanel } from "../components/InteractionPanel";
import { RunHeader } from "../components/RunHeader";
import "../styles/app.css";

const initialRunId = new URLSearchParams(window.location.search).get("run_id") || "run_cli";

export default function App() {
  const [runId, setRunId] = useState(initialRunId);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh(nextRunId = runId) {
    try {
      setError(null);
      setSnapshot(await fetchRun(nextRunId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSnapshot(null);
    }
  }

  async function respond(message: string) {
    if (!snapshot) return;
    try {
      setError(null);
      setSnapshot(await respondToRun(snapshot.run_id, message));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh(runId);
  }, [runId]);

  return (
    <main className="workbench">
      <RunHeader runId={runId} onRunIdChange={setRunId} snapshot={snapshot} onRefresh={() => refresh()} />
      {error ? <div className="error">{error}</div> : null}
      <section className="workbench-grid">
        <EventTimeline trace={snapshot?.trace ?? []} />
        <InteractionPanel interaction={snapshot?.pending_interaction ?? null} onRespond={respond} />
        <FieldStatusPanel fields={snapshot?.fields ?? {}} />
        <DraftPreview markdown={snapshot?.draft_markdown ?? ""} />
        <EvidenceDrawer report={snapshot?.field_report ?? {}} />
        <ConfirmationHistory confirmations={snapshot?.confirmations ?? []} />
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
