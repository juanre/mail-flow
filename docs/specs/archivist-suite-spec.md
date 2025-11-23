# Archivist Classifier Suite – Single‑File Specification (Core + LLM)

Purpose: Deliver a general, trainable decision‑maker that selects a workflow for any piece of text + metadata, with first‑class LLM assistance and production‑grade vector search. This spec combines the core classifier and the LLM plugin into one document for implementation.

--------------------------------------------------------------------------------

## 1) Goals & Non‑Goals

Goals
- Select a workflow (“label”) for text + metadata, given a list of candidate workflows (name + description + tags).
- Learn from user confirmations/corrections (feedback) over time.
- Use multiple advisors: Rules, Local Similarity, Vector KNN (pgvector/pgdbm), and LLM (llmring).
- Persist decisions, feedback, and (optionally) embeddings for auditability and improved performance.

Non‑Goals
- Not a general ML platform; no heavy pipelines. Keep scope minimal, testable, and optional features as plugins.
- Not a server by default; provide a Python library. (CLI helpers optional.)

--------------------------------------------------------------------------------

## 2) High‑Level Architecture

Inputs
- text: string (subject/body preview/filename excerpt/any text)
- meta: dict (source=email/slack/fs/hn, sender/recipient/channel/date/filename/mimetype, etc.)
- workflows: list[{name, description, tags?}] (allowed labels)

Advisors (run in order, configurable)
1) RulesAdvisor: keyword/pattern matches on text/meta/workflow descriptions.
2) LocalSimilarityAdvisor: token Jaccard or TF‑IDF vs confirmed examples.
3) VectorAdvisor: semantic KNN using Postgres + vector extension (pgvector or “pgdbm”). Dev fallback: brute‑force cosine (NumPy) when DB unavailable.
4) LLMAdvisor: constrained‑choice selection via llmring (first‑class, budget/cached).

Decision Policy
- Compute per‑advisor outputs (label, confidence, evidence). Choose best non‑LLM result.
- If best ≥ high_threshold (default 0.85): accept.
- If medium ≤ best < high and LLM enabled: call LLM to confirm/rerank.
- If best < medium and LLM enabled: call LLM.
- If still low or LLM disabled: return low‑confidence result and let caller ask user.
- Interactive/Learning mode: if `opts.interactive=True` (or global “interactive/learning” mode), always present a small top‑K (e.g., 3) ranked suggestions with advisors_used + brief evidence and allow the user to confirm/correct. Persist the selection via `feedback()` and treat it as a confirmed example. When interactive is on, the user choice takes precedence regardless of thresholds.
- Persist advisors_used + per‑advisor scores + evidence into decisions.

Learning
- Log every decision. Feedback (corrections) converts decisions into confirmed examples.
- Examples are derived from decisions (+feedback) — no separate “examples” table as source of truth. Use a view or materialized view for performance.

--------------------------------------------------------------------------------

## 3) Public API (Python)

Types
```
from typing import TypedDict, Optional, Any

class ClassifyOpts(TypedDict, total=False):
    high_threshold: float        # default 0.85
    medium_threshold: float      # default 0.50
    allow_llm: bool              # default True
    allow_vectors: bool          # default True
    max_candidates: int          # default 5
    interactive: bool            # default False

class Workflow(TypedDict):
    name: str
    description: str
    tags: list[str] | None

class Decision(TypedDict, total=False):
    decision_id: int | None      # set when persisted
    label: str
    confidence: float            # 0..1
    advisors_used: list[str]
    scores: dict[str, float]     # per‑advisor scores
    evidence: dict[str, Any]     # matches, neighbors, LLM rationale
    created_at: str
```

Core Classifier
```
class Classifier:
    @staticmethod
    def from_env() -> "Classifier":
        """Create from env/config; connect to DB + set up advisors/policy."""

    def classify(
        self,
        text: str,
        meta: dict,
        workflows: list[Workflow],
        opts: Optional[ClassifyOpts] = None,
    ) -> Decision:
        """Run advisors + policy; persist decision; return Decision."""

    def feedback(self, decision_id: int, correct_label: str, reason: str | None = None) -> None:
        """Persist user correction; future examples derive from this."""

    def train(self, label: str, text: str, meta: dict) -> None:
        """Optional explicit training (bootstrapping)."""

    def get_metrics(self) -> dict:
        """Return basic metrics (counts, recent top‑1 accuracy if evaluated)."""
```

--------------------------------------------------------------------------------

## 4) Storage (Production: Postgres + Vector Extension)

