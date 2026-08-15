# tools/dev-docs/GITHUB.md

Manual command reference. For the assistant-driven workflow see CHANGEIT.md,
FINISHIT.md, and POSTMERGE.md — this doc is the same shape, written out
by hand.

# --------------------------------------------------
# 0. one-time per clone: install git hooks
# --------------------------------------------------
tools/git-hooks/install.sh

# --------------------------------------------------
# 1. create issue + branch
# --------------------------------------------------
BRANCH="feat/12-REG-add-server-remove-command"
ISSUE_TITLE="Add server remove command"
ISSUE_BODY="Track adding a remove subcommand to the REG registry CLI."

ISSUE_URL=$(gh issue create \
  --title "$ISSUE_TITLE" \
  --body "$ISSUE_BODY")

ISSUE_NUMBER=$(basename "$ISSUE_URL")

git checkout main
git pull origin main
git checkout -b "$BRANCH"

# --------------------------------------------------
# 2. develop + commit
# --------------------------------------------------
git add .
git status
pytest || exit 1

git commit -m "feat(REG): add server remove command"

# commit subject format (enforced by tools/git-hooks/commit-msg):
# <type>(<EPIC>): <shortDescription>
# type: feat|fix|docs|test|refactor|perf|build|chore
# EPIC: see config/git/epics.txt / docs/epics/README.md

# --------------------------------------------------
# 3. push + create PR
# --------------------------------------------------
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

gh pr status
gh pr view

# --------------------------------------------------
# 4. validate PR
# --------------------------------------------------
gh pr checks
pytest

# optional manual checks
python -m minecraftmgr about
python -m minecraftmgr server list

# --------------------------------------------------
# 5. merge PR
# --------------------------------------------------
gh pr merge --merge --delete-branch

# --------------------------------------------------
# 6. post-merge cleanup (see POSTMERGE.md)
# --------------------------------------------------
git checkout main
git pull origin main
git branch -d "$BRANCH"
git fetch --prune

Author: Mike Mattinson
Updated: Aug/15/2026
