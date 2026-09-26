import type { AIReportDraftResponse } from "../types/ingestion";

export type EditableDraftSections = {
  executiveSummaryBody: string;
  executiveSummaryRecommendation: string;
  commercialAnalysisBody: string;
};

export type SectionEditState = {
  executiveSummary: boolean;
  commercialAnalysis: boolean;
};

export function toEditorHtml(value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) {
    return "<p></p>";
  }
  // If backend text is plain text/newline based, convert to simple paragraphs.
  if (!/[<>]/.test(text)) {
    return text
      .split(/\n{2,}/)
      .map((part) => `<p>${part.replace(/\n/g, "<br />")}</p>`)
      .join("");
  }
  return text;
}

export function buildCurrentDraftSections(
  draft: AIReportDraftResponse,
  editable: EditableDraftSections,
): Record<string, unknown> {
  return {
    ...draft.draft_sections,
    executive_summary: {
      ...((draft.draft_sections as Record<string, unknown>).executive_summary as Record<
        string,
        unknown
      >),
      body: editable.executiveSummaryBody,
      recommendation: editable.executiveSummaryRecommendation,
    },
    commercial_analysis: {
      ...((draft.draft_sections as Record<string, unknown>).commercial_analysis as Record<
        string,
        unknown
      >),
      body: editable.commercialAnalysisBody,
    },
  };
}

export function editableSectionsFromDraft(
  draft: AIReportDraftResponse,
): EditableDraftSections {
  const sections = draft.draft_sections as Record<string, unknown>;
  const executive = (sections.executive_summary ?? {}) as Record<string, unknown>;
  const commercial = (sections.commercial_analysis ?? {}) as Record<string, unknown>;
  return {
    executiveSummaryBody: toEditorHtml(executive.body),
    executiveSummaryRecommendation: toEditorHtml(executive.recommendation),
    commercialAnalysisBody: toEditorHtml(commercial.body),
  };
}