Recommended: Postgres + pgvector. If the organization mandates “pgdbm” (linked), adapt vector DDL/operator syntax and implement a vector adapter layer.

DDL (pgvector syntax shown)
```
CREATE EXTENSION IF NOT EXISTS vector;  -- swap if using a different extension

CREATE TABLE workflows (
  name text PRIMARY KEY,
  description text NOT NULL,
  tags jsonb DEFAULT '[]'::jsonb
);

CREATE TABLE decisions (
  id bigserial PRIMARY KEY,
  input_hash text NOT NULL,
  text text NOT NULL,
  meta_json jsonb NOT NULL,
  suggested_label text NOT NULL,
  suggested_conf double precision NOT NULL,
  advisors_json jsonb NOT NULL,
  workflows_json jsonb NOT NULL,  -- workflows list passed to classify()
  created_at timestamptz DEFAULT now()
);
CREATE INDEX ON decisions (created_at DESC);
CREATE INDEX ON decisions (suggested_label);

CREATE TABLE feedback (
  id bigserial PRIMARY KEY,
  decision_id bigint NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
  correct_label text NOT NULL,
  reason text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX ON feedback (decision_id);

-- Embeddings table (pgvector; adapt if using another extension)
CREATE TABLE embeddings (
  id bigserial PRIMARY KEY,
  decision_id bigint NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
  label text NOT NULL,
  backend text NOT NULL DEFAULT 'pgvector',
  dim int NOT NULL,
  embedding vector(768) NOT NULL,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON embeddings (label);

-- Confirmed examples for training
CREATE VIEW examples AS
SELECT d.id AS decision_id,
       coalesce(f.correct_label, d.suggested_label) AS label,
       d.text,
       d.meta_json
FROM decisions d
LEFT JOIN feedback f ON f.decision_id = d.id
WHERE f.correct_label IS NOT NULL
   OR (f.correct_label IS NULL AND d.suggested_conf >= 0.85);
```

Vector Query (pgvector)
```
-- Given $1::vector query, $2::text[] allowed labels or NULL, $3::int k
SELECT d.id, e.label, 1 - (e.embedding <=> $1::vector) AS score
FROM embeddings e
JOIN decisions d ON d.id = e.decision_id
WHERE ($2 IS NULL OR e.label = ANY ($2))
ORDER BY e.embedding <=> $1::vector
LIMIT $3;
```

Adapter Layer
- Implement a `VectorBackend` interface with methods:
  - embed(text: str) -> vector
  - knn(query_vector, labels_filter: list[str] | None, k: int) -> list[(decision_id, label, score)]
- Provide a pgvector/pgdbm implementation; and a dev fallback (NumPy cosine brute force) that reads embeddings from memory or a lightweight store.

--------------------------------------------------------------------------------

## 5) Advisors

Common Interface
```
class Advisor:
    name: str
    def advise(self, text: str, meta: dict, workflows: list[Workflow]) -> tuple[str | None, float, dict]:
        """Return (label, confidence, evidence). Label may be None; confidence 0..1."""
```

Implementations
- RulesAdvisor
  - Use keyword patterns (e.g., ‘invoice’, ‘receipt’, tags from workflow descriptions).
  - Confidence from keyword density/weights; evidence = matched terms.
- LocalSimilarityAdvisor
  - Tokenize text/meta (simple regex tokens). Compare to confirmed examples (examples view) using Jaccard/TF‑IDF.
  - Confidence scaled to [0,1]; evidence = top matches.
- VectorAdvisor
  - Embed text → vector; use vector backend knn() constrained by workflows; compute similarity = 1 − distance.
  - evidence = neighbors with scores.
- LLMAdvisor (llmring)
  - Constrained‑choice classification among workflows (name + 1–2 line description), JSON output only.
  - evidence = LLM rationale; confidence clamped to [0,1].

--------------------------------------------------------------------------------

## 6) Decision Policy

- Combine advisor outputs:
  - best_label, best_conf from {rules, local, vector};
  - if best_conf ≥ high_threshold: accept; advisors_used = those contributing; scores recorded.
  - elif best_conf ≥ medium_threshold and LLM allowed: call LLM; if LLM conf > best, pick LLM.
  - elif LLM allowed: call LLM; otherwise return best local with low confidence.
- Interactive/Learning mode: if interactive=True, present top‑K suggestions with brief evidence to the user for immediate confirmation/correction. Persist the final user choice via feedback(); treat it as a confirmed example.
- Persist advisors_used + scores + evidence as advisors_json in decisions.
- Return Decision with decision_id if persisted.

