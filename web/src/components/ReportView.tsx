import type { ValidatedReport } from "../types/contracts";

export function ReportView({ report }: { report: ValidatedReport }) {
  return (
    <article className="report">
      <header>
        <span className={`status ${report.status}`}>{report.status}</span>
        <h2>{report.summary}</h2>
        <p className="muted">{report.analysisId} · {report.target}</p>
      </header>
      {report.sections.map((section) => (
        <section key={section.id}>
          <h3>{section.title}</h3>
          <h4>Grounded facts</h4>
          <ul>
            {section.facts.map((fact) => (
              <li key={fact.text}>
                {fact.text} <small>[{[...fact.evidenceIds, ...fact.deterministicFindingIds].join(", ")}]</small>
              </li>
            ))}
          </ul>
          <div className="hypothesis">
            <strong>Hypothesis · {section.hypothesis.confidence} confidence</strong>
            <p>{section.hypothesis.text}</p>
          </div>
          <h4>Recommended checks</h4>
          <ul>{section.recommendedChecks.map((check) => <li key={check}>{check}</li>)}</ul>
          <h4>Limitations</h4>
          <ul>{section.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          <details>
            <summary>Verification queries</summary>
            {section.verification.map((query) => (
              <pre key={query.query}>{query.system}: {query.query}</pre>
            ))}
          </details>
        </section>
      ))}
      <aside><strong>Report limitations:</strong> {report.limitations.join(" ")}</aside>
    </article>
  );
}
