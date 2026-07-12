# Vision ground-truth benchmark

Measure **per-field exact-match accuracy** of the NumisLens tiered OCR + VLM photo-identification and grading pipeline. The harness runs coin image pairs through each tier and through the agreement gate, then scores outputs against staged truth.

## What it measures

| Stage | Role |
|-------|------|
| **OCR (T1)** | PaddleOCR-VL transcription |
| **VLM (T2)** | Qwen vision calls (series, date, mintmark, grade) |
| **Gate** | Deterministic agreement — disagreements escalate, never guessed |

The runner reports per-tier accuracy (**OCR alone**, **VLM alone**), **post-gate** accuracy, and **escalation rate**.

- **Date** and **mintmark** — scored **separately**, **strict exact match** after canonicalization.
- **Series** — exact match on canonical name.
- **Grade** — photo-grade **condition bucket** only: `AG`, `G`, `VG`, `F`, `VF`, `XF`, `AU`, `UNC`. Never an MS number.

## Staging ground truth (~20 coins)

Photograph **~20 of your own coins** with **known** attributions. Vary series, dates, mintmarks (including no mintmark), **grades**, and **lighting**.

For each coin:

1. Capture **obverse** and **reverse** images.
2. Record truth: `series`, `year`, `mintmark`, `grade_bucket`.
3. Store images (e.g. under `vision/bench/images/`).
4. Add an entry to `vision/bench/ground_truth.json` following `ground_truth.example.json`.

Set any `truth` field to `null` to **skip scoring** that field for that coin.

## Schema

```json
{
  "image_pairs": [
    {
      "id": "1943-d-steel",
      "obverse": "images/1943-d-obv.jpg",
      "reverse": "images/1943-d-rev.jpg",
      "truth": {
        "series": "Lincoln Wheat Cent",
        "year": 1943,
        "mintmark": "D",
        "grade_bucket": "VF"
      },
      "synthetic": false
    }
  ]
}
```

- `obverse` / `reverse` — paths **relative to the JSON file**.
- `truth.mintmark` — letter (`P`, `D`, `S`, …) or **`null` if the coin has no mintmark**.
- Any `truth` field may be `null` to exclude it from scoring.

## Synthetic smoke entry

`ground_truth.example.json` includes one entry with `"obverse": "synthetic"`, `"reverse": "synthetic"`, and `"synthetic": true`. It proves the harness executes without real photos.

This entry is **excluded from all accuracy numbers**. It exists in the example only — never cite it in results.

## Running

Activate the vision venv, then from `vision/`:

```bash
python bench/runner.py bench/ground_truth.json
```

Omit the path to default to `bench/ground_truth.json`.

OCR and VLM endpoints must be reachable:

- `VISION_OCR_URLS` — comma-separated OCR base URL(s)
- `VISION_VLM_URL` — VLM base URL

The runner does not touch the daemon or database.

## Interpreting output

Summary lines show exact-match counts per field per stage, plus escalations across real pairs. Low post-gate vs per-tier scores usually mean OCR/VLM disagreement (gate working as designed). Escalation is expected on weak mintmarks and key dates.

## Accuracy claims

**Only real staged coins count.** Never include the synthetic smoke entry in published or comparative accuracy numbers. Re-run after prompt, model, or gate changes.
