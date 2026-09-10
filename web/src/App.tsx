import { Route, Routes } from "react-router-dom";

import { AuditTrailPage } from "@/features/audit/AuditTrailPage";
import { QualityMetricsPage } from "@/features/metrics/QualityMetricsPage";
import { CaseQueuePage } from "@/features/queue/CaseQueuePage";
import { VerificationDetailPage } from "@/features/verification/VerificationDetailPage";
import { CaseWorkspacePage } from "@/features/workspace/CaseWorkspacePage";
import { VersionDiffPage } from "@/features/workspace/VersionDiffPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CaseQueuePage />} />
      <Route path="/metrics" element={<QualityMetricsPage />} />
      <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
      <Route path="/cases/:caseId/audit" element={<AuditTrailPage />} />
      <Route path="/cases/:caseId/narratives/:narrativeId/verification" element={<VerificationDetailPage />} />
      <Route path="/cases/:caseId/narratives/:narrativeId/diff/:otherVersion" element={<VersionDiffPage />} />
    </Routes>
  );
}
