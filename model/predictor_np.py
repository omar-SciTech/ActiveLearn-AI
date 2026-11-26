"""The same predictions as predictor.py, but with numpy only (no PyTorch).

Why: free web hosting (PythonAnywhere: 512 MB disk) has no room for PyTorch (~700 MB installed).
The trained weights are copied once into saved/<model>_<dataset>.npz by export_numpy.py (that step needs
PyTorch); this file then runs the same forward pass with numpy. Supports DKT and DKT-Q with a GRU or LSTM.

  p = NumpyPredictor()            # model named in saved/active_is201.json
  p.topic_mastery(history)        # same output as Predictor.topic_mastery
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = os.path.join(HERE, "saved")


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class NumpyPredictor:
    def __init__(self, name=None, dataset="is201"):
        if name is None:
            name = json.load(open(os.path.join(SAVED, f"active_{dataset}.json")))["model"]
        stem = f"{name}_{dataset}"
        self.meta = json.load(open(os.path.join(SAVED, f"{stem}_meta.json"), encoding="utf-8"))
        if self.meta["model"] not in ("dkt", "dktq"):
            raise ValueError(f"numpy inference supports DKT and DKT-Q, not {self.meta['model']}")
        self.w = dict(np.load(os.path.join(SAVED, f"{stem}.npz")))
        self.name, self.kind, self.cell = name, self.meta["model"], self.meta["config"]["cell"]
        self.hidden = self.w["rnn.weight_hh_l0"].shape[1]
        smap, qmap = self.meta["skill_map"], self.meta["question_map"]
        self.qids = list(self.meta["question_topic"])
        self.cand_sk = np.array([smap[str(self.meta["question_topic"][q])] + 1 for q in self.qids])
        self.cand_q = np.array([qmap.get(q, 1) for q in self.qids])

    def _last_state(self, x_seq):
        """Run the recurrent layer over the inputs (T, emb) and return the last hidden state."""
        w = self.w
        Wi, Wh = w["rnn.weight_ih_l0"], w["rnn.weight_hh_l0"]
        bi, bh = w["rnn.bias_ih_l0"], w["rnn.bias_hh_l0"]
        H = self.hidden
        h, c = np.zeros(H), np.zeros(H)
        for x in x_seq:
            gi, gh = Wi @ x + bi, Wh @ h + bh
            if self.cell == "gru":                        # PyTorch gate order: reset, update, new
                r = sigmoid(gi[:H] + gh[:H])
                z = sigmoid(gi[H:2 * H] + gh[H:2 * H])
                n = np.tanh(gi[2 * H:] + r * gh[2 * H:])
                h = (1 - z) * n + z * h
            else:                                         # LSTM gate order: input, forget, cell, output
                g = gi + gh
                i, f = sigmoid(g[:H]), sigmoid(g[H:2 * H])
                cc, o = np.tanh(g[2 * H:3 * H]), sigmoid(g[3 * H:])
                c = f * c + i * cc
                h = o * np.tanh(c)
        return h

    def question_probs(self, history):
        smap, qmap, w = self.meta["skill_map"], self.meta["question_map"], self.w
        h = [(smap[str(t)], int(ok), qmap.get(str(q), 1)) for t, ok, q in history if str(t) in smap]
        if self.kind == "dkt":
            if not h:
                p = np.array([self.meta["prior"][s - 1] for s in self.cand_sk])
            else:
                x = w["emb.weight"][[s * 2 + c + 1 for s, c, _ in h]]
                state = self._last_state(x)
                p = sigmoid(w["out.weight"] @ state + w["out.bias"])[self.cand_sk - 1]
        else:
            if not h:
                state = np.zeros(self.hidden)
            else:
                x = w["emb_i.weight"][[s * 2 + c + 1 for s, c, _ in h]] + w["emb_q.weight"][[q for *_, q in h]]
                state = self._last_state(x)
            n = len(self.cand_q)
            feats = np.concatenate([np.tile(state, (n, 1)), w["next_q.weight"][self.cand_q],
                                    w["next_s.weight"][self.cand_sk]], axis=1)
            hid = np.maximum(feats @ w["head.0.weight"].T + w["head.0.bias"], 0)
            p = sigmoid(hid @ w["head.3.weight"].T + w["head.3.bias"])[:, 0]
        return dict(zip(self.qids, p.tolist()))

    def topic_mastery(self, history):
        probs = self.question_probs(history)
        by_topic = {}
        for q, p in probs.items():
            by_topic.setdefault(int(self.meta["question_topic"][q]), []).append(p)
        return {t: round(sum(v) / len(v), 4) for t, v in by_topic.items()}
