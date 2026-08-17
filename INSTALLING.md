# Installing and updating the MILLER subagent

MILLER ships as a real Claude Code subagent definition:
`.claude/agents/miller.md`. There is no plugin/marketplace mechanism for
this yet — the actual, documented Claude Code convention for a single
subagent file is simpler than that: **copy the file into your own
`.claude/agents/` directory.**

## Install

Pick one, depending on scope:

**Project-level** (recommended for a team — check it into your own repo so
everyone who clones it gets MILLER automatically):

```bash
mkdir -p .claude/agents
curl -o .claude/agents/miller.md \
  https://raw.githubusercontent.com/Agent-Of/miller/devline/.claude/agents/miller.md
```

**User-level** (applies to every project on your machine, not checked into
any repo):

```bash
mkdir -p ~/.claude/agents
curl -o ~/.claude/agents/miller.md \
  https://raw.githubusercontent.com/Agent-Of/miller/devline/.claude/agents/miller.md
```

If `.claude/agents/` did not already exist and this is the *first* file in
it, Claude Code needs one restart to discover it (confirmed directly,
2026-08-17 — a brand-new agents directory is not picked up by a live
filesystem watch, only at process start). Adding a *second* agent to an
already-populated directory does not require a restart. If you're not sure
which case you're in, restarting costs nothing and always works.

Verify it's live: ask Claude Code to investigate a session's own JSONL
transcript, or invoke it explicitly — "use the miller agent to...". If it
isn't found, check `.claude/agents/miller.md` exists at the path you
expect and that you're not mid-way through the first-file/restart case
above.

## Update

There is no auto-sync — updating means re-fetching and overwriting the
file, the same as install:

```bash
curl -o .claude/agents/miller.md \
  https://raw.githubusercontent.com/Agent-Of/miller/devline/.claude/agents/miller.md
```

(swap the path for the user-level location if that's where you installed
it). No restart is needed to pick up an *updated* file in an
already-existing agents directory — only a brand-new directory's first
file needs one.

## Which branch to track

- **`devline`** — active integration branch. Track this if you want fixes
  as they land, and are willing to hit the occasional rough edge — this is
  also where feedback from other teams testing MILLER against their own
  real sessions is most useful, since it's not yet been proven stable
  across multiple environments.
- **`main`** — promoted from `devline` once a set of changes has actually
  been proven out (not on a fixed schedule). Track this if you want
  fewer-but-more-vetted updates.

Both the underlying Python library (`slurper.py` et al., for anyone
building on it directly rather than only using the subagent) and the
subagent definition itself live in this same repo and move through the
same `devline` → `main` promotion — there is no separate versioning
between the two.

## If something doesn't work on your real data

The whole point of shipping this as something other teams can install is
real-environment testing — this was built and dogfooded against one
specific machine's real Claude Code sessions, and "does it hold up
somewhere else" is a genuinely open question, not a formality. If file
discovery misses a real session, or counts don't reconcile against your
own independent check, file an issue with the specifics (session size,
entrypoints involved, what you expected vs. got) — that's exactly the
signal this needs to actually mature.
