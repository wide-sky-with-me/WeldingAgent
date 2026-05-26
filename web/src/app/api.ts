import type { RunSnapshot } from "./types";

export async function fetchRun(runId: string): Promise<RunSnapshot> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function respondToRun(runId: string, message: string): Promise<RunSnapshot> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/respond`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}
