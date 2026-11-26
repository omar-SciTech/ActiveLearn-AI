"""Knowledge-tracing models (PyTorch). Three models, one interface:

  dkt   DKT (Piech et al., 2015): RNN over (skill, correct?) -> P(correct) for every skill.
        Sees only the SKILL of each question.
  dktq  DKT-Q: same RNN, but it also sees WHICH QUESTION was answered and predicts the next
        question directly: [RNN state ; embedding(next question) ; embedding(next skill)] -> MLP -> P.
        So it can learn that two questions of the same skill have different difficulty.
  sakt  SAKT (Pandey & Karypis, 2019): self-attention (Transformer) instead of an RNN. The next
        question is the query, the student's past answers are the keys/values, so the model decides
        which past answers matter for this question.

RNN cell for dkt / dktq: --cell lstm or --cell gru.

Batch tensors (built by collate):
  inter : interaction id = skill*2 + correct + 1   (0 = padding)
  sk    : skill index + 1                          (0 = padding)
  qq    : question index (0 = padding, 1 = rare/unknown question, 2.. = known questions)
  y     : correct (0/1),  valid : True where there is a real answer
Every model's forward() returns one logit per step t = 1..T-1: P(answer t is correct | answers 0..t-1).
"""
import torch
import torch.nn as nn


def rnn_cell(cell):
    return {"lstm": nn.LSTM, "gru": nn.GRU}[cell]


