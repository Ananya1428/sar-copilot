import numpy as np

from app.domain.detection.ml import AnomalyEnsemble


def test_ensemble_fits_and_scores_without_crashing():
    rng = np.random.RandomState(0)
    normal = rng.normal(loc=0, scale=1, size=(28, 5))
    outliers = np.array([[50, 50, 50, 50, 50], [-50, -50, -50, -50, -50]])
    X = np.vstack([normal, outliers])
    names = [f"f{i}" for i in range(5)]

    ensemble = AnomalyEnsemble(seed=1)
    ensemble.fit(X, names)
    scores = ensemble.score()

    assert scores.shape == (30,)
    assert np.all(scores >= 0.0) and np.all(scores <= 1.0 + 1e-9)

    # The two deliberate outliers should score among the highest.
    top2 = set(np.argsort(scores)[-2:])
    assert top2 == {28, 29}


def test_ensemble_explain_returns_top_k_features():
    rng = np.random.RandomState(0)
    X = rng.normal(size=(15, 4))
    names = ["a", "b", "c", "d"]

    ensemble = AnomalyEnsemble(seed=1)
    ensemble.fit(X, names)
    explanation = ensemble.explain(X[0], top_k=2)

    assert len(explanation) == 2
    assert all({"feature", "z_score", "raw_value"} <= e.keys() for e in explanation)


def test_ensemble_degrades_gracefully_with_few_samples():
    # n_samples <= n_features + 1 can't support MinCovDet's covariance
    # estimate — fit/score must still complete, just without that term.
    X = np.random.RandomState(2).normal(size=(4, 6))
    names = [f"f{i}" for i in range(6)]

    ensemble = AnomalyEnsemble(seed=1)
    ensemble.fit(X, names)

    assert ensemble._mcd_available is False
    scores = ensemble.score()
    assert scores.shape == (4,)
    assert np.all(np.isfinite(scores))


def test_score_before_fit_raises():
    ensemble = AnomalyEnsemble()
    try:
        ensemble.score()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
