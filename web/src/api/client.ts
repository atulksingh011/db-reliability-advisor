import type { ValidatedReport } from "../types/contracts";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return response;
}
export async function getHealth(): Promise<string> {
  const response = await checked(await fetch(`${API_URL}/health`));
  const body = await response.json();
  return body.status;
}

export async function runScenario(
  scenario: "query-regression" | "connection-pressure",
): Promise<ValidatedReport> {
  const response = await checked(
    await fetch(`${API_URL}/api/v1/dev/mock/${scenario}`, { method: "POST" }),
  );
  return response.json();
}

export async function sendFeedback(
  analysisId: string,
  findingId: string | undefined,
  verdict: "correct" | "partially_correct" | "incorrect",
  comment: string,
): Promise<void> {
  await checked(
    await fetch(`${API_URL}/api/v1/analyses/${analysisId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysisId, findingId, verdict, comment }),
    }),
  );
}
