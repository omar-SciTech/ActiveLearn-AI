"""Trains a knowledge-tracing model (PyTorch) and evaluates it on students it never saw.

  python train.py assist --model dktq --cell gru      # question-aware DKT with a GRU   (default)
  python train.py assist --model dkt  --cell lstm     # classic DKT
  python train.py assist --model sakt                 # self-attention (Transformer)
  python train.py is201  --model dktq                 # same models on the IS201 bank (used in the app)

Optimization / regularization (DLS courses 1, 2 and 5):
  Adam + L2 weight decay, shuffled mini-batches, dropout, gradient clipping, learning-rate decay
  (ReduceLROnPlateau), early stopping on the validation set (best weights kept), Xavier init,
  train / validation / test split by student.

Every run writes (name = model[-cell], e.g. dktq-gru):
  saved/<name>_<dataset>.pt + _meta.json         weights + settings + maps
  results/metrics_<name>_<dataset>.json          AUC / accuracy vs 3 baselines + training history
  results/training_curves_<name>_<dataset>.png
  results/test_predictions_<name>_<dataset>.csv  every test prediction next to the baselines
  results/comparison_<dataset>.csv               ONE ROW PER RUN -> compare all your experiments
For is201, the model with the best VALIDATION AUC becomes the one the app uses (saved/active_is201.json).
"""
import argparse, csv, json, os, pickle, random, time
from collections import defaultdict
from datetime import datetime
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score, accuracy_score
from dkt import build_model, make_windows, collate

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(HERE, *a)


def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s); torch.cuda.manual_seed_all(s)


def windows_of(part, max_len):
    return [w for u, s, c, q in part for w in make_windows(u, s, c, q, max_len)]


def batches(windows, bs, shuffle):
    idx = list(range(len(windows)))
    if shuffle:
        random.shuffle(idx)
    for i in range(0, len(idx), bs):
        chunk = [windows[j] for j in idx[i:i + bs]]
        yield chunk, collate(chunk)


@torch.no_grad()
def predict(model, windows, device, bs=256):
    """Returns rows (user, global_step, skill, question, y) and probabilities, in the same order."""
    model.eval()
    rows, probs = [], []
    for chunk, (inter, sk, qq, y, valid) in batches(windows, bs, False):
        p = torch.sigmoid(model(inter.to(device), sk.to(device), qq.to(device))).cpu()
        for i, (user, start, s, c, q) in enumerate(chunk):
            for t in range(1, len(s)):
                rows.append((user, start + t, s[t], q[t], c[t])); probs.append(p[i, t - 1].item())
    return rows, np.array(probs)


def run_epoch(model, windows, opt, loss_fn, device, bs, clip):
    model.train(); tot, n = 0.0, 0
    for _, (inter, sk, qq, y, valid) in batches(windows, bs, True):
        inter, sk, qq, y, valid = (t.to(device) for t in (inter, sk, qq, y, valid))
        m = valid[:, 1:]
        loss = loss_fn(model(inter, sk, qq)[m], y[:, 1:][m])
        opt.zero_grad(); loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), clip)        # gradient clipping
        opt.step()
        tot += loss.item() * m.sum().item(); n += m.sum().item()
    return tot / n


def baselines(train, test, prior, decay=0.85):
    """Three simple predictors on exactly the same answers:
       skill average    = how often training students got this skill right
       question average = how often training students got this exact question right (shrunk to the skill average)
       recency formula  = the formula the app used before the model (recent answers count more)"""
    qt, qc = defaultdict(int), defaultdict(int)
    for _, s, c, q in train:
        for k, v, qi in zip(s, c, q):
            qt[qi] += 1; qc[qi] += v
    out = {}
    for user, s, c, q in test:
        num, den = {}, {}
        for t in range(1, len(s)):
            for k in num:
                num[k] *= decay; den[k] *= decay
            num[s[t - 1]] = num.get(s[t - 1], 0) + c[t - 1]; den[s[t - 1]] = den.get(s[t - 1], 0) + 1
            k, qi = s[t], q[t]
            q_avg = (qc[qi] + 2 * prior[k]) / (qt[qi] + 2) if qi != 1 else prior[k]
            out[(user, t)] = (prior[k], q_avg, (num.get(k, 0) + prior[k]) / (den.get(k, 0) + 1))
    return out


