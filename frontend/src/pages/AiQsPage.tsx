import { useState } from "react";

import { runAIQuery } from "../api/ingestion";
import type { AIQueryResponse } from "../types/ingestion";

export function AiQsPage() {
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiResult, setAiResult] = useState<AIQueryResponse | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [showRawAiData, setShowRawAiData] = useState(false);

  async function handleRunAIQuery() {
    if (!aiQuestion.trim()) {
      setAiError("Enter a question for the AI assistant.");
      return;
    }

    setBusyAction("ai-query");
    setAiError(null);
    setAiResult(null);
    setShowRawAiData(false);
    try {
      const result = await runAIQuery(aiQuestion.trim());
      setAiResult(result);
    } catch (error) {
      setAiError(error instanceof Error ? error.message : "AI query failed.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <>
      <section className="hero">
        <div className="hero-card">
          <div className="hero-kicker">Natural language SQL</div>
          <h1>AI QS Assistant</h1>
          <p>
            Ask natural-language benchmarking questions, inspect the generated SQL, and review
            query results in one dedicated page.
          </p>
        </div>
      </section>

      <section className="section-grid">
        <section className="section-card span-12">
          <div className="section-header">
            <div>
              <h2 className="section-title">AI SQL Assistant</h2>
              <p className="section-subtitle">
                Ask a natural-language question, review generated SQL, and inspect query results.
              </p>
            </div>
          </div>

          <div className="field-stack">
            <label className="field-label" htmlFor="ai-question">
              Question
            </label>
            <div className="ai-question-compose">
              <textarea
                id="ai-question"
                className="text-input ai-textarea ai-textarea-compose"
                placeholder="e.g. Show top 10 Level2 elements by total cost"
                value={aiQuestion}
                onChange={(event) => setAiQuestion(event.target.value)}
              />
              <button
                className="ai-submit-button ai-submit-button-inline"
                onClick={() => void handleRunAIQuery()}
                disabled={busyAction === "ai-query"}
                aria-label={busyAction === "ai-query" ? "Running query" : "Submit query"}
                title={busyAction === "ai-query" ? "Running..." : "Submit query"}
              >
                {busyAction === "ai-query" ? "…" : "↑"}
              </button>
            </div>
          </div>

          {aiError ? <div className="message-error">{aiError}</div> : null}

          {aiResult ? (
            <>
              <div className="summary-grid" style={{ marginTop: "18px" }}>
                <div className="summary-item">
                  <span className="summary-item-label">Question</span>
                  <span className="summary-item-value">{aiResult.question}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-item-label">Rows returned</span>
                  <span className="summary-item-value">{aiResult.row_count}</span>
                </div>
              </div>

              {aiResult.truncated ? (
                <p style={{ marginTop: "12px", color: "var(--muted, #5c6570)" }}>
                  Showing first {aiResult.row_count} rows (result was truncated).
                </p>
              ) : null}

              <div className="summary-item" style={{ marginTop: "12px" }}>
                <span className="summary-item-label">AI answer</span>
                <span className="summary-item-value">{aiResult.answer_text}</span>
              </div>

              <details className="row-data-details" style={{ marginTop: "12px" }}>
                <summary>Generated SQL</summary>
                <pre className="row-data-pre">{aiResult.generated_sql}</pre>
              </details>

              <div className="action-row" style={{ marginTop: "12px" }}>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => setShowRawAiData((prev) => !prev)}
                >
                  {showRawAiData ? "Hide raw data" : "Show raw data"}
                </button>
              </div>

              {showRawAiData ? (
                aiResult.rows.length > 0 ? (
                  <div className="table-wrap" style={{ marginTop: "12px" }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          {Object.keys(aiResult.rows[0]).map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {aiResult.rows.map((row, idx) => (
                          <tr key={idx}>
                            {Object.keys(aiResult.rows[0]).map((col) => (
                              <td key={`${idx}-${col}`}>{String(row[col] ?? "")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="message-muted" style={{ marginTop: "12px" }}>
                    Query ran successfully but returned no rows.
                  </p>
                )
              ) : null}
            </>
          ) : null}
        </section>
      </section>
    </>
  );
}
