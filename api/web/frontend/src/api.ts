import type { RunCreated } from "./types";

export async function createRun(payload: unknown): Promise<RunCreated> {
  const response = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : "The 4M input needs a correction.");
  }
  return body;
}

export async function requestSignoff(runId: string, reviewer: string): Promise<void> {
  const response = await fetch(`/runs/${runId}/signoff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer })
  });
  if (!response.ok) {
    const body = await response.json();
    throw new Error(body.detail ?? "Sign-off did not complete.");
  }
}

