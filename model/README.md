# AI part – knowledge tracing in PyTorch (DKT, DKT-Q, SAKT)

The model reads a student's answers in order and predicts the probability that the student answers
a given question correctly. The app averages these predictions per chapter, picks the next question
from the weakest chapter and says "Review Chapter X".

## The three models (all in `dkt.py`)
| `--model` | Name | How it works |
|---|---|---|
| `dkt` | DKT (Piech et al., 2015) | RNN (LSTM or GRU) over (skill, correct?) → P(correct) for every skill. Sees only the **skill** |
| `dktq` | DKT-Q (question-aware DKT) | Same RNN, but it also sees **which question** was answered and predicts the next question directly: [RNN state ; embedding(next question) ; embedding(next skill)] → MLP → sigmoid. Learns the difficulty of every question |
| `sakt` | SAKT (Pandey & Karypis, 2019) | **Self-attention** (Transformer block): the next question is the query, past answers are keys/values, with a causal mask so it only sees the past |

`--cell lstm` or `--cell gru` chooses the RNN for `dkt` / `dktq` (default GRU).

## Files
| File | What it does |
|---|---|
| `dkt.py` | The three models + batching helpers |
| `prepare_data.py` | Cleans the data, builds the sequences (skill, correct, question), splits 80/10/10 **by student** |
| `train.py` | Trains one model, evaluates it on unseen students against 3 baselines, logs every run |
| `predictor.py` | Loads the app's model and turns a history into predictions (used by the backend) |
| `predict_all.py` | Predictions for every student in the database → `topic_mastery` + CSV files |
| `data/raw/` | `skill_builder_data_corrected_collapsed.csv` (ASSISTments, downloaded) |
| `data/processed/` | `<dataset>_sequences.pkl` + `<dataset>_meta.json` |
| `saved/` | `<model>_<dataset>.pt` + `_meta.json`; `active_is201.json` = the model the app uses |
| `results/` | `comparison_<dataset>.csv` (one row per run), `metrics_…json`, `training_curves_…png`, `test_predictions_…csv`, `is201_student_predictions.csv`, `is201_question_predictions.csv` |

## Running without PyTorch
`export_numpy.py` copies the weights of the DKT / DKT-Q models into `saved/*.npz` (train.py does it automatically
for the model the app uses). `predictor_np.py` runs the same forward pass with numpy only; its predictions match
PyTorch to within 1e-6. The backend uses it automatically when PyTorch is not installed (e.g. on free hosting).

## Datasets
| Dataset | Data | Why |
|---|---|---|
| `assist` | **Real** answers: ASSISTments 2009-2010 skill builder (corrected, collapsed) – ~3,850 students, 149 skills | Proves the method works on real students |
| `is201` | Our 60-question IS201 bank answered by **simulated** students (`database/simulate_students.py`) | The model used inside the app (its inputs are our chapters and questions). Retrain on real answers later: `analysis/export_for_ai.py` → `prepare_data.py is201 --from-export ../analysis/exports/attempts_sequences.csv` |

## Training choices (DLS)
Adam + L2 weight decay · shuffled mini-batches · dropout · gradient clipping · learning-rate decay
(ReduceLROnPlateau) · early stopping with best weights · Xavier init · train/validation/test split by student ·
sequences cut into windows of `--max-len` answers. Hyperparameters are chosen by **validation** AUC;
the test set is only used for the final numbers.

Baselines on exactly the same test answers: skill average, question average, and the recency formula the app used before.

## Run (GPU is used automatically)
```
python prepare_data.py assist
python train.py assist --model dkt --cell lstm
python train.py assist --model dkt --cell gru
python train.py assist --model dktq
python train.py assist --model sakt

python prepare_data.py is201
python train.py is201 --model dktq      # the best validation AUC automatically becomes the app's model
python predict_all.py                   # after backend/seed.py has built the database
```
Then open `results/comparison_assist.csv` / `comparison_is201.csv` to compare all runs.

## ASSISTments results (real students, test set = 10% of students never seen in training)
Trained on a laptop GPU (RTX 2050). Files: `results/comparison_assist.csv`, `results/metrics_*_assist.json`,
`results/training_curves_*_assist.png`, weights in `saved/*_assist.pt`.

| Model | Validation AUC | Test AUC | Test accuracy |
|---|---|---|---|
| **DKT-Q (GRU)** | **0.783** | **0.776** | **0.741** |
| DKT (GRU) | 0.769 | 0.759 | 0.734 |
| SAKT (attention) | 0.767 | 0.757 | 0.729 |
| Baseline: recency formula | – | 0.701 | – |
| Baseline: question average | – | 0.697 | – |
| Baseline: skill average | – | 0.628 | – |

The raw CSV (~60 MB) is not in the repository. Download `skill_builder_data_corrected_collapsed.csv` from the
[ASSISTments 2009-2010 page](https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010)
into `data/raw/`, then run `python prepare_data.py assist`.

## IS201 results (simulated students, test set = 300 unseen students)
| Model | Validation AUC | Test AUC | Test accuracy |
|---|---|---|---|
| DKT (LSTM) | 0.698 | 0.687 | 0.760 |
| DKT (GRU) | 0.703 | 0.690 | 0.758 |
| **DKT-Q (GRU)** – used by the app | **0.795** | **0.788** | **0.785** |
| SAKT (attention) | 0.788 | 0.779 | 0.776 |
| Baseline: question average | – | 0.714 | – |
| Baseline: recency formula (old app) | – | 0.650 | – |
| Baseline: skill average | – | 0.538 | – |
