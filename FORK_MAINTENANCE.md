# Graphify fork maintenance (Const011 / GnttProject)

Track **our** changes vs [upstream graphify](https://github.com/safishamsi/graphify) (`upstream/v8`) so we can merge new releases without losing production behaviour.

| Remote | URL | Role |
|--------|-----|------|
| `origin` | `git@github.com:Const011/graphify.git` | Our fork |
| `upstream` | `https://github.com/safishamsi/graphify.git` | safishamsi master line (`v8` branch) |

**Active branch:** `feat/incremental-stitch-file-slice` (PR [#1326](https://github.com/safishamsi/graphify/pull/1326), commit `e7f6a8e` + merges from upstream `v8`).

**Install in GnttProject:** `pip install -e BoT-assistant-shared/graphify` after `source graphify/env.sh` (see `graphify-test/rebuild-graphify.sh`).

---

## Production choices (validated 2026-06)

| Setting | Value |
|---------|--------|
| Local graph build (Ollama) | `gemma4:4E` |
| Context | `OLLAMA_NUM_CTX=16384`, margin 2048 → token-budget ~7168 |
| Doc corpus prompt | `graphify-test/smoke-extraction-env.sh` → `GRAPHIFY_EXTRACTION_SUFFIX` |
| Cloud fallback | Google `gemma-4-31b-it` via `graphify/env.sh` |
| Smoke corpus | `graphify-test/corpus-smoke/` (8 markdown files) |

Reference run: `ollama-gemma4-4E-smoke` — 41 nodes, 32 edges, 100% traceable, 8/8 files.

---

## Change inventory

### A. PR #1326 — committed on `feat/incremental-stitch-file-slice`

Core fork features (merge carefully; upstream may add overlapping fixes):

| Area | Files | What |
|------|-------|------|
| **Intra-file slicing** | `graphify/file_slice.py`, `graphify/llm.py`, `tests/test_file_slice.py` | Split large `.md`/`.txt`/`.rst` by headings; adaptive bisect on truncation; `SemanticUnit` / `FileSlice` |
| **Incremental safety** | `graphify/__main__.py`, `graphify/build.py`, `tests/test_build.py`, `tests/test_extract.py` | Abort incremental extract on failed/empty re-extract; safe prune; no silent graph shrink |
| **Cross-file stitch** | `graphify/stitch.py`, `tests/test_stitch.py` | Post-merge `references` edges from changed docs → existing graph (backticks + paths); `new_node_ids` for wrong LLM `source_file` |
| **LLM wiring** | `graphify/llm.py` | `_read_files(units)`, slice labels in prompt, `split_chunk_for_retry` from `file_slice` |
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
| **Split JSON recovery** | `graphify/llm_json_parser.py` | Heal Gemma split envelopes (`{"nodes":[...]\n{"edges":[...]}`), merge multiple top-level JSON objects; imported by `llm.py` as `_parse_llm_json` | Yes — parser robustness for local models |
| **Debug prints** | `graphify/llm.py` → `_response_is_hollow()` | `[RAW CONTENT IS NULL]`, `[PARSED IS EMPTY]` | **Remove** before commit |

**New module:** `graphify/llm_json_parser.py` — keep parser logic here (not inline in `llm.py`) so upstream merges on `llm.py` do not clobber recovery. Tests: `tests/test_llm_parser.py` imports `parse_llm_json` directly.

Suggested commit message:

```
fork: doc extraction suffix, hollow stop fix, split JSON parser

- Append GRAPHIFY_EXTRACTION_SUFFIX to extraction system prompt (env override).
- Do not treat finish_reason=stop + empty nodes/edges as hollow truncation.
- Add llm_json_parser.py: heal/merge split LLM JSON envelopes (Gemma/Ollama).
```

Add or extend tests in `tests/test_llm_parser.py` when committing.

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
| `graphify-test/run-smoke-*.sh` | Smoke scripts (Ollama default `gemma4:4E`, 16k ctx) |
| `graphify-test/analyze-traceability.py` | Corpus ↔ graph attribution checks |
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
2. **Re-apply section B** if merge overwrote `_extraction_system`, `_response_is_hollow`, or dropped `llm_json_parser.py`.
3. **Run tests:** `pytest tests/test_file_slice.py tests/test_stitch.py tests/test_build.py tests/test_chunking.py tests/test_llm_parser.py -q`
4. **Reinstall:** `graphify-test/rebuild-graphify.sh`
5. **Smoke:** `graphify-test/run-smoke-ollama.sh` + `analyze-traceability.py`

### Conflict cheat sheet

| File | Keep from |
|------|-----------|
| `file_slice.py`, `stitch.py` | **ours** (fork) unless upstream added equivalent |
| `llm.py` OpenRouter / `BACKENDS` | **theirs** (upstream v8) + re-apply suffix + hollow fix + `from graphify.llm_json_parser import parse_llm_json` |
| `llm_json_parser.py` | **ours** (fork) — new file; safe unless upstream adds equivalent |
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

[#1326](https://github.com/safishamsi/graphify/pull/1326) — intra-file slice, incremental safety, stitch. If closed unmerged, **keep the fork branch**; upstream may implement subsets later — use this doc + `git log upstream/v8..HEAD` to see what still differs.

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

Update this table when committing fork patches or completing an upstream merge.
