"""Knowledge-tracing hook used by the backend.

predict_mastery(history, topic_ids) -> {topic_id: P(correct)}
    history  : list of (topic_id, is_correct, question_id) from oldest to newest
    topic_ids: the chapters of the course

It uses the IS201 model chosen in model/saved/active_is201.json (the one with the best validation
AUC: DKT, DKT-Q or SAKT). Without PyTorch it runs the numpy copy of the model (model/predictor_np.py);
if the model files are missing it falls back to a simple recency-weighted accuracy, so the app always works.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(os.path.dirname(HERE), "model")

DECAY = 0.85          # fallback: newer attempts count more
PRIOR = 0.5           # fallback: assumed p(correct) with no history

_predictor = None
MODEL_ACTIVE = False
MODEL_NAME = "fallback formula"
try:                                            # load the model once, when the server starts
    if os.path.exists(os.path.join(MODEL_DIR, "saved", "active_is201.json")):
        sys.path.insert(0, MODEL_DIR)
        try:
            from predictor import Predictor          # PyTorch version
            _predictor = Predictor()
        except ImportError:                          # no PyTorch (e.g. free hosting) -> same model in numpy
            from predictor_np import NumpyPredictor
            _predictor = NumpyPredictor()
            print("[mastery] PyTorch not installed, using the numpy copy of the model")
        MODEL_ACTIVE, MODEL_NAME = True, _predictor.name
except Exception as e:                          # e.g. no model files
    print("[mastery] model not loaded, using fallback formula:", e)


def _fallback(history, topic_ids):
    num = {t: 0.0 for t in topic_ids}
    den = {t: 0.0 for t in topic_ids}
    n = len(history)
    for i, (t, ok, *_) in enumerate(history):
        if t not in num:
            continue
        w = DECAY ** (n - 1 - i)
        num[t] += w * ok
        den[t] += w
    return {t: round((num[t] + PRIOR) / (den[t] + 1.0), 4) for t in topic_ids}


def predict_mastery(history, topic_ids):
    if not MODEL_ACTIVE:
        return _fallback(history, topic_ids)
    m = _predictor.topic_mastery(history)
    fb = None
    out = {}
    for t in topic_ids:
        if t in m:
            out[t] = m[t]
        else:                                   # a chapter the model was not trained on
            fb = fb or _fallback(history, topic_ids)
            out[t] = fb[t]
    return out