def scores(y, p):
    return {"auc": round(roc_auc_score(y, p), 4), "accuracy": round(accuracy_score(y, p >= 0.5), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["assist", "is201"])
    ap.add_argument("--model", choices=["dkt", "dktq", "sakt"], default="dktq")
    ap.add_argument("--cell", choices=["lstm", "gru"], default="gru", help="RNN cell for dkt / dktq")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--emb", type=int, default=64)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--heads", type=int, default=4, help="attention heads (sakt)")
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--max-len", type=int, default=100)
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--patience", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    set_seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    name = a.model if a.model == "sakt" else f"{a.model}-{a.cell}"
    stem = f"{name}_{a.dataset}"
    print(f"model: {name}   device: {device}")

    splits = pickle.load(open(P("data", "processed", f"{a.dataset}_sequences.pkl"), "rb"))
    if len(splits["train"][0]) != 4:
        raise SystemExit("Old data format: run  python prepare_data.py " + a.dataset + "  again first.")
    meta = json.load(open(P("data", "processed", f"{a.dataset}_meta.json"), encoding="utf-8"))
    K, NQ = meta["n_skills"], meta["n_questions"]
    tr, va, te = (windows_of(splits[k], a.max_len) for k in ("train", "val", "test"))
    print(f"skills={K}  questions={NQ - 2}  windows train/val/test = {len(tr)}/{len(va)}/{len(te)}")

    cfg = {"emb": a.emb, "hidden": a.hidden, "dropout": a.dropout, "cell": a.cell, "heads": a.heads, "max_len": a.max_len}
    model = build_model(a.model, K, NQ, cfg).to(device)
    print("trainable parameters:", sum(p.numel() for p in model.parameters() if p.requires_grad))
    opt = torch.optim.Adam(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="max", factor=0.5, patience=1)
    loss_fn = nn.BCEWithLogitsLoss()
    os.makedirs(P("saved"), exist_ok=True); os.makedirs(P("results"), exist_ok=True)
    w_path = P("saved", f"{stem}.pt")

    hist, best, bad = [], -1.0, 0
    for ep in range(1, a.epochs + 1):
        t0 = time.time()
        tl = run_epoch(model, tr, opt, loss_fn, device, a.batch, a.clip)
        rows, p = predict(model, va, device)
        y = np.array([r[4] for r in rows])
        v_auc = roc_auc_score(y, p)
        v_loss = float(-np.mean(y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9)))
        sched.step(v_auc)
        lr = opt.param_groups[0]["lr"]
        hist.append({"epoch": ep, "train_loss": tl, "val_loss": v_loss, "val_auc": v_auc, "lr": lr})
        print(f"epoch {ep:2d}  train_loss {tl:.4f}  val_loss {v_loss:.4f}  val_auc {v_auc:.4f}  lr {lr:.1e}  ({time.time()-t0:.0f}s)")
        if v_auc > best + 1e-4:
            best, bad = v_auc, 0
            torch.save(model.state_dict(), w_path)
        else:
            bad += 1
            if bad >= a.patience:
                print("early stopping"); break

    model.load_state_dict(torch.load(w_path, map_location=device))
    rows, p_model = predict(model, te, device)
    base = baselines(splits["train"], splits["test"], meta["prior"])
    b = np.array([base[(r[0], r[1])] for r in rows])
    y = np.array([r[4] for r in rows])
    label = {"dkt": "DKT", "dktq": "DKT-Q", "sakt": "SAKT"}[a.model] + (f" ({a.cell.upper()})" if a.model != "sakt" else " (attention)")
    test = {label: scores(y, p_model), "Baseline: skill average": scores(y, b[:, 0]),
            "Baseline: question average": scores(y, b[:, 1]), "Baseline: recency formula (old app)": scores(y, b[:, 2])}

    names = meta.get("skill_names", {})
    with open(P("results", f"test_predictions_{stem}.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["student", "step", "skill_index", "skill_name", "question_index", "actual_correct",
                     f"p_{name}", "p_skill_average", "p_question_average", "p_recency_formula"])
        for r, pm, bb in zip(rows, p_model, b):
            wr.writerow([r[0], r[1], r[2], names.get(str(r[2]), ""), r[3], r[4], round(pm, 4), *(round(x, 4) for x in bb)])

    metrics = {"model": name, "dataset": meta["dataset"], "source": meta["source"], "device": device,
               "n_skills": K, "n_questions": NQ - 2, "students": meta["stats"], "epochs_trained": len(hist),
               "best_val_auc": round(best, 4), "test": test, "test_predictions": len(y),
               "hyperparameters": vars(a), "history": hist}
    json.dump(metrics, open(P("results", f"metrics_{stem}.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    keep = {k: meta[k] for k in ("dataset", "n_skills", "n_questions", "skill_map", "skill_names", "prior", "question_topic", "question_map") if k in meta}
    if a.dataset == "assist":
        keep.pop("question_map", None)          # large; only needed for the IS201 app model
    json.dump(dict(keep, model=a.model, name=name, config=cfg, best_val_auc=round(best, 4)),
              open(P("saved", f"{stem}_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    comp = P("results", f"comparison_{a.dataset}.csv")
    new = not os.path.exists(comp)
    with open(comp, "a", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        if new:
            wr.writerow(["time", "model", "val_auc", "test_auc", "test_accuracy", "epochs", "emb", "hidden", "dropout",
                         "lr", "batch", "weight_decay", "max_len", "heads", "base_skill_auc", "base_question_auc", "base_recency_auc"])
        wr.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), name, round(best, 4), test[label]["auc"], test[label]["accuracy"],
                     len(hist), a.emb, a.hidden, a.dropout, a.lr, a.batch, a.weight_decay, a.max_len,
                     a.heads if a.model == "sakt" else "", test["Baseline: skill average"]["auc"],
                     test["Baseline: question average"]["auc"], test["Baseline: recency formula (old app)"]["auc"]])
    plot_curves(hist, stem)
    if a.dataset == "is201":
        activate_if_best(name, best)
    print(json.dumps(test, indent=1))


def activate_if_best(name, val_auc):
    path = P("saved", "active_is201.json")
    cur = json.load(open(path)) if os.path.exists(path) else None
    if cur is None or cur["model"] == name or val_auc >= cur["val_auc"]:
        json.dump({"model": name, "val_auc": round(val_auc, 4)}, open(path, "w"), indent=1)
        print(f"-> the app now uses {name} (validation AUC {val_auc:.4f})")
    else:
        print(f"-> the app keeps {cur['model']} (validation AUC {cur['val_auc']} is higher)")


def plot_curves(hist, stem):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ep = [h["epoch"] for h in hist]
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    ax[0].plot(ep, [h["train_loss"] for h in hist], label="train", color="#2a78d6", linewidth=2)
    ax[0].plot(ep, [h["val_loss"] for h in hist], label="validation", color="#eb6834", linewidth=2)
    ax[0].set_title("Loss (binary cross-entropy)", loc="left"); ax[0].set_xlabel("epoch"); ax[0].legend(frameon=False)
    ax[1].plot(ep, [h["val_auc"] for h in hist], color="#2a78d6", linewidth=2)
    ax[1].set_title("Validation AUC", loc="left"); ax[1].set_xlabel("epoch")
    for a_ in ax:
        a_.spines[["top", "right"]].set_visible(False); a_.grid(alpha=.25)
    fig.suptitle(f"Training - {stem}")
    fig.tight_layout(); fig.savefig(P("results", f"training_curves_{stem}.png"), dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
