from fastapi import APIRouter

from app.api.v1 import audit, auth, cases, detection, evidence, exports, metrics, narratives, onboarding

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(narratives.router, prefix="/narratives", tags=["narratives"])
api_router.include_router(evidence.router, prefix="/evidence", tags=["evidence"])
api_router.include_router(detection.router, prefix="/detection", tags=["detection"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(onboarding.customers_router, prefix="/customers", tags=["onboarding"])
api_router.include_router(onboarding.accounts_router, prefix="/accounts", tags=["onboarding"])
