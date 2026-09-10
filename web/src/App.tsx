import { Route, Routes } from "react-router-dom";

import { CaseQueuePage } from "@/features/queue/CaseQueuePage";
import { CaseWorkspacePage } from "@/features/workspace/CaseWorkspacePage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CaseQueuePage />} />
      <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
    </Routes>
  );
}
