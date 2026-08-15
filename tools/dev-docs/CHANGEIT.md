# tools/dev-docs/CHANGEIT.md

1. **Purpose**
   <pre lang="markdown">
   ChangeIt is the standardized implementation workflow for:
   - bug fixes
   - enhancements
   - refactors
   - small feature additions

   When the user says:
   "changeit"

   the assistant should:
   - analyze the requested change
   - infer implementation scope and epic
   - generate git/github workflow commands
   - generate branch naming
   - generate issue/PR templates
   - follow project commit conventions
   </pre>

1. **Assistant Responsibilities**
   <pre lang="markdown">
   The assistant should:

   - Review current git status
   - Infer likely epic and scope (see docs/epics/README.md)
   - Suggest branch names
   - Suggest issue titles
   - Generate issue bodies
   - Generate commit messages
   - Generate PR templates
   - Generate git workflow commands
   - Prefer pytest before commit
   - Avoid runtime/generated files unless intentional
   </pre>

1. **Command Output Rules**
   <pre lang="markdown">
   When generating terminal commands:

   - ALWAYS use plain fenced markdown code blocks
   - Prefer ```bash fenced blocks
   - NEVER use writing blocks for terminal commands
   - NEVER interleave commentary inside command blocks
   - Output must be directly copy/paste safe for Git Bash
   </pre>

1. **Commit Subject Format**
   <pre lang="markdown">
   All commit subjects (first line) MUST follow:

   <type>(<epicAbbrev>): <shortDescription>

   type:             feat | fix | docs | test | refactor | perf | build | chore
   epicAbbrev:       CLI | REG | BAK | DEP | TST | DOC (config/git/epics.txt
                      is the source of truth; docs/epics/README.md maps each code
                      to its epic)
   shortDescription: imperative mood, verb + noun

   Examples:
   - feat(REG): add server remove command
   - fix(BAK): correct sha256 file suffix
   - docs(DEP): document Velocity forced-hosts setup

   Merge commits and "Release vX.Y.Z" commits are exempt.

   Enforced locally by tools/git-hooks/commit-msg (run tools/git-hooks/install.sh
   once per clone -- .git/hooks/ isn't tracked by git). Branch names are enforced
   the same way by tools/git-hooks/pre-push.
   </pre>

1. **Canonical Workflow Template**
   <pre lang="bash">
   BRANCH=""
   ISSUE_TITLE=""
   ISSUE_BODY=""
   COMMIT_MESSAGE=""

   ISSUE_URL=$(gh issue create \
     --title "$ISSUE_TITLE" \
     --body "$ISSUE_BODY")

   ISSUE_NUMBER=$(basename "$ISSUE_URL")

   git checkout main
   git pull origin main
   git checkout -b "$BRANCH"

   git add .

   git status
   pytest || exit 1

   git commit -m "$COMMIT_MESSAGE"

   git push -u origin "$BRANCH"

   gh pr create \
     --base main \
     --head "$BRANCH" \
     --title "$ISSUE_TITLE" \
     --body "
   ## Summary
   - ...

   Closes #$ISSUE_NUMBER
   "
   </pre>

1. **Post Merge Cleanup**
   <pre lang="bash">
   After the PR is merged, use POSTMERGE.md.
   </pre>

1. **Workflow Preferences**
   <pre lang="markdown">
   Prefer:
   - small incremental phases
   - PR-friendly changes
   - test-first validation
   - minimal-risk implementation steps

   Avoid:
   - large multi-feature commits
   - direct commits/pushes to main
   - mixing refactors with unrelated fixes
   - committing generated runtime files
   </pre>

<br>Author: Mike Mattinson/Chat
<br>Updated: Aug/15/2026
