# Change Review — 2026-11-24

## Summary of changes

Changes since commit `8e38a6f`:

- **`.claude/settings.json` (modified).** `enabledPlugins` is unchanged. A new `hooks.Stop` command hook (timeout 600 s) was added. When `IN_REVIEW_HOOK` is unset and `git status --porcelain` is non-empty, it runs a headless `claude -p "Use the change-reviewer subagent ..." --allowedTools "Read Grep Glob Bash Write Agent"` with `IN_REVIEW_HOOK=1`.
- **`planning/change-review.md` (untracked).** This is the output of an earlier run of this same review. This run replaces it.

What I checked:
- The JSON is well-formed (20 lines).
- The command uses no permission-bypass flags.
- The `IN_REVIEW_HOOK` guard stops recursion within a single stop. The child session's Stop hook inherits the variable, and the subagent fires `SubagentStop`, not `Stop`.
- `planning/change-review.md` is not gitignored (`git check-ignore` returns 1). There is no `.claude/settings.local.json`.
- `.claude/agents/change-reviewer.md:4` grants `tools: Read, Grep, Glob, Bash, Write`.

There are no conflicts with `planning/PLAN.md`. The change is tooling only and does not touch the product spec. It does not address any open item in §13.

## Findings

### High

**H1. The review keeps re-triggering itself.** `.claude/settings.json:13`
Every run writes `planning/change-review.md`. That file is untracked and not ignored, so after the first run `git status --porcelain` is never empty again. Every later Stop of any session starts a new review of up to 10 minutes. That includes turns that only answered a question, and the stop right after a commit. Each run rewrites the file, so the loop never ends. This run was itself triggered because the earlier review file was present. Committing the file would not help: the next rewrite would make it a modified tracked file.
Fix: add `planning/change-review.md` to `.gitignore`, or exclude it in the check:
`[ -z "$(git status --porcelain -- . ':(exclude)planning/change-review.md')" ]`.
Better still, skip the run if nothing changed since the last review. For example, hash `git diff HEAD` plus the list of untracked files into `.git/last-review-hash`, and compare before running.

**H2. Unrestricted `Bash` and `Write` are pre-approved in a headless session that reads untrusted content.** `.claude/settings.json:13`, `.claude/agents/change-reviewer.md:4`
`--allowedTools "... Bash Write ..."` approves any shell command and any file write without asking. The reviewer reads diffs and untracked files, which may come from other agents or from downloads. That opens the door to prompt injection. "Never write to any other file" is only an instruction in the agent prompt, and nothing enforces it.
Fix: scope the rules, for example:
`--allowedTools "Read Grep Glob Agent Bash(git status:*) Bash(git diff:*) Bash(git ls-files:*) Edit(/planning/change-review.md)"`
Edit rules also govern `Write`. Narrow the agent's `tools:` to match.

### Medium

**M1. The main session blocks for up to 10 minutes at every Stop.** `.claude/settings.json:14`
Stop hooks run synchronously. A large diff can exceed 600 s. The process is then killed and leaves the review file stale or half-written, with no signal to the user. With exit code 0, the hook's stdout is not shown to the main agent.
Fix: run it detached in the background:
`(IN_REVIEW_HOOK=1 nohup claude -p ... >/dev/null 2>&1 &)`.
Alternatively, make it a slash command you trigger by hand. If it stays synchronous, bound it with `--max-turns`.

**M2. The hook is committed for the whole project.** `.claude/settings.json:7-19`
The hook is in the shared `settings.json`. Every clone and every orchestrated agent session (PLAN.md §1) inherits it, so each one starts a paid review at every stop. Several can run in parallel and race on the same output file.
Fix: move the hook to `.claude/settings.local.json`, or make it opt-in by adding `[ -n "$AUTO_REVIEW" ] || exit 0` at the start.

**M3. The command silently depends on a POSIX shell.** `.claude/settings.json:13`
`[ ]`, `$(...)` and `VAR=1 cmd` only work because Claude Code on Windows runs hooks through Git Bash. On a setup without Git Bash, every Stop fails with a syntax error.
Fix: move the logic to `.claude/hooks/review.sh`, call it with `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/review.sh"`, and document that Git Bash is required.

### Low

**L1. The git check depends on the working directory.** `.claude/settings.json:13`
If the session has `cd`'d into a subdirectory or outside the repo, `git status` checks the wrong tree or prints `fatal:` to stderr.
Fix: use `git -C "$CLAUDE_PROJECT_DIR" status --porcelain 2>/dev/null`, and `cd "$CLAUDE_PROJECT_DIR"` before running `claude`.

**L2. The hook does not check `stop_hook_active`.** `.claude/settings.json:13`
This is harmless today because the hook never exits with code 2. If it is later changed to feed findings back through exit 2, the env guard alone will not prevent a loop in the main session.
Fix: also read `stop_hook_active` from the hook's stdin JSON and skip the run when it is true.

**L3. The hook reaches the subagent indirectly.** `.claude/settings.json:13`
The child session has to decide on its own to use the `Agent` tool, which adds an extra model layer.
Fix: call the reviewer directly with `claude -p --agent change-reviewer "..."`. This is more deterministic and cheaper.

**L4. Line endings.** `.claude/settings.json`
Git warns that LF will be replaced by CRLF.
Fix: add `*.json text eol=lf` to `.gitattributes`.
