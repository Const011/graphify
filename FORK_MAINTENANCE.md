# Graphify fork maintenance (Const011 / GnttProject)

Track **our** changes vs [upstream graphify](https://github.com/safishamsi/graphify) (`upstream/v8`) so we can merge new releases without losing production behaviour.

| Remote | URL | Role |
|--------|-----|------|
| `origin` | `git@github.com:Const011/graphify.git` | Our fork |
| `upstream` | `https://github.com/safishamsi/graphify.git` | safishamsi master line (`v8` branch) |

**Active branch:** split PRs to upstream — see [PR status](#pr-status). Archive: `feat/incremental-stitch-file-slice`, `fork/archive/monolithic-pr-1326`.

**Install in GnttProject:** `pip install -e BoT-assistant-shared/graphify` after `source graphify/env.sh` (see `graphify-test/rebuild-graphify.sh`). **Restart** pi-web / knowhow after reinstall so the processor picks up `llm.py` changes.

---

## Production choices (validated 2026-06)

| Setting | Value |
|---------|--------|
| Local graph build (Ollama) | `gemma4:4E` |
| Context | `OLLAMA_NUM_CTX=16384`, margin 2048 → token-budget ~7168 |
| Doc corpus prompt | `graphify-test/smoke-extraction-env.sh` → `GRAPHIFY_EXTRACTION_SUFFIX` |
| Cloud fallback | Google `gemma-4-31b-it` via `graphify/env.sh` / `pi-web/start.sh` → `GRAPHIFY_GEMINI_MODEL` |
| Smoke corpus | `graphify-test/corpus-smoke/` (8 markdown files) |

Reference run: `ollama-gemma4-4E-smoke` — 41 nodes, 32 edges, 100% traceable, 8/8 files.

### Knowhow processor (MVP6)

The central knowhow processor (`MVP6-knowledge-mgmt/ingest/knowhow/processor.py`) **always** invokes:

```bash
python -m graphify extract {projectDir} --out {projectDir}/.pi/knowhow \
  --backend gemini --model gemma-4-31b-it \
  --max-concurrency 4 --api-timeout 900
```

Init (no usable graph): processor **removes** `.pi/knowhow/graphify-out/` when `graph.json` is missing or has 0 nodes. Incremental: `graph.json` (≥1 node) **and** `manifest.json` file present — graphify then prints `incremental scan of …` (manifest may be `{}` until fork manifest fix is deployed).

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

**Validated smoke (2026-06-18):** `graphify-test/run-smoke-gemma.sh` — clustered extract, no `--no-cluster`; 24 nodes, 16 links, 8 communities, 8/8 corpus files.

### Incidents fixed (2026-06-18, knowhow + fork)

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Extract succeeds but knowhow reports “graph.json missing or empty” | Clustered `graph.json` uses NetworkX node-link format (`links`, not `edges`); `GraphCounts.from_graph_json` required `edges` | Knowhow `graphify_run_log.py` — count `edges` or `links` |
| Second promoted doc wipes graph, full re-init | After first extract, `manifest.json` was `{}`; knowhow required non-empty manifest → **init + reset** | Fork `__main__.py` manifest stamp + knowhow `graphify_incremental_ready()` aligned with graphify gate |
| Incremental re-extract, tokens spent, graph delta +0 | `_incremental_prune` included re-extracted paths; `build_merge` `prune_sources` deleted fresh nodes | Fork `__main__.py` — `prune_sources=deleted_files` only |

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

**Upstream:** same bug on `v8` @ 0.8.41 — candidate for a small follow-up PR to Safi (not in #1369–#1371 unless cherry-picked).

---

## Change inventory

### A. PR #1326 — committed on `feat/incremental-stitch-file-slice`

Core fork features (merge carefully; upstream may add overlapping fixes):

| Area | Files | What |
|------|-------|------|
| **Intra-file slicing** | `graphify/file_slice.py`, `graphify/llm.py`, `tests/test_file_slice.py` | **Upstream #1369 (v8 @ 0.8.43):** split oversized `.md`/`.txt`/`.rst` at heading/paragraph boundaries by `_FILE_CHAR_CAP` (20k chars) **before** packing — full file coverage, no silent tail drop. Adaptive retry bisects `FileSlice` units on truncation. |
| **Incremental safety** | `graphify/__main__.py`, `graphify/build.py`, `tests/test_build.py`, `tests/test_extract.py` | Abort incremental extract on failed/empty re-extract; safe prune; no silent graph shrink |
| **Cross-file stitch** | `graphify/stitch.py`, `tests/test_stitch.py` | Post-merge `references` edges from changed docs → existing graph (backticks + paths); `new_node_ids` for wrong LLM `source_file` |
| **LLM wiring** | `graphify/llm.py` | `_read_files(units)` — slices use `read_slice_text`; whole files still capped at `_FILE_CHAR_CAP`; `extract_corpus_parallel` calls `expand_oversized_files(files, _FILE_CHAR_CAP)` first (#1369) |
| **Docs / version** | `CHANGELOG.md`, `README.md`, `pyproject.toml` | PR description material |

**Note:** Early PR commits added OpenRouter/`GOOGLE_BYOK` in `llm.py`. Upstream **v8** later shipped `#1273` (custom `OPENAI_BASE_URL` / env keys). On merge, prefer **upstream** OpenAI config; keep slice/stitch/incremental logic from our branch.

Other commits on the branch may include upstream merges (0.8.40, query skill, Java/Swift AST) — treat as **upstream**, not fork-specific.

---

### B. Local fork patches — not yet committed on `feat/incremental-stitch-file-slice`

**Status (2026-06):** modified, **not committed**.

| Change | File(s) | Purpose | Upstream candidate? |
|--------|---------|---------|---------------------|
| **`GRAPHIFY_EXTRACTION_SUFFIX`** | `graphify/llm.py` → `_extraction_system()` | Append env-driven doc-mode rules without editing `_EXTRACTION_SYSTEM` | Yes — small, env-only |
| **Accept intentional empty JSON** | `graphify/llm.py` → `_response_is_hollow()` | `return ... and finish_reason != "stop"` — model may return `{"nodes":[],"edges":[]}` when slice is code-only; do **not** bisect/retry | Yes — bugfix for doc extraction |
| **Split JSON recovery** | `graphify/llm_json_parser.py` | Heal Gemma split envelopes (`{"nodes":[...]\n{"edges":[...]}`), merge multiple top-level JSON objects | Yes — parser robustness (PR **#2** below) |
| **Skip `reasoning_effort` for Gemma** | `graphify/llm.py` → `_call_openai_compat`, `_supports_reasoning_effort` | Gemma via `--backend gemini` rejects OpenAI-style thinking level | Yes — bugfix (PR **#3** or fold into Gemma bundle) |
| **Strip Gemma `<thought>` preamble** | `graphify/llm_json_parser.py` → `strip_model_thought_blocks()` | Remove `<thought>…</thought>` / unclosed preamble before JSON parse | Yes — PR **#2** |
| **Wire parser in `llm.py`** | `graphify/llm.py` | **Delete** duplicate `_parse_llm_json` (~80 lines) so `from graphify.llm_json_parser import parse_llm_json as _parse_llm_json` is used at runtime | Yes — PR **#2** (same PR as thought strip; shadowing made #2 ineffective until removed) |
| **Manifest path alias on extract** | `graphify/__main__.py` → `_manifest_files` | Use `path_covered_by_extraction(f, sem_result, target)` instead of `f in _sem_extracted` — detect paths are absolute, LLM `source_file` is relative → upstream wrote `{}` manifest | Yes — **separate PR #1** (manifest-only) |
| **Incremental prune_sources** | `graphify/__main__.py` → `_incremental_prune` | Pass **deleted files only** to `build_merge(prune_sources=…)`; re-extracted paths were pruned after merge → +0 nodes | Yes — **PR #4** |
| **Debug prints** | `graphify/llm.py` → `_response_is_hollow()` | `[RAW CONTENT IS NULL]`, `[PARSED IS EMPTY]` | **Remove** before commit |

**New module:** `graphify/llm_json_parser.py` — keep parser logic here (not inline in `llm.py`) so upstream merges on `llm.py` do not clobber recovery.

**Tests (fork):**

| Area | Tests |
|------|-------|
| Thought / split JSON / `llm` wiring | `tests/test_llm_parser.py` (incl. `test_llm_module_delegates_to_llm_json_parser`) |
| Gemma `reasoning_effort` | `tests/test_llm_backends.py` |
| Manifest stamp | **TODO** — add `tests/test_extract_manifest.py` before upstream PR **#1** (repro: absolute detect path + relative `source_file` → non-empty manifest) |

---

### Proposed upstream PR split (2026-06-18)

Submit as **separate** PRs to safishamsi/graphify — easier review, independent merge:

| PR | Title (suggested) | Files | Notes |
|----|-------------------|-------|-------|
| **#1 Manifest** | `fix(extract): stamp manifest when LLM source_file is relative` | `graphify/__main__.py`, new test | Bug: `_manifest_files` filtered with `f in _sem_extracted` (string equality). `detect()` yields `/abs/path/doc.md`; nodes carry `doc.md`. Manifest stayed `{}` → broken incremental. **Needs dedicated test before submit.** |
| **#2 LLM JSON parser** | `fix(llm): robust JSON parse for Gemma thought blocks and split envelopes` | `graphify/llm_json_parser.py`, `graphify/llm.py` (import only, remove duplicate), `tests/test_llm_parser.py` | Includes `<thought>` strip, split-envelope heal, and **must** delete shadow `_parse_llm_json` in `llm.py`. |
| **#3 Gemma API** | `fix(gemini): skip reasoning_effort for gemma-* models` | `graphify/llm.py`, `tests/test_llm_backends.py` | Small; can merge independently or with #2. |
| **#4 Incremental prune** | `fix(extract): do not prune re-extracted sources in incremental merge` | `graphify/__main__.py`, `tests/test_build.py` | Bug: changed paths in `prune_sources` removed merged nodes. Test: `test_build_merge_prune_sources_deleted_only_not_reextracted`. |

**Not upstream (GnttProject / knowhow):** clustered extract default, `GraphCounts` `links` support, `graphify_incremental_ready()` gate, processor logging — see MVP6 `ingest/knowhow/` and `MVP6-knowledge-mgmt/ARCHITECTURE.md` §11.3.

Suggested commit messages (fork, before splitting PRs):

```
fix(extract): stamp manifest using path_covered_by_extraction

detect() records absolute paths; LLM source_file is relative. Matching with
set membership left semantic files out of _manifest_files → empty manifest.
```

```
fix(llm): use llm_json_parser for all extract paths; strip Gemma <thought>

- Add strip_model_thought_blocks() for <thought> preamble.
- Remove duplicate _parse_llm_json in llm.py that shadowed the import.
```

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
| `graphify-test/run-smoke-gemma.sh` | Gemma cloud smoke — **clustered** (no `--no-cluster`); validates fork on 8-file corpus |
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

1. **Resolve conflicts** using the table above — never drop `file_slice.py`, `stitch.py`, incremental guards without re-applying.
2. **Re-apply section B** if merge overwrote `_extraction_system`, `_response_is_hollow`, `_call_openai_compat` reasoning guard, or dropped `llm_json_parser.py`.
3. **Run tests:** `pytest tests/test_file_slice.py tests/test_stitch.py tests/test_build.py tests/test_chunking.py tests/test_llm_parser.py tests/test_llm_backends.py -q`
4. **Reinstall:** `graphify-test/rebuild-graphify.sh`
5. **Smoke:** `graphify-test/run-smoke-ollama.sh` + `analyze-traceability.py`

### Conflict cheat sheet

| File | Keep from |
|------|-----------|
| `file_slice.py`, `stitch.py` | **theirs** (upstream #1369 slicing merged 2026-06-19) unless fork adds stitch-only deltas |
| `llm.py` OpenRouter / `BACKENDS` | **theirs** (upstream v8) + re-apply suffix + hollow fix + Gemma `reasoning_effort` guard + **single** `from graphify.llm_json_parser import parse_llm_json as _parse_llm_json` (no local duplicate) |
| `llm_json_parser.py` | **ours** (fork) — new file; safe unless upstream adds equivalent |
| `__main__.py` `_manifest_files` | **ours** — `path_covered_by_extraction` manifest stamp (PR #1) |
| `__main__.py`, `build.py` incremental | **ours** + integrate upstream CLI flags |
| `skill*.md`, skillgen | usually **theirs**, re-run skillgen if needed |

### Optional: maintenance branch per upstream release

```bash
git checkout -b maintain/v8-0.8.41 upstream/v8   # after tag
git merge feat/incremental-stitch-file-slice      # bring fork commits
# fix conflicts, tag: const011-0.8.41-fork
git push origin maintain/v8-0.8.41
```

Keeps `feat/incremental-stitch-file-slice` as the PR branch and `maintain/v8-*` as reproducible integration points.

---

## What we are **not** carrying in the fork

- `analysis-corpus/` — local scratch (untracked)
- Debug `print()` in `llm.py` — remove before commit
- `graphify/apply-openrouter-patch.sh` — obsolete; use `graphify/env.sh` instead
- Fenced-code **preprocessing** — rejected; doc behaviour is prompt-only via `GRAPHIFY_EXTRACTION_SUFFIX`

---

## PR status

[#1326](https://github.com/safishamsi/graphify/pull/1326) — closed; work split into three upstream PRs:

| Part | Branch | Upstream PR |
|------|--------|-------------|
| 1 — file slice | `feat/file-slice` | [#1369](https://github.com/safishamsi/graphify/pull/1369) |
| 2 — incremental safety | `feat/incremental-safety` | [#1370](https://github.com/safishamsi/graphify/pull/1370) |
| 3 — cross-file stitch | `feat/cross-file-stitch` (stacked on #1370) | [#1371](https://github.com/safishamsi/graphify/pull/1371) |

Merge order: **#1369** (independent) → **#1370** → **#1371**.

Quick diff after each sync:

```bash
git log --oneline upstream/v8..HEAD
git diff upstream/v8...HEAD --stat
```

---

## Changelog (fork-only, manual)

| Date | Change |
|------|--------|
| 2026-06-15 | PR: `file_slice`, `stitch`, incremental extract safety (`e7f6a8e`) |
| 2026-06-16 | Merged upstream `v8` @ 0.8.40 into PR branch |
| 2026-06-16 | `GRAPHIFY_EXTRACTION_SUFFIX` + hollow `finish_reason=stop` (local `llm.py`) |
| 2026-06-16 | `llm_json_parser.py` — split JSON heal/merge for Ollama Gemma |
| 2026-06-16 | Smoke: `gemma4:4E`, 16k ctx, DOCUMENT-ONLY suffix; 41-node corpus graph |
| 2026-06-18 | Split #1326 → upstream PRs #1369 / #1370 / #1371 |
| 2026-06-18 | Knowhow: clustered extract; `links`/`edges` graph counts; incremental gate matches graphify |
| 2026-06-18 | Fork: manifest stamp via `path_covered_by_extraction` (`__main__.py`) — **upstream PR #1 candidate** |
| 2026-06-18 | Fork: `llm_json_parser` `<thought>` strip + remove shadow `_parse_llm_json` in `llm.py` — **upstream PR #2 candidate** |
| 2026-06-19 | Merged `upstream/v8` @ 0.8.43 — upstream #1369 file slicing replaces fork token-estimate/`char_cap` slice path; fork patches retained in `llm.py` (`llm_json_parser`, `GRAPHIFY_EXTRACTION_SUFFIX`, Gemma `reasoning_effort`, intentional-empty hollow guard) |

Update this table when committing fork patches or completing an upstream merge.
