import { FormEvent, useState } from "react";
import { sendFeedback } from "../api/client";
import type { ValidatedReport } from "../types/contracts";

export function FeedbackForm({ report }: { report: ValidatedReport }) {
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const verdict = form.get("verdict") as "correct" | "partially_correct" | "incorrect";
    await sendFeedback(report.analysisId, report.sections[0]?.id, verdict, comment);
    setMessage("Feedback recorded in SQLite.");
  }

  return (
    <form onSubmit={submit} className="feedback">
      <h3>Feedback</h3>
      <select name="verdict" defaultValue="correct">
        <option value="correct">Correct</option>
        <option value="partially_correct">Partially correct</option>
        <option value="incorrect">Incorrect</option>
      </select>
      <input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Optional comment" />
      <button type="submit">Submit feedback</button>
      {message && <span>{message}</span>}
    </form>
  );
}
