import { useMemo, useState } from "react";

import {
  getBatchErrorCounts,
  getBatchErrorRows,
  getBatchSummary,
  getErrorDownloadUrl,
  uploadWorkbookWithProgress,
} from "../api/ingestion";
import { StatusBadge } from "../components/StatusBadge";
import type {
  BatchSummary,
  IngestionRunResponse,
  ValidationErrorCount,
  ValidationErrorRow,
} from "../types/ingestion";
import {
  severityLabel,
  toFriendlyErrorMessage,
} from "../utils/validationErrors";

export function IngestionPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<IngestionRunResponse | null>(null);
  const [summary, setSummary] = useState<BatchSummary | null>(null);
  const [errorCounts, setErrorCounts] = useState<ValidationErrorCount[]>([]);
  const [errorDetails, setErrorDetails] = useState<ValidationErrorRow[]>([]);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  const activeBatchId = useMemo(() => uploadResult?.load_batch_id || "", [uploadResult]);
  const currentStatus = summary?.BatchStatus ?? uploadResult?.status ?? "Not started";

  async function loadBatchData(loadBatchId: string) {
    const [summaryResult, countsResult, detailsResult] = await Promise.all([
      getBatchSummary(loadBatchId),
      getBatchErrorCounts(loadBatchId),
      getBatchErrorRows(loadBatchId),
    ]);
    setSummary(summaryResult);
    setErrorCounts(countsResult);
    setErrorDetails(detailsResult);
  }

  async function handleUpload() {
    if (!selectedFile) {
      setErrorMessage("Choose an Excel file before uploading.");
      return;
    }

    setBusyAction("upload");
    setErrorMessage(null);
    setUploadProgress(0);
    setUploadResult(null);
    setSummary(null);
    setErrorCounts([]);
    setErrorDetails([]);
    try {
      const result = await uploadWorkbookWithProgress(selectedFile, setUploadProgress);
      setUploadResult(result);
      await loadBatchData(result.load_batch_id);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Upload failed for an unknown reason.",
      );
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <>
      <section className="hero">
        <div className="hero-card">
          <div className="hero-kicker">Backend-connected POC</div>
          <h1>Benchmarking Ingestion Console</h1>
          <p>
            Upload benchmark workbooks, inspect batch processing results, review validation
            issues, and download a clean CSV of errors from the FastAPI backend.
          </p>
          <div className="hero-metrics">
            <div className="metric-card">
              <span className="metric-label">Current batch</span>
              <span className="metric-value mono">
                {activeBatchId ? activeBatchId.slice(0, 8) : "--"}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Error groups</span>
              <span className="metric-value">{errorCounts.length}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Error rows</span>
              <span className="metric-value">{errorDetails.length}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section-grid">
        <section className="section-card span-5">
          <div className="section-header">
            <div>
              <h2 className="section-title">Upload workbook</h2>
              <p className="section-subtitle">
                Submit a `.xlsx` file and monitor the upload and ingestion result in one place.
              </p>
            </div>
          </div>

          <div className="field-stack">
            <label className="field-label" htmlFor="workbook-file">
              Excel workbook
            </label>
            <input
              id="workbook-file"
              className="file-picker"
              type="file"
              accept=".xlsx"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </div>

          <div className="action-row">
            <button
              className="button"
              onClick={() => void handleUpload()}
              disabled={busyAction === "upload"}
            >
              {busyAction === "upload" ? "Uploading..." : "Upload and run"}
            </button>
            {activeBatchId ? (
              <a className="button-link" href={getErrorDownloadUrl(activeBatchId)}>
                Download errors CSV
              </a>
            ) : null}
          </div>

          <div className="progress-block">
            <div className="progress-meta">
              <span className="progress-label">Upload progress</span>
              <span className="progress-value">{uploadProgress}%</span>
            </div>
            <div className="progress-track" aria-hidden="true">
              <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
          </div>

          {!uploadResult ? (
            <p className="message-muted" style={{ marginTop: "18px" }}>
              No upload has been run in this session yet.
            </p>
          ) : null}

          {uploadResult?.exception ? (
            <div className="message-error">{uploadResult.exception}</div>
          ) : null}
          {errorMessage ? <div className="message-error">{errorMessage}</div> : null}
          {!errorMessage && uploadResult?.duplicate ? (
            <div className="message-success">
              This workbook was already ingested. Linked to existing batch{" "}
              <span className="mono">{uploadResult.load_batch_id.slice(0, 8)}</span>.
            </div>
          ) : null}
          {!errorMessage && !uploadResult?.duplicate && uploadResult?.status === "COMMITTED" ? (
            <div className="message-success">Upload completed successfully.</div>
          ) : null}
          {!errorMessage && !uploadResult?.duplicate && uploadResult?.status === "FAILED" ? (
            <div className="message-error">
              Upload completed but the batch failed validation. Review the errors below for the
              reason.
            </div>
          ) : null}
        </section>

        <section className="section-card span-7">
          <div className="section-header">
            <div>
              <h2 className="section-title">Run overview</h2>
              <p className="section-subtitle">
                Summary of the latest upload attempt and the backend response.
              </p>
            </div>
            <StatusBadge status={currentStatus} />
          </div>

          <div className="summary-grid">
            <div className="summary-item">
              <span className="summary-item-label">Selected file</span>
              <span className="summary-item-value">{selectedFile?.name ?? "-"}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item-label">Upload progress</span>
              <span className="summary-item-value">{uploadProgress}%</span>
            </div>
            <div className="summary-item">
              <span className="summary-item-label">Current batch</span>
              <span className="summary-item-value mono">{activeBatchId || "-"}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item-label">Status</span>
              <span className="summary-item-value">{currentStatus}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item-label">Error groups</span>
              <span className="summary-item-value">{errorCounts.length}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item-label">Detailed rows</span>
              <span className="summary-item-value">{errorDetails.length}</span>
            </div>
          </div>
        </section>

        <section className="section-card span-12">
          <div className="section-header">
            <div>
              <h2 className="section-title">Error insights</h2>
              <p className="section-subtitle">
                Review aggregated error counts and detailed row-level validation output.
              </p>
            </div>
            {activeBatchId ? (
              <a className="button-link" href={getErrorDownloadUrl(activeBatchId)}>
                Download errors CSV
              </a>
            ) : null}
          </div>

          {errorCounts.length > 0 ? (
            <div className="table-wrap" style={{ marginBottom: "14px" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Error type</th>
                    <th>Sheet</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {errorCounts.map((row, index) => (
                    <tr key={`${row.ErrorType}-${row.SheetName}-${index}`}>
                      <td>{row.Severity ?? "-"}</td>
                      <td>{row.ErrorType ?? "-"}</td>
                      <td>{row.SheetName ?? "-"}</td>
                      <td>{row.Cnt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="message-muted" style={{ marginBottom: "12px" }}>
              No error counts loaded yet.
            </p>
          )}

          {errorDetails.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Sheet</th>
                    <th>Row</th>
                    <th>Column</th>
                    <th>Type</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {errorDetails.map((row, index) => (
                    <tr key={`${row.ErrorType}-${row.RowNum}-${index}`}>
                      <td>{severityLabel(row.Severity)}</td>
                      <td>{row.SheetName ?? "-"}</td>
                      <td>{row.RowNum ?? "-"}</td>
                      <td>{row.ColumnName ?? "-"}</td>
                      <td>{row.ErrorType ?? "-"}</td>
                      <td>
                        <div>{toFriendlyErrorMessage(row)}</div>
                        {row.RowData ? (
                          <details className="row-data-details">
                            <summary>View row values</summary>
                            <pre className="row-data-pre">
                              {JSON.stringify(row.RowData, null, 2)}
                            </pre>
                          </details>
                        ) : (
                          <div className="row-data-unavailable">
                            Row values are not available for this error. This usually means the
                            row was skipped before staging (for example, missing required
                            TotalCost), so no staged snapshot exists.
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="message-muted">No error details loaded yet.</p>
          )}
        </section>
      </section>
    </>
  );
}