--------------------------------------------------------------------------------

## 7) LLM Integration (llmring)

Config (example)
```
{
  "enabled": true,
  "model": "claude-3-5-haiku",
  "temperature": 0.2,
  "max_tokens": 512,
  "budget_usd": 1.0,
  "cache_dir": "~/.cache/archivist-llm"
}
```

Prompts (JSON‑only outputs; enumerate allowed workflows). Provide templates for:
- classify_email: From/To/Subject/BodyPreview → {label, confidence, rationale, fields?}
- classify_file: Filename/Mimetype/Path/Context → {label, confidence, rationale}
- gate_email: {decision: bool, confidence, rationale}
- gate_slack: {decision: bool, confidence, rationale}

Policy Helpers
- Call LLM only below thresholds; include caching (hash of {prompt, model, allowed_labels, origin subset, text hash}).
- Track budget; stop calling when exceeded; return None (fallback to local).
- Retries: up to 2 on transient errors; on failure return None and log in advisors_json.

--------------------------------------------------------------------------------

## 8) Security & Privacy
- Default: do not send full content; only subject/from/filename or brief previews unless enabled.
- Redact sensitive tokens by configurable regex.
- Persist minimal text for audit; store input_hash for dedup.

--------------------------------------------------------------------------------

## 9) Configuration
- db.url (Postgres). If absent, run in dev mode (no vector advisor, or NumPy fallback).
- embeddings: {enabled: true, dim: 768}
- llm: as above.
- thresholds: {high: 0.85, medium: 0.50}

--------------------------------------------------------------------------------

## 10) CLI (Optional)
- ac-classify: stdin text + meta/workflows JSON → Decision JSON
- ac-feedback: record correction
- ac-train: add training example
- ac-inspect: show advisors_used + evidence
- ac-metrics: basic metrics

--------------------------------------------------------------------------------

## 11) Testing Plan

Unit (core)
- RulesAdvisor: keyword hits and negatives; tags influence.
- LocalSimilarity: closer tokens produce higher scores; cutoff behavior.
- VectorAdvisor: mocked backend returns closer neighbors for similar inputs; verify label & score.
- LLMAdvisor (stub): threshold gating, cache usage, budget limits, JSON coercion/clamping.
- Policy: no LLM above high; LLM called below medium; scores recorded; advisors_used order stable.
- Storage: decisions + feedback roundtrip; examples view returns expected rows.

Integration (env‑guarded)
- Postgres + vector extension end‑to‑end KNN; index exists and queries return meaningful neighbors.
- llmring integration with a fake provider; real LLM behind env flags.

Performance
- KNN latency within target bounds for N≈10k (smoke). Index tuning (ivfflat lists) documented.

--------------------------------------------------------------------------------

## 12) Implementation Notes
- Tokenization: lowercasing + `\b[\w.-]{2,}\b` is fine for MVP; swap later if needed.
- Advisors return label=None when they abstain; policy should ignore absent labels.
- Confidence blending: start with max non‑LLM; use weighted bump with other advisors; record raw scores.
- Calibration: record decisions vs. outcomes; later add calibration if necessary.
- Migrations: maintain a version table; ship SQL migrations.
- Vector Backend Adapter: isolate pgvector vs. "pgdbm" differences behind a small interface.

--------------------------------------------------------------------------------

## 13) Integration Contract (mailflow / slackstash / fileflow)
- Call `classify(text, meta, workflows)`; record Decision in item metadata:
  - origin.classifier = {label, confidence, advisors_used, …}
  - origin.classifier_llm (if used) = {label, confidence, rationale}
- On user confirmation/correction: call `feedback(decision_id, correct_label)`.

--------------------------------------------------------------------------------

## 14) Acceptance Criteria
- Library installs and initializes from env; production path uses Postgres + vector extension; dev fallback works.
- classify() returns structured, deterministic outputs; confidence in [0,1].
- LLM advisor obeys thresholds/budget; resilient to API errors; JSON‑only.
- decisions/feedback/embeddings persisted; examples view correct.
- Unit + integration tests pass; env‑gated tests skip cleanly without creds.

--------------------------------------------------------------------------------

## 15) Milestones
- v0: Core (Rules, LocalSimilarity), storage (decisions/feedback), LLM advisor with stub + policy, basic CLI.
- v0.1: Embeddings + VectorAdvisor (pgvector/pgdbm), ANN index, adapter; perf checks.
- v0.2: Caching/budget for LLM; confidence calibration tweaks; metrics.