class DKT(nn.Module):
    def __init__(self, n_skills, n_questions, emb=64, hidden=128, dropout=0.3, cell="lstm", **_):
        super().__init__()
        self.emb = nn.Embedding(2 * n_skills + 1, emb, padding_idx=0)
        self.rnn = rnn_cell(cell)(emb, hidden, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.out = nn.Linear(hidden, n_skills)
        nn.init.xavier_uniform_(self.out.weight)

    def forward(self, inter, sk, qq):
        h, _ = self.rnn(self.emb(inter[:, :-1]))
        logits = self.out(self.drop(h))                          # (B, T-1, n_skills)
        target = (sk[:, 1:] - 1).clamp(min=0)
        return logits.gather(2, target.unsqueeze(-1)).squeeze(-1)

    @torch.no_grad()
    def predict_candidates(self, inter, sk, qq, cand_sk, cand_q):
        if inter.shape[1] == 0:
            return None
        h, _ = self.rnn(self.emb(inter))
        return torch.sigmoid(self.out(h[:, -1]))[0, cand_sk - 1]


class DKTQ(nn.Module):
    def __init__(self, n_skills, n_questions, emb=64, hidden=128, dropout=0.3, cell="gru", **_):
        super().__init__()
        self.emb_i = nn.Embedding(2 * n_skills + 1, emb, padding_idx=0)   # what happened (skill, correct)
        self.emb_q = nn.Embedding(n_questions, emb, padding_idx=0)        # which question it was
        self.rnn = rnn_cell(cell)(emb, hidden, batch_first=True)
        self.next_q = nn.Embedding(n_questions, emb, padding_idx=0)       # the question to predict
        self.next_s = nn.Embedding(n_skills + 1, emb, padding_idx=0)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Sequential(nn.Linear(hidden + 2 * emb, hidden), nn.ReLU(),
                                  nn.Dropout(dropout), nn.Linear(hidden, 1))
        self.hidden = hidden

    def _states(self, inter, qq):
        h, _ = self.rnn(self.emb_i(inter) + self.emb_q(qq))
        return h

    def _score(self, h, sk_next, q_next):
        x = torch.cat([self.drop(h), self.next_q(q_next), self.next_s(sk_next)], dim=-1)
        return self.head(x).squeeze(-1)

    def forward(self, inter, sk, qq):
        return self._score(self._states(inter[:, :-1], qq[:, :-1]), sk[:, 1:], qq[:, 1:])

    @torch.no_grad()
    def predict_candidates(self, inter, sk, qq, cand_sk, cand_q):
        if inter.shape[1] == 0:
            h = torch.zeros(1, self.hidden, device=cand_q.device)            # no history yet
        else:
            h = self._states(inter, qq)[:, -1]
        return torch.sigmoid(self._score(h.expand(len(cand_q), -1), cand_sk, cand_q))


class SAKT(nn.Module):
    def __init__(self, n_skills, n_questions, emb=64, dropout=0.2, heads=4, max_len=100, **_):
        super().__init__()
        d = emb
        self.emb_i = nn.Embedding(2 * n_skills + 1, d, padding_idx=0)
        self.emb_q = nn.Embedding(n_questions, d, padding_idx=0)
        self.qry_q = nn.Embedding(n_questions, d, padding_idx=0)
        self.qry_s = nn.Embedding(n_skills + 1, d, padding_idx=0)
        self.pos = nn.Embedding(max_len, d)                                 # position in the sequence
        self.attn = nn.MultiheadAttention(d, heads, dropout=dropout, batch_first=True)
        self.ln1, self.ln2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.ffn = nn.Sequential(nn.Linear(d, 2 * d), nn.ReLU(), nn.Dropout(dropout), nn.Linear(2 * d, d))
        self.drop = nn.Dropout(dropout)
        self.out = nn.Linear(d, 1)
        self.max_len = max_len

    def _block(self, queries, keys, attn_mask=None, key_pad=None):
        a, _ = self.attn(queries, keys, keys, attn_mask=attn_mask, key_padding_mask=key_pad)
        x = self.ln1(queries + self.drop(a))
        x = self.ln2(x + self.drop(self.ffn(x)))
        return self.out(x).squeeze(-1)

    def forward(self, inter, sk, qq):
        L = inter.shape[1] - 1
        pos = self.pos(torch.arange(L, device=inter.device))
        keys = self.emb_i(inter[:, :-1]) + self.emb_q(qq[:, :-1]) + pos
        queries = self.qry_q(qq[:, 1:]) + self.qry_s(sk[:, 1:]) + pos
        causal = torch.triu(torch.ones(L, L, dtype=torch.bool, device=inter.device), diagonal=1)
        return self._block(queries, keys, causal, inter[:, :-1] == 0)       # can only look at the past

    @torch.no_grad()
    def predict_candidates(self, inter, sk, qq, cand_sk, cand_q):
        if inter.shape[1] == 0:
            return None
        inter, qq = inter[:, -(self.max_len - 1):], qq[:, -(self.max_len - 1):]
        L = inter.shape[1]
        keys = self.emb_i(inter) + self.emb_q(qq) + self.pos(torch.arange(L, device=inter.device))
        keys = keys.expand(len(cand_q), -1, -1)
        last = self.pos(torch.tensor([L - 1], device=inter.device))
        queries = (self.qry_q(cand_q) + self.qry_s(cand_sk) + last).unsqueeze(1)
        return torch.sigmoid(self._block(queries, keys)).view(-1)


MODELS = {"dkt": DKT, "dktq": DKTQ, "sakt": SAKT}


def build_model(name, n_skills, n_questions, cfg):
    return MODELS[name](n_skills, n_questions, **cfg)


def make_windows(user, s, c, q, max_len):
    """Cuts one student's sequence into pieces of at most max_len answers (truncated BPTT)."""
    out = []
    for i in range(0, len(s), max_len):
        if len(s[i:i + max_len]) >= 2:
            out.append((user, i, s[i:i + max_len], c[i:i + max_len], q[i:i + max_len]))
    return out


def collate(windows):
    T = max(len(w[2]) for w in windows)
    B = len(windows)
    inter = torch.zeros(B, T, dtype=torch.long)
    sk = torch.zeros(B, T, dtype=torch.long)
    qq = torch.zeros(B, T, dtype=torch.long)
    y = torch.zeros(B, T)
    valid = torch.zeros(B, T, dtype=torch.bool)
    for i, (_, _, s, c, q) in enumerate(windows):
        L = len(s)
        inter[i, :L] = torch.tensor([a * 2 + b + 1 for a, b in zip(s, c)])
        sk[i, :L] = torch.tensor(s) + 1
        qq[i, :L] = torch.tensor(q)
        y[i, :L] = torch.tensor(c, dtype=torch.float)
        valid[i, :L] = True
    return inter, sk, qq, y, valid


def history_tensors(skills, corrects, questions, device="cpu"):
    """One student's history as (1, L) tensors for predict_candidates."""
    inter = torch.tensor([[a * 2 + b + 1 for a, b in zip(skills, corrects)]], dtype=torch.long, device=device)
    sk = torch.tensor([[a + 1 for a in skills]], dtype=torch.long, device=device)
    qq = torch.tensor([questions], dtype=torch.long, device=device)
    return inter.view(1, -1), sk.view(1, -1), qq.view(1, -1)
