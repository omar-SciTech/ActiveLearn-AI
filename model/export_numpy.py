"""Copy trained PyTorch weights into .npz files so predictor_np.py can run without PyTorch.

  python export_numpy.py              # every DKT / DKT-Q model of the IS201 dataset
  python export_numpy.py dktq-gru     # one model

Run it again after retraining (train.py also calls it for the model the app uses).
"""
import glob, json, os, sys
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = os.path.join(HERE, "saved")


def export(name, dataset="is201"):
    stem = f"{name}_{dataset}"
    meta = json.load(open(os.path.join(SAVED, f"{stem}_meta.json"), encoding="utf-8"))
    if meta["model"] not in ("dkt", "dktq"):
        print(f"skip {stem}: numpy inference supports DKT and DKT-Q only")
        return False
    state = torch.load(os.path.join(SAVED, f"{stem}.pt"), map_location="cpu")
    np.savez(os.path.join(SAVED, f"{stem}.npz"), **{k: v.numpy() for k, v in state.items()})
    print(f"saved/{stem}.npz written")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        export(sys.argv[1])
    else:
        for meta in sorted(glob.glob(os.path.join(SAVED, "*_is201_meta.json"))):
            export(os.path.basename(meta)[:-len("_is201_meta.json")])
