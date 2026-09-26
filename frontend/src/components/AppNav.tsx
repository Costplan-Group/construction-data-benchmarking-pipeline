export type PageId = "ingestion" | "ai-report" | "ai-qs";

type AppNavProps = {
  activePage: PageId;
  onChange: (page: PageId) => void;
};

export function AppNav({ activePage, onChange }: AppNavProps) {
  return (
    <div className="top-nav">
      <button
        type="button"
        className={`tab-button ${activePage === "ingestion" ? "tab-button-active" : ""}`}
        onClick={() => onChange("ingestion")}
      >
        Ingestion Console
      </button>
      <button
        type="button"
        className={`tab-button ${activePage === "ai-qs" ? "tab-button-active" : ""}`}
        onClick={() => onChange("ai-qs")}
      >
        AI QS Assistant
      </button>
      <button
        type="button"
        className={`tab-button ${activePage === "ai-report" ? "tab-button-active" : ""}`}
        onClick={() => onChange("ai-report")}
      >
        AI Report Generation
      </button>
    </div>
  );
}
