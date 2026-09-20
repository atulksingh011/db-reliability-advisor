import { useEffect, useState } from "react";
import { getHealth, runScenario } from "./api/client";
import { FeedbackForm } from "./components/FeedbackForm";
import { ReportView } from "./components/ReportView";
import type { ValidatedReport } from "./types/contracts";
import "./styles.css";

export default function App() {
  const [health, setHealth] = useState("checking");
  const [report, setReport] = useState<ValidatedReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { getHealth().then(setHealth).catch(() => setHealth("unavailable")); }, []);

  async function run(scenario: "query-regression" | "connection-pressure") {
    setBusy(true);
    setError("");
    try { setReport(await runScenario(scenario)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Request failed"); }
    finally { setBusy(false); }
  }

  return (
    <main>
      <header className="masthead">
        <div>
          <p className="eyebrow">Mock-first foundation</p>
          <h1>Database Reliability Advisor</h1>
          <p>Backend health: <strong>{health}</strong></p>
        </div>
        <div className="actions">
          <button disabled={busy} onClick={() => run("query-regression")}>Run query regression</button>
          <button disabled={busy} onClick={() => run("connection-pressure")}>Run connection pressure</button>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {busy && <p>Running the shared analysis pipeline…</p>}
      {report ? <><ReportView report={report} /><FeedbackForm report={report} /></> : (
        <div className="empty">Choose a mock scenario. No Gemini credentials are required.</div>
      )}
    </main>
  );
}
