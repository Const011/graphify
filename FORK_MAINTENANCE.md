# Graphify fork maintenance (Const011 / GnttProject)

Track **our** changes vs [upstream graphify](https://github.com/safishamsi/graphify) (`upstream/v8`) so we can merge new releases without losing production behaviour.

| Remote | URL | Role |
|--------|-----|------|
| `origin` | `git@github.com:Const011/graphify.git` | Our fork |
| `upstream` | `https://github.com/safishamsi/graphify.git` | safishamsi master line (`v8` branch) |

**Active branch:** `feat/incremental-stitch-file-slice` — split PRs to upstream; see [PR status](#pr-status). Archive: `fork/archive/monolithic-pr-1326`.

**Upstream baseline (merged):** `upstream/v8` @ **0.8.43** (`435da06`). Last merge on fork branch: `3f55f5a`.

**Install in GnttProject:** `pip install -e BoT-assistant-shared/graphify` after `source graphify/env.sh` (see `graphify-test/rebuild-graphify.sh`). **Restart** pi-web / knowhow after reinstall so the processor picks up `llm.py` changes.

### Current delta vs `upstream/v8`

Files that differ from upstream (fork-owned or pending upstream PR):

| File | Fork change |
|------|-------------|
| `graphify/stitch.py` | Cross-file stitch (#1371 candidate) |
| `graphify/llm_json_parser.py` | Gemma JSON recovery (#2 candidate) |
| `graphify/llm.py` | Import parser; `GRAPHIFY_EXTRACTION_SUFFIX`; hollow guard; Gemma `reasoning_effort` skip; **`_coerce_semantic_units`** (FileSlice pass-through — upstream #1369 gap) |
| `graphify/__main__.py` | Manifest stamp; incremental `prune_sources`; incremental safety |
| `graphify/build.py` | `path_covered_by_extraction` and path-alias helpers (manifest PR) |
| `tests/test_stitch.py` | Stitch tests |
| `tests/test_llm_parser.py` | Parser / thought-block tests |
| `tests/test_llm_backends.py` | Gemma `reasoning_effort` tests |
| `tests/test_build.py` | Incremental prune + upstream root-collapse test |

**Upstream only (do not fork):** `graphify/file_slice.py`, `tests/test_file_slice.py`, `tests/test_chunking.py` — take `theirs` on every sync (#1369).

Quick check after each sync:

```bash
git fetch upstream
git diff upstream/v8 --name-only
git log --oneline upstream/v8..HEAD
```

---

## Production choices (validated 2026-06)

| Setting | Value |
|---------|--------|
| Local graph build (Ollama) | `gemma4:4E` |
| Context | `OLLAMA_NUM_CTX=16384`, margin 2048 → token-budget ~7168 |
| Doc corpus prompt | `graphify-test/smoke-extraction-env.sh` → `GRAPHIFY_EXTRACTION_SUFFIX` |
| Cloud fallback | Google `gemma-4-31b-it` via `graphify/env.sh` / `pi-web/start.sh` → `GRAPHIFY_GEMINI_MODEL` |
| Smoke corpus | `graphify-test/corpus-smoke/` — 8 markdown files incl. large `PMBOK8.md` (~1 MB) |

Reference runs (small corpus, pre-PMBOK8): `ollama-gemma4-4E-smoke` — 41 nodes, 32 edges, 100% traceable, 8/8 files.

**Detail levers (smoke findings):** clustering does **not** reduce node count vs `--no-cluster`. Large-doc coverage comes from upstream **#1369** slicing (`expand_oversized_files` before pack). Prompt density is capped by `GRAPHIFY_EXTRACTION_SUFFIX` (“3–8 nodes per file” in smoke env).

### Knowhow processor (MVP6)

The central knowhow processor (`MVP6-knowledge-mgmt/ingest/knowhow/processor.py`) **always** invokes:

```bash
python -m graphify extract {projectDir} --out {projectDir}/.pi/knowhow \
  --backend gemini --model gemma-4-31b-it \
  --max-concurrency 4 --api-timeout 900
```

Init (no usable graph): processor **removes** `.pi/knowhow/graphify-out/` when `graph.json` is missing or has 0 nodes. Incremental: `graph.json` (≥1 node) **and** `manifest.json` file present — graphify prints `incremental scan of …`. The fork stamps a non-empty manifest when extract succeeds; **reinstall the fork** (`pip install -e`) for that behaviour locally. Upstream merge: [PR #1384](https://github.com/safishamsi/graphify/pull/1384) (branch `fix/extract-manifest-source-path`).

| Graph state | graphify mode | Knowhow phase |
|-------------|---------------|---------------|
| No `graph.json`, or empty graph (0 nodes) | Full semantic init (`scanning …`) | **init** — wipe `graphify-out/` |
| Non-empty `graph.json` + `manifest.json` exists | Incremental semantic extract (clustered) | **incremental** |

**Do not** route knowhow markdown through `graphify update` — that path is AST/code-only (`watch._rebuild_code`) and skips semantic LLM extraction.

### Working extract flags (knowhow production)

| Flag / env | Knowhow default | Effect |
|------------|-----------------|--------|
| `--backend gemini --model gemma-4-31b-it` | yes | Explicit backend when `GRAPHIFY_GEMINI_MODEL` is set |
| `GRAPHIFY_EXTRACTION_SUFFIX` | yes (`smoke-extraction-env.sh`) | Document-only prompt rules |
| Clustering | **on** (`KNOWHOW_GRAPHIFY_NO_CLUSTER=0`) | Community detection for search/navigation; failed init exits 1 with no graph/manifest |
| `--max-concurrency 4` | yes | Throughput |
| `--api-timeout 900` | yes | Timeout |
| Wipe `graphify-out/` before init | yes | Avoids stale cache; `reset_graphify_out()` on init |

**Failed init (clustered):** When the LLM returns no parseable JSON, graphify exits 1 and writes **neither** `graph.json` nor `manifest.json`. Incremental re-extract failure aborts with `incremental update aborted — existing graph.json and manifest unchanged` (graph preserved).

**Gemma `<thought>` preamble:** `gemma-4-31b-it` emits `<thought>…</thought>` (or unclosed `<thought>` before JSON). Not `<think>` — that is Cursor UI labelling, not model output.

**Validated smoke (2026-06-18, small corpus):** `graphify-test/run-smoke-gemma.sh` — clustered extract; 24 nodes, 16 links, 8 communities, 8/8 files.

**PMBOK8 + slicing (2026-06-19):** `run-smoke-gemma-detail-compare.sh` with `--token-budget 16000` (`gemma-smoke-slice-16k`) — **125 nodes**, 113 edges, 35 communities, **99 PMBOK8 nodes** (vs 5 before #1369 + FileSlice fix). Default 60k budget / cluster vs `--no-cluster` still ~26 nodes — slicing only activates when pack yields `FileSlice` chunks. Requires fork `_coerce_semantic_units` (upstream 0.8.43 still coerces slices to `Path` and fails).

### Incidents fixed (2026-06-18, knowhow + fork)

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Extract succeeds but knowhow reports “graph.json missing or empty” | Clustered `graph.json` uses NetworkX node-link format (`links`, not `edges`); `GraphCounts.from_graph_json` required `edges` | Knowhow `graphify_run_log.py` — count `edges` or `links` |
| Second promoted doc wipes graph, full re-init | After first extract, `manifest.json` was `{}`; knowhow required non-empty manifest → **init + reset** | Fork `__main__.py` manifest stamp + knowhow `graphify_incremental_ready()` aligned with graphify gate |
| Incremental re-extract, tokens spent, graph delta +0 | `_incremental_prune` included re-extracted paths; `build_merge` `prune_sources` deleted fresh nodes | Fork `__main__.py` — `prune_sources=deleted_files` only |
| Large doc only partially extracted | Pre-#1369: `_FILE_CHAR_CAP` truncated unsplit files | **Upstream #1369** — slice before pack; fork takes upstream `file_slice.py` |
| `--token-budget 16000` extract: all chunks fail `not 'FileSlice'` | Upstream #1369 packs `FileSlice` into chunks but `extract_files_direct` did `[Path(f) for f in files]` | Fork `llm.py` — `_coerce_semantic_units()`; regression in `tests/test_file_slice.py` |

Knowhow patches (outside graphify git repo): `MVP6-knowledge-mgmt/ingest/knowhow/graphify_run_log.py`, `graphify_cli.py`, `graphify_trigger.py`; tests in `ingest/tests/test_graphify_*.py`.

### Google Gemini / Gemma (`backend=gemini`)

Production uses **`gemma-4-31b-it`** through Google’s OpenAI-compatible endpoint (`graphify/env.sh`, `MVP3-html-tui/pi-web/start.sh`).

Upstream `BACKENDS["gemini"]` sets `"reasoning_effort": "low"` for the default **`gemini-3-flash-preview`**. That parameter is valid for Gemini Flash, but **Gemma models reject it**:

```text
400 INVALID_ARGUMENT: Thinking level is not supported for this model.
```

**Symptom:** knowhow / `graphify extract --backend gemini` fails every semantic chunk with the above error when `GRAPHIFY_GEMINI_MODEL=gemma-4-31b-it` (or any `gemma*` model).

**Fork fix (`graphify/llm.py`):**

- `_supports_reasoning_effort(model)` — returns `False` when the model id starts with `gemma` (after stripping an optional `provider/` prefix).
- `_call_openai_compat` — only adds `reasoning_effort` to the API kwargs when `_supports_reasoning_effort(model)` is true.

Previously the guard existed only on the **dedup** LLM path; **extract** still sent `reasoning_effort: "low"` and broke Gemma.

**Tests:** `tests/test_llm_backends.py` — `test_call_openai_compat_skips_reasoning_effort_for_gemma`, `test_call_openai_compat_sends_reasoning_effort_for_gemini_flash`.

**After changing `llm.py`:** `pip install -e BoT-assistant-shared/graphify` and restart the knowhow processor / pi-web.

**Upstream:** same bug on `v8` @ 0.8.43 — candidate PR **#3** to Safi.

---

## Change inventory

### A. PR #1326 — committed on `feat/incremental-stitch-file-slice`

Core fork features still not fully upstream (merge carefully; upstream may add overlapping fixes):

| Area | Files | What |
|------|-------|------|
| **Incremental safety** | `graphify/__main__.py`, `graphify/build.py`, `tests/test_build.py`, `tests/test_extract.py` | Abort incremental extract on failed/empty re-extract; safe prune; no silent graph shrink |
| **Cross-file stitch** | `graphify/stitch.py`, `tests/test_stitch.py` | Post-merge `references` edges from changed docs → existing graph (backticks + paths); `new_node_ids` for wrong LLM `source_file` |
| **Docs / version** | `CHANGELOG.md`, `README.md`, `pyproject.toml` | PR description material |

**Note:** Early PR commits added OpenRouter/`GOOGLE_BYOK` in `llm.py`. Upstream **v8** later shipped `#1273` (custom `OPENAI_BASE_URL` / env keys). On merge, prefer **upstream** OpenAI config; keep stitch/incremental logic from our branch.

**File slicing (#1369):** **merged upstream** @ 0.8.43. Track `upstream/v8` only — no fork overrides, no fork-specific slice tests.

Other commits on the branch may include upstream merges — treat as **upstream**, not fork-specific.

---

### B. Fork deltas on `feat/incremental-stitch-file-slice` (committed; vs `upstream/v8` @ 0.8.43)

**Status (2026-06-19):** on branch after merge; **upstream submission** tracked in [PR status](#pr-status).

| Change | File(s) | Purpose | Upstream PR |
|--------|---------|---------|-------------|
| **Manifest path alias on extract** | `graphify/__main__.py`, `graphify/build.py` | `path_covered_by_extraction(f, sem_result, target)` instead of `f in _sem_extracted` — detect absolute paths vs relative LLM `source_file` | **#1384** submitted (`fix/extract-manifest-source-path`; includes `tests/test_extract_manifest.py` on that branch) |
| **Incremental prune_sources** | `graphify/__main__.py` | `prune_sources=deleted_files` only — re-extracted paths must not be pruned after merge | **#4** pending |
| **Split JSON recovery** | `graphify/llm_json_parser.py` | Heal Gemma split envelopes; merge multiple top-level JSON objects | **#2** pending |
| **Strip Gemma `<thought>` preamble** | `graphify/llm_json_parser.py` | `strip_model_thought_blocks()` before JSON parse | **#2** pending |
| **Wire parser in `llm.py`** | `graphify/llm.py` | `from graphify.llm_json_parser import parse_llm_json as _parse_llm_json` — no shadow `_parse_llm_json` in `llm.py` | **#2** pending |
| **`GRAPHIFY_EXTRACTION_SUFFIX`** | `graphify/llm.py` → `_extraction_system()` | Env-driven doc-mode rules (GnttProject smoke/knowhow) | Optional small upstream PR |
| **Intentional empty JSON (hollow guard)** | `graphify/llm.py` → `_response_is_hollow()`, `_is_intentional_empty_extraction()` | Valid `{"nodes":[],"edges":[]}` with `finish_reason=stop` is accepted; broken/partial JSON still relabelled for adaptive retry | **#2** / doc-extraction bugfix |
| **Skip `reasoning_effort` for Gemma** | `graphify/llm.py` | Gemma via `--backend gemini` rejects thinking level | **#3** pending |

**New module:** `graphify/llm_json_parser.py` — keep parser logic here (not inline in `llm.py`) so upstream merges on `llm.py` do not clobber recovery.

**Tests (fork, on branch):**

| Area | Tests |
|------|-------|
| Thought / split JSON / `llm` wiring | `tests/test_llm_parser.py` |
| Gemma `reasoning_effort` | `tests/test_llm_backends.py` |
| Incremental prune | `tests/test_build.py` → `test_build_merge_prune_sources_deleted_only_not_reextracted` |
| Stitch | `tests/test_stitch.py` |
| Manifest stamp | `tests/test_extract_manifest.py` on branch `fix/extract-manifest-source-path` only (included in #1384) |

---

### Proposed upstream PR queue

Submit as **separate** PRs to safishamsi/graphify — one at a time:

| PR | Title (suggested) | Files | Status |
|----|-------------------|-------|--------|
| **#1384 Manifest** | `fix(extract): stamp manifest when LLM source_file is relative` | `build.py`, `__main__.py`, `tests/test_extract_manifest.py` | **Submitted** — `fix/extract-manifest-source-path` |
| **#2 LLM JSON parser** | `fix(llm): robust JSON parse for Gemma thought blocks and split envelopes` | `llm_json_parser.py`, `llm.py`, `tests/test_llm_parser.py` | Pending |
| **#3 Gemma API** | `fix(gemini): skip reasoning_effort for gemma-* models` | `llm.py`, `tests/test_llm_backends.py` | Pending |
| **#4 Incremental prune** | `fix(extract): do not prune re-extracted sources in incremental merge` | `__main__.py`, `tests/test_build.py` | Pending |

**Not upstream (GnttProject / knowhow):** clustered extract default, `GraphCounts` `links` support, `graphify_incremental_ready()` gate, processor logging, `GRAPHIFY_EXTRACTION_SUFFIX` content — see MVP6 `ingest/knowhow/` and `MVP6-knowledge-mgmt/ARCHITECTURE.md` §11.3.

---

### C. GnttProject integration — **outside** the graphify git repo

These live in `GnttProject/` and survive upstream merges automatically:

| Path | Purpose |
|------|---------|
| `graphify/env.sh` | Venv, `.tokens.sh`, `GOOGLE_BYOK` → `GOOGLE_API_KEY`, OpenRouter → `OPENAI_*`, default `gemma-4-31b-it` |
| `graphify/.tokens.sh` | Secrets only (not committed) |
| `graphify/graphify.env` | Optional local overrides (if present) |
| `graphify/run-extract.sh` | Production extract wrapper |
| `graphify-test/smoke-extraction-env.sh` | **`GRAPHIFY_EXTRACTION_SUFFIX`** — DOCUMENT-ONLY MODE for markdown corpora |
| `graphify-test/run-smoke-gemma.sh` | Gemma cloud smoke — clustered default |
| `graphify-test/run-smoke-gemma-detail-compare.sh` | Cluster vs `--no-cluster` / `--mode deep` / token-budget variants; PMBOK8 corpus |
| `graphify-test/analyze-traceability.py` | Corpus ↔ graph attribution; accepts clustered `links` or flat `edges` |
| `graphify-test/rebuild-graphify.sh` | `pip install -e` fork |

---

## Sync workflow (upstream releases)

Run from `BoT-assistant-shared/graphify`:

```bash
git fetch upstream
git checkout feat/incremental-stitch-file-slice

# Option 1 — merge (preserves history, one merge commit)
git merge upstream/v8

# Option 2 — rebase (linear history; only if branch not shared / you force-push origin)
# git rebase upstream/v8
```

After merge:

1. **Resolve conflicts** using the table below — never drop `stitch.py` or incremental guards without re-applying.
2. **Re-apply section B** if merge overwrote `_extraction_system`, `_response_is_hollow`, `_call_openai_compat` reasoning guard, or dropped `llm_json_parser.py`.
3. **Run tests:** `pytest tests/test_stitch.py tests/test_build.py tests/test_chunking.py tests/test_llm_parser.py tests/test_llm_backends.py -q`
4. **Reinstall:** `graphify-test/rebuild-graphify.sh`
5. **Smoke:** `graphify-test/run-smoke-gemma.sh` or `run-smoke-gemma-detail-compare.sh` + `analyze-traceability.py`

### Conflict cheat sheet

| File | Keep from |
|------|-----------|
| `file_slice.py`, `tests/test_file_slice.py`, `tests/test_chunking.py` | **theirs** (upstream) — always |
| `stitch.py`, `tests/test_stitch.py` | **ours** (fork) unless upstream adds equivalent |
| `llm_json_parser.py`, `tests/test_llm_parser.py` | **ours** (fork) |
| `llm.py` | **theirs** (upstream `BACKENDS` / OpenAI config) + re-apply: suffix, hollow guard, Gemma `reasoning_effort`, single `llm_json_parser` import |
| `build.py` path helpers | **ours** — `source_path_aliases`, `path_covered_by_extraction` (manifest PR #1384) |
| `__main__.py` `_manifest_files`, `_incremental_prune` | **ours** + integrate upstream CLI flags |
| `__main__.py`, `build.py` incremental safety | **ours** where not yet upstream (#1370) |
| `skill*.md`, skillgen | usually **theirs**, re-run skillgen if needed |

### Optional: maintenance branch per upstream release

```bash
git checkout -b maintain/v8-0.8.43 upstream/v8
git merge feat/incremental-stitch-file-slice
# fix conflicts, tag: const011-0.8.43-fork
git push origin maintain/v8-0.8.43
```

Keeps `feat/incremental-stitch-file-slice` as the PR branch and `maintain/v8-*` as reproducible integration points.

---

## What we are **not** carrying in the fork

- `analysis-corpus/` — local scratch (untracked)
- Parallel **file slicing** implementation — upstream #1369 only
- `graphify/apply-openrouter-patch.sh` — obsolete; use `graphify/env.sh` instead
- Fenced-code **preprocessing** — rejected; doc behaviour is prompt-only via `GRAPHIFY_EXTRACTION_SUFFIX`

---

## PR status

[#1326](https://github.com/safishamsi/graphify/pull/1326) — closed; original monolithic PR split as follows:

| Part | Branch | Upstream PR | Status |
|------|--------|-------------|--------|
| 1 — file slice | `feat/file-slice` | [#1369](https://github.com/safishamsi/graphify/pull/1369) | **Merged upstream** @ 0.8.43 |
| 2 — incremental safety | `feat/incremental-safety` | [#1370](https://github.com/safishamsi/graphify/pull/1370) | Pending — check overlap after each sync |
| 3 — cross-file stitch | `feat/cross-file-stitch` | [#1371](https://github.com/safishamsi/graphify/pull/1371) | Pending (stacked on #1370) |

**Additional fork PRs (post-#1326 split):**

| PR | Status |
|----|--------|
| [#1384](https://github.com/safishamsi/graphify/pull/1384) manifest stamp | Submitted |
| #2 LLM JSON parser | Pending |
| #3 Gemma `reasoning_effort` | Pending |
| #4 Incremental prune | Pending |

Merge order for #1326 remainder: **#1370** → **#1371**. Fork PRs #2–#4 are independent of that stack.

---

## Changelog (fork-only, manual)

| Date | Change |
|------|--------|
| 2026-06-15 | PR: `stitch`, incremental extract safety (`e7f6a8e`) |
| 2026-06-16 | Merged upstream `v8` @ 0.8.40 into PR branch |
| 2026-06-16 | `GRAPHIFY_EXTRACTION_SUFFIX` + intentional-empty hollow guard (`llm.py`) |
| 2026-06-16 | `llm_json_parser.py` — split JSON heal/merge for Gemma |
| 2026-06-16 | Smoke: `gemma4:4E`, 16k ctx, DOCUMENT-ONLY suffix; 41-node corpus graph |
| 2026-06-18 | Split #1326 → upstream PRs #1369 / #1370 / #1371 |
| 2026-06-18 | Knowhow: clustered extract; `links`/`edges` graph counts; incremental gate matches graphify |
| 2026-06-18 | Fork: manifest stamp via `path_covered_by_extraction` — upstream **#1384** |
| 2026-06-18 | Fork: `llm_json_parser` + remove shadow `_parse_llm_json` in `llm.py` |
| 2026-06-19 | Merged `upstream/v8` @ **0.8.43** — adopt upstream #1369 slicing; align slice tests with upstream; fork patches retained |
| 2026-06-19 | `FORK_MAINTENANCE.md` post-merge refresh |

Update this table when committing fork patches or completing an upstream merge.
