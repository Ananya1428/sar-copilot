import { Route, Routes } from "react-router-dom";

import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { AuditTrailPage } from "@/features/audit/AuditTrailPage";
import { QualityMetricsPage } from "@/features/metrics/QualityMetricsPage";
import { DataEntryPage } from "@/features/onboarding/DataEntryPage";
import { CaseQueuePage } from "@/features/queue/CaseQueuePage";
import { VerificationDetailPage } from "@/features/verification/VerificationDetailPage";
import { CaseWorkspacePage } from "@/features/workspace/CaseWorkspacePage";
import { VersionDiffPage } from "@/features/workspace/VersionDiffPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/" element={<CaseQueuePage />} />
        <Route path="/data-entry" element={<DataEntryPage />} />
        <Route path="/metrics" element={<QualityMetricsPage />} />
        <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
        <Route path="/cases/:caseId/audit" element={<AuditTrailPage />} />
        <Route path="/cases/:caseId/narratives/:narrativeId/verification" element={<VerificationDetailPage />} />
        <Route path="/cases/:caseId/narratives/:narrativeId/diff/:otherVersion" element={<VersionDiffPage />} />
      </Route>
    </Routes>
  );
}
