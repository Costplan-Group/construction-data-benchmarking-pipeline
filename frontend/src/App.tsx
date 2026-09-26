import { useState } from "react";

import { AppNav, type PageId } from "./components/AppNav";
import { AiQsPage } from "./pages/AiQsPage";
import { AiReportPage } from "./pages/AiReportPage";
import { IngestionPage } from "./pages/IngestionPage";

function App() {
  const [activePage, setActivePage] = useState<PageId>("ingestion");

  return (
    <main className="app-shell">
      <AppNav activePage={activePage} onChange={setActivePage} />
      {activePage === "ingestion" ? (
        <IngestionPage />
      ) : activePage === "ai-report" ? (
        <AiReportPage />
      ) : (
        <AiQsPage />
      )}
    </main>
  );
}

export default App;
