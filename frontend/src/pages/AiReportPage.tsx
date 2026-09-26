import { useState } from "react";

import {
  createAIReportDraft,
  exportAIReportDocx,
  exportAIReportPdf,
  saveAIReportDraft,
} from "../api/ingestion";
import { RichTextEditor } from "../components/RichTextEditor";
import type { AIReportDraftResponse } from "../types/ingestion";
import {
  buildCurrentDraftSections,
  editableSectionsFromDraft,
  type EditableDraftSections,
  type SectionEditState,
} from "../utils/reportDraft";

export function AiReportPage() {
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [reportProjectNumber, setReportProjectNumber] = useState("");
  const [reportDraft, setReportDraft] = useState<AIReportDraftResponse | null>(null);
  const [reportDraftError, setReportDraftError] = useState<string | null>(null);
  const [editableDraftSections, setEditableDraftSections] = useState<EditableDraftSections | null>(
    null,
  );
  const [reportDraftSavedAt, setReportDraftSavedAt] = useState<string | null>(null);
  const [sectionEditState, setSectionEditState] = useState<SectionEditState>({
    executiveSummary: false,
    commercialAnalysis: false,
  });

  async function handleGenerateReportDraft(regenerateFresh = false) {
    if (!reportProjectNumber.trim()) {
      setReportDraftError("Enter a Project ID to generate a report draft.");
      return;
    }

    setBusyAction("ai-report-draft");
    setReportDraftError(null);
    setReportDraft(null);
    setEditableDraftSections(null);
    setReportDraftSavedAt(null);
    setSectionEditState({
      executiveSummary: false,
      commercialAnalysis: false,
    });
    try {
      const result = await createAIReportDraft(reportProjectNumber.trim(), { regenerateFresh });
      setReportDraft(result);
      setEditableDraftSections(editableSectionsFromDraft(result));
    } catch (error) {
      setReportDraftError(
        error instanceof Error ? error.message : "Failed to generate AI report draft.",
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSaveReportDraft() {
    if (!reportDraft || !editableDraftSections) {
      setReportDraftError("Generate a draft before saving.");
      return;
    }
    setBusyAction("ai-report-save");
    setReportDraftError(null);
    try {
      const nextDraftSections = buildCurrentDraftSections(reportDraft, editableDraftSections);
      const saved = await saveAIReportDraft({
        project_id: reportDraft.project_id ?? reportProjectNumber,
        load_batch_id: reportDraft.load_batch_id,
        source_file_name: reportDraft.source_file_name,
        draft_sections: nextDraftSections,
      });
      setReportDraft((prev) =>
        prev
          ? {
              ...prev,
              draft_sections: saved.draft_sections,
            }
          : prev,
      );
      setReportDraftSavedAt(saved.saved_at_utc);
      setSectionEditState({
        executiveSummary: false,
        commercialAnalysis: false,
      });
    } catch (error) {
      setReportDraftError(error instanceof Error ? error.message : "Failed to save report draft.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleExportDocx() {
    if (!reportDraft || !editableDraftSections) {
      setReportDraftError("Generate a draft before exporting.");
      return;
    }
    setBusyAction("ai-report-docx");
    setReportDraftError(null);
    try {
      await exportAIReportDocx({
        project_id: reportDraft.project_id ?? reportProjectNumber,
        load_batch_id: reportDraft.load_batch_id,
        source_file_name: reportDraft.source_file_name,
        draft_sections: buildCurrentDraftSections(reportDraft, editableDraftSections),
        report_context: reportDraft.report_context,
      });
    } catch (error) {
      setReportDraftError(error instanceof Error ? error.message : "DOCX export failed.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleExportPdf() {
    if (!reportDraft || !editableDraftSections) {
      setReportDraftError("Generate a draft before exporting.");
      return;
    }
    setBusyAction("ai-report-pdf");
    setReportDraftError(null);
    try {
      await exportAIReportPdf({
        project_id: reportDraft.project_id ?? reportProjectNumber,
        load_batch_id: reportDraft.load_batch_id,
        source_file_name: reportDraft.source_file_name,
        draft_sections: buildCurrentDraftSections(reportDraft, editableDraftSections),
        report_context: reportDraft.report_context,
      });
    } catch (error) {
      setReportDraftError(error instanceof Error ? error.message : "PDF export failed.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <>
      <section className="hero">
        <div className="hero-card">
          <div className="hero-kicker">AI-assisted report workflow</div>
          <h1>AI Report Generation</h1>
          <p>
            Generate a report draft context from a processed batch. This draft is the backend
            contract for the editable report page and final PDF/DOCX output flow.
          </p>
        </div>
      </section>

      <section className="section-grid">
        <section className="section-card span-12">
          <div className="section-header">
            <div>
              <h2 className="section-title">Create report draft</h2>
              <p className="section-subtitle">
                Enter a Project ID to fetch the latest matching report context.
              </p>
            </div>
          </div>

          <div className="field-stack">
            <label className="field-label" htmlFor="report-project-number">
              Project ID
            </label>
            <input
              id="report-project-number"
              className="text-input"
              placeholder="e.g. P2402"
              value={reportProjectNumber}
              onChange={(event) => setReportProjectNumber(event.target.value)}
            />
          </div>

          <div className="action-row">
            <button
              className="button"
              onClick={() => void handleGenerateReportDraft(false)}
              disabled={busyAction === "ai-report-draft"}
            >
              {busyAction === "ai-report-draft" ? "Generating..." : "Generate report draft"}
            </button>
            <button
              className="button-secondary"
              onClick={() => void handleGenerateReportDraft(true)}
              disabled={busyAction === "ai-report-draft"}
            >
              {busyAction === "ai-report-draft" ? "Regenerating..." : "Regenerate fresh"}
            </button>
            <button
              className="button-secondary"
              onClick={() => void handleSaveReportDraft()}
              disabled={
                busyAction === "ai-report-save" || !reportDraft || !editableDraftSections
              }
            >
              {busyAction === "ai-report-save" ? "Saving..." : "Save draft edits"}
            </button>
            <button
              className="button-secondary"
              onClick={() => void handleExportDocx()}
              disabled={busyAction === "ai-report-docx" || !reportDraft || !editableDraftSections}
            >
              {busyAction === "ai-report-docx" ? "Generating DOCX..." : "Generate .docx"}
            </button>
            <button
              className="button-secondary"
              onClick={() => void handleExportPdf()}
              disabled={busyAction === "ai-report-pdf" || !reportDraft || !editableDraftSections}
            >
              {busyAction === "ai-report-pdf" ? "Generating PDF..." : "Generate .pdf"}
            </button>
          </div>

          {reportDraftError ? <div className="message-error">{reportDraftError}</div> : null}
          {reportDraft?.saved_draft_loaded && reportDraft.saved_at_utc ? (
            <div className="message-success">
              Saved draft loaded from {new Date(reportDraft.saved_at_utc).toLocaleString()}.
            </div>
          ) : null}
          {reportDraftSavedAt ? (
            <div className="message-success">
              Draft saved successfully at {new Date(reportDraftSavedAt).toLocaleString()}.
            </div>
          ) : null}

          {reportDraft ? (
            <>
              <div className="summary-grid" style={{ marginTop: "18px" }}>
                <div className="summary-item">
                  <span className="summary-item-label">Source file</span>
                  <span className="summary-item-value">
                    {reportDraft.source_file_name ?? "-"}
                  </span>
                </div>
              </div>

              <details className="row-data-details" style={{ marginTop: "12px" }}>
                <summary>Draft sections JSON</summary>
                <pre className="row-data-pre">
                  {JSON.stringify(reportDraft.draft_sections, null, 2)}
                </pre>
              </details>
              {editableDraftSections ? (
                <div className="section-grid" style={{ marginTop: "12px" }}>
                  <section className="section-card span-12 report-section-editor">
                    <div className="section-header">
                      <div>
                        <h3 className="section-title">Executive Summary</h3>
                      </div>
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() =>
                          setSectionEditState((prev) => ({
                            ...prev,
                            executiveSummary: !prev.executiveSummary,
                          }))
                        }
                      >
                        {sectionEditState.executiveSummary ? "Cancel edit" : "Edit section"}
                      </button>
                    </div>
                    <div className="field-stack">
                      <label className="field-label" htmlFor="exec-body">
                        Summary body
                      </label>
                      {sectionEditState.executiveSummary ? (
                        <RichTextEditor
                          id="exec-body"
                          value={editableDraftSections.executiveSummaryBody}
                          height={220}
                          onChange={(value) =>
                            setEditableDraftSections((prev) =>
                              prev ? { ...prev, executiveSummaryBody: value } : prev,
                            )
                          }
                        />
                      ) : (
                        <div
                          className="report-preview-html"
                          dangerouslySetInnerHTML={{
                            __html: editableDraftSections.executiveSummaryBody,
                          }}
                        />
                      )}
                    </div>
                    <div className="field-stack" style={{ marginTop: "10px" }}>
                      <label className="field-label" htmlFor="exec-recommendation">
                        Recommendation
                      </label>
                      {sectionEditState.executiveSummary ? (
                        <RichTextEditor
                          id="exec-recommendation"
                          value={editableDraftSections.executiveSummaryRecommendation}
                          height={180}
                          compact
                          onChange={(value) =>
                            setEditableDraftSections((prev) =>
                              prev
                                ? { ...prev, executiveSummaryRecommendation: value }
                                : prev,
                            )
                          }
                        />
                      ) : (
                        <div
                          className="report-preview-html"
                          dangerouslySetInnerHTML={{
                            __html: editableDraftSections.executiveSummaryRecommendation,
                          }}
                        />
                      )}
                    </div>
                  </section>
                  <section className="section-card span-12 report-section-editor">
                    <div className="section-header">
                      <div>
                        <h3 className="section-title">Commercial Analysis</h3>
                      </div>
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() =>
                          setSectionEditState((prev) => ({
                            ...prev,
                            commercialAnalysis: !prev.commercialAnalysis,
                          }))
                        }
                      >
                        {sectionEditState.commercialAnalysis ? "Cancel edit" : "Edit section"}
                      </button>
                    </div>
                    <div className="field-stack">
                      <label className="field-label" htmlFor="commercial-body">
                        Analysis body
                      </label>
                      {sectionEditState.commercialAnalysis ? (
                        <RichTextEditor
                          id="commercial-body"
                          value={editableDraftSections.commercialAnalysisBody}
                          height={240}
                          onChange={(value) =>
                            setEditableDraftSections((prev) =>
                              prev ? { ...prev, commercialAnalysisBody: value } : prev,
                            )
                          }
                        />
                      ) : (
                        <div
                          className="report-preview-html"
                          dangerouslySetInnerHTML={{
                            __html: editableDraftSections.commercialAnalysisBody,
                          }}
                        />
                      )}
                    </div>
                  </section>
                </div>
              ) : null}
              <details className="row-data-details" style={{ marginTop: "12px" }}>
                <summary>Report context JSON</summary>
                <pre className="row-data-pre">
                  {JSON.stringify(reportDraft.report_context, null, 2)}
                </pre>
              </details>
            </>
          ) : (
            <p className="message-muted" style={{ marginTop: "14px" }}>
              No draft generated yet.
            </p>
          )}
        </section>
      </section>
    </>
  );
}
