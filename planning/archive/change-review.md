# Change review — 2026-11-24

*Scope: everything changed since commit `becaafe` (`git diff HEAD` plus untracked files). `planning/change-review.md` itself is excluded because it is this report.*

## Summary of changes

- **`.claude/settings.json` (modified).** The project-level `Stop` hook was removed. `"independent-reviewer@pepe-tools": true` was added to `enabledPlugins`.
- **`.claude-plugin/marketplace.json` (new).** Defines a local marketplace `pepe-tools` with one plugin, `independent-reviewer`, at `./independent-reviewer`.
- **`independent-reviewer/.claude-plugin/plugin.json` (new).** Plugin manifest.
- **`independent-reviewer/hooks/hooks.json` (new).** The `Stop` hook from `settings.json`, moved over unchanged.
- **`README.md` (modified).** The 3-line stub is now a full overview: features, stack table, quick start, env vars, project layout, docs and license links.
- **`planning/review.md` (deleted).** The detailed plan review (about 33 numbered findings tagged [B]/[W]/[N]) is gone.

Overall: the review hook moved from project settings into a repo-local plugin. That is a reasonable way to package it, but whether the hook still fires depends on the plugin loading, and the changes as written do not guarantee that (see H2, M1). Deleting `review.md` loses work that exists nowhere else.

---

## High

### H1. `planning/review.md` deleted; its findings exist nowhere else
- **Where:** `planning/review.md` (deleted). Compare with `planning/PLAN.md:460-484` (§13).
- **Problem:** `review.md` described itself as a *supplement* to PLAN §13 ("tych 10 punktów tu nie powtarzam"). It held about 33 separate findings, several marked **[B] (blocks agent start)**: single uvicorn worker / no `--reload`, event-loop blocking by sync `litellm.completion` and sync `sqlite3`, the price being available right after `add_ticker()`. It also covered SQLite WAL/`busy_timeout`/`DB_PATH`, price resets on restart, and seed prices for arbitrary tickers. A grep of `PLAN.md` for `workers`, `acompletion`, `WAL` and `DB_PATH` finds nothing, so none of these were moved into the spec. Once the file is gone, agents that use `planning/` as the shared contract cannot see these blocking decisions.
- **Fix:** Restore the file (`git checkout HEAD -- planning/review.md`) until each item is resolved into PLAN.md. Alternatively, merge the [B]/[W] items into PLAN §13 (or the relevant sections) in the same change that deletes the file.

### H2. `plugin.json` `author` is a string; the manifest schema expects an object
- **Where:** `independent-reviewer/.claude-plugin/plugin.json:5`
- **Problem:** `"author" : "FinAlly"`. The Claude Code plugin manifest defines `author` as an object (`{"name": ..., "email"?: ..., "url"?: ...}`), which is how `marketplace.json:14-16` already writes it. A manifest that fails validation can stop the plugin from loading. Because the `Stop` hook was removed from `settings.json`, that would quietly turn off the automatic change review. The author also differs from the marketplace entry ("FinAlly" vs "Pepe").
- **Fix:** `"author": { "name": "Pepe" }` (match the marketplace). Then confirm the plugin loads with `claude plugin validate .` or `/plugin` and check that the hook appears under `/hooks`.

## Medium

### M1. Marketplace `pepe-tools` is enabled but not registered in project settings
- **Where:** `.claude/settings.json:6`
- **Problem:** `enabledPlugins` refers to `independent-reviewer@pepe-tools`, but `settings.json` has no `extraKnownMarketplaces` entry for `pepe-tools`. The marketplace only resolves on a machine where someone ran `/plugin marketplace add ./` by hand, and that registration is stored in user-level state, not in the repo. Anyone else who clones the repo, including the agents or a CI run, gets an unknown-plugin warning and no review hook. Before this change the hook worked straight from the checked-in `settings.json`.
- **Fix:** Register the marketplace in the project settings, for example `"extraKnownMarketplaces": { "pepe-tools": { "source": { "source": "directory", "path": "." } } }`. Or note the one-time `/plugin marketplace add ./` + `/plugin install independent-reviewer@pepe-tools` step in README.

### M2. Plugin depends on a project-local subagent it does not ship
- **Where:** `independent-reviewer/hooks/hooks.json:8`; `.claude/agents/change-reviewer.md`
- **Problem:** The hook prompt says "Use the change-reviewer subagent", but that agent lives in `.claude/agents/`, not in the plugin (there is no `independent-reviewer/agents/`). The plugin is described as a reusable "independent review" tool, yet it fails in any other repo. Even here it only works because the project agent happens to exist. The hook also writes to `planning/change-review.md`, which is specific to this project.
- **Fix:** Move (or copy) `change-reviewer.md` into `independent-reviewer/agents/` and refer to it as the plugin's agent. Or state in the plugin description that it requires a project-level `change-reviewer` agent.

### M3. README Quick Start points to files that do not exist yet
- **Where:** `README.md:28-32`
- **Problem:** `cp .env.example .env` and `./scripts/start_mac.sh` / `.\scripts\start_windows.ps1` both fail right now: neither `.env.example` nor `scripts/` exists. PLAN §4 does plan these files, but the README reads as if the project already works and gives no hint that it is a specification in progress.
- **Fix:** Add a short status note ("Work in progress — see planning/PLAN.md; scripts and `.env.example` are not yet committed"), or create a placeholder `.env.example` with the three variables from PLAN §5.

## Low

### L1. README settles points that PLAN §13 still lists as open
- **Where:** `README.md:20` ("created on startup"), `README.md:38` (`OPENROUTER_API_KEY` "Yes (for chat)", which implies the app starts without it).
- **Problem:** PLAN §4 says lazy init on first request, §7 says "on startup (or first request)", and §13 #8c only *recommends* startup. Likewise, starting without a key is only a recommendation in §13 #6. The README quietly picks one answer before the spec does.
- **Fix:** Either write the decisions into PLAN.md (§7/§5) and remove the corresponding §13 items, or use neutral wording in README ("created automatically").

### L2. Redundant and placeholder metadata in the plugin files
- **Where:** `.claude-plugin/marketplace.json:6,13`; `independent-reviewer/.claude-plugin/plugin.json:4`
- **Problem:** `version` and `description` appear in both the marketplace entry and `plugin.json`, so they can drift apart (`plugin.json` takes precedence). `owner.email` is the placeholder `pepe@example.com`. `plugin.json` declares `"license": "MIT"`; check that this matches the repo `LICENSE`.
- **Fix:** Keep `version` in `plugin.json` only. Remove the placeholder email or replace it with a real one. Make the license match `LICENSE`.

### L3. Formatting
- **Where:** `.claude-plugin/marketplace.json:3-4,14-16` (Allman-style brace, trailing spaces, 4-space indent); `independent-reviewer/.claude-plugin/plugin.json:2-6` (no indentation, spaces before colons). Neither file ends with a newline.
- **Fix:** Reformat both with 2-space indentation like `settings.json` and `hooks.json`, and add a final newline.

### L4. Hook command is POSIX-only
- **Where:** `independent-reviewer/hooks/hooks.json:8`
- **Problem:** `[ -n ... ] || ... || IN_REVIEW_HOOK=1 claude ...` needs a POSIX shell. It works with Git Bash on Windows, but it is fragile if hooks run through another shell. This behaviour carried over from the old hook and is not new.
- **Fix:** No action is required. Optionally, put the command in a `scripts/` file inside the plugin, referenced through `${CLAUDE_PLUGIN_ROOT}`.
