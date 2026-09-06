"""Unsupervised ML anomaly ensemble (blueprint §12.3).

Three complementary, interpretable detectors averaged into one score —
chosen deliberately over a deep model (e.g. an autoencoder) because every
component here can be explained to a model validator without hand-waving,
which blueprint §12.3 calls out as a real SR 11-7 deployment concern, not
just a style preference.

Two deliberate deviations from the blueprint's illustrative snippet, both
needed to make it actually correct for how this build uses it (fit and
score the SAME batch every detection run — no persistence across runs,
per the Part 2 brief):

1. `LocalOutlierFactor(novelty=False)`, not `novelty=True`. scikit-learn's
   own docs are explicit that with `novelty=True`, `score_samples` must be
   called on data DISJOINT from the fit set — calling it on the fit set
   itself (exactly what the blueprint's `score()` does) is documented to
   give wrong results. `novelty=False` is scikit-learn's actual "outlier
   detection on a fixed dataset" mode, and exposes the fitted scores via
   `negative_outlier_factor_` instead of a separate `score_samples` call.
2. `score()` therefore takes no argument and always scores the data passed
   to `fit()` — there is no supported way for this ensemble to score new,
   held-out data, so a `score(X)` signature implying otherwise would be
   misleading API surface.

`explain()` is unchanged from the blueprint: per-account, which features
deviate most from the batch, in units of the RobustScaler's scale — this
feeds `ml_findings` in a later part's EvidencePack so a narrative can state
something like "transaction velocity was 4.2 standard deviations above
baseline" as a verifiable claim.
"""

import numpy as np
from sklearn.covariance import MinCovDet
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

from app.domain.detection.thresholds import ML_CONTAMINATION, ML_LOF_N_NEIGHBORS, ML_SEED


class AnomalyEnsemble:
    def __init__(self, contamination: float = ML_CONTAMINATION, seed: int = ML_SEED):
        self.scaler = RobustScaler()
        self.iforest = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed, n_jobs=-1)
        self.lof = LocalOutlierFactor(n_neighbors=ML_LOF_N_NEIGHBORS, contamination=contamination, novelty=False)
        self.mcd = MinCovDet(random_state=seed)
        self.feature_names_: list[str] = []
        self._fit_X: np.ndarray | None = None
        self._mcd_available = False

    def fit(self, X: np.ndarray, feature_names: list[str]) -> "AnomalyEnsemble":
        X = np.asarray(X, dtype=float)
        n_samples, n_features = X.shape
        self.feature_names_ = feature_names

        Xs = self.scaler.fit_transform(X)
        self.iforest.fit(Xs)

        # LOF needs n_neighbors < n_samples; clamp for small batches
        # (unit tests, or a detection run over very few accounts).
        self.lof.n_neighbors = max(1, min(ML_LOF_N_NEIGHBORS, n_samples - 1))
        self.lof.fit(Xs)

        # MinCovDet needs materially more samples than features to produce
        # a full-rank covariance estimate. Below that, skip it rather than
        # let a small batch crash the whole detection run — score() then
        # averages just the other two detectors.
        self._mcd_available = n_samples > n_features + 1
        if self._mcd_available:
            try:
                self.mcd.fit(Xs)
            except (ValueError, np.linalg.LinAlgError):
                self._mcd_available = False

        self._fit_X = Xs
        return self

    def score(self) -> np.ndarray:
        """Returns anomaly score in [0,1] for the data passed to `fit`;
        higher = more anomalous."""
        if self._fit_X is None:
            raise RuntimeError("AnomalyEnsemble.score() called before fit()")

        Xs = self._fit_X
        s_if = -self.iforest.score_samples(Xs)
        s_lof = -self.lof.negative_outlier_factor_

        def norm(v: np.ndarray) -> np.ndarray:
            spread = v.max() - v.min()
            return (v - v.min()) / spread if spread > 1e-9 else np.zeros_like(v)

        if self._mcd_available:
            s_mah = self.mcd.mahalanobis(Xs)
            return (norm(s_if) + norm(s_lof) + norm(s_mah)) / 3.0
        return (norm(s_if) + norm(s_lof)) / 2.0

    def explain(self, x: np.ndarray, top_k: int = 5) -> list[dict]:
        """Per-account explanation: which features deviate most, in scaled
        (RobustScaler) units."""
        xs = self.scaler.transform(x.reshape(1, -1))[0]
        deviations = np.abs(xs)
        idx = np.argsort(deviations)[::-1][:top_k]
        return [
            {
                "feature": self.feature_names_[i],
                "z_score": round(float(xs[i]), 2),
                "raw_value": float(x[i]),
            }
            for i in idx
        ]
