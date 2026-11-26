"""Loads the IS201 model chosen for the app and turns a student's history into predictions.

Used by backend/mastery.py (live, after every answer) and model/predict_all.py (all students at once).

  p = Predictor()                                    # loads the model named in saved/active_is201.json
  p.topic_mastery([(topic_id, is_correct, question_id), ...])
     -> {topic_id: predicted P(correct)}  = average prediction over that chapter's questions
  p.question_probs(history) -> {question_id: predicted P(correct)}
"""
import json, os
import torch
from dkt import build_model, history_tensors

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = os.path.join(HERE, "saved")


class Predictor:
    def __init__(self, name=None, dataset="is201"):
        if name is None:
            name = json.load(open(os.path.join(SAVED, f"active_{dataset}.json")))["model"]
        stem = f"{name}_{dataset}"
        self.meta = json.load(open(os.path.join(SAVED, f"{stem}_meta.json"), encoding="utf-8"))
        self.name = name
        self.model = build_model(self.meta["model"], self.meta["n_skills"], self.meta["n_questions"], self.meta["config"])
        self.model.load_state_dict(torch.load(os.path.join(SAVED, f"{stem}.pt"), map_location="cpu"))
        self.model.eval()
        smap, qmap = self.meta["skill_map"], self.meta["question_map"]
        self.qids = list(self.meta["question_topic"])                    # every question of the course
        self.cand_sk = torch.tensor([smap[str(self.meta["question_topic"][q])] + 1 for q in self.qids])
        self.cand_q = torch.tensor([qmap.get(q, 1) for q in self.qids])

    def question_probs(self, history):
        smap, qmap = self.meta["skill_map"], self.meta["question_map"]
        h = [(smap[str(t)], int(ok), qmap.get(str(q), 1)) for t, ok, q in history if str(t) in smap]
        inter, sk, qq = history_tensors([x[0] for x in h], [x[1] for x in h], [x[2] for x in h])
        p = self.model.predict_candidates(inter, sk, qq, self.cand_sk, self.cand_q)
        if p is None:                                                   # no history -> training average
            p = torch.tensor([self.meta["prior"][int(s) - 1] for s in self.cand_sk])
        return dict(zip(self.qids, p.tolist()))

    def topic_mastery(self, history):
        probs = self.question_probs(history)
        by_topic = {}
        for q, p in probs.items():
            by_topic.setdefault(int(self.meta["question_topic"][q]), []).append(p)
        return {t: round(sum(v) / len(v), 4) for t, v in by_topic.items()}
