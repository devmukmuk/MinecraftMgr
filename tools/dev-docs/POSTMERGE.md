# tools/dev-docs/POSTMERGE.md

1. **Purpose**
   <pre lang="markdown">
   PostMerge is the standardized cleanup workflow after a pull request has
   been merged into main.

   When the user says:
   - "postmerge"
   - "post-merge"
   - "post merge commands"
   - "cleanup after merge"

   the assistant should:
   - assume the PR has already been merged
   - preserve the current branch name before switching to main
   - update local main
   - delete the merged local branch
   - delete the merged remote branch (if GitHub didn't already auto-delete it)
   - prune stale remote-tracking branches
   </pre>

1. **Expected Repository State**
   <pre lang="markdown">
   Expected:
   - pull request has already been merged
   - user is still on the merged feature/change branch
   - local working tree is clean or only contains intentional follow-up changes

   The assistant should:
   - capture the current branch before checkout
   - switch to main
   - pull the latest main
   - delete the previous local branch
   - delete the previous remote branch (skip if GitHub already deleted it)
   - prune stale remote references
   </pre>

1. **Critical Workflow Rules**
   <pre lang="markdown">
   NEVER during PostMerge workflow:
   - create a new branch
   - create a new issue
   - create a new pull request
   - commit files
   - push changes

   These commands belong to ChangeIt or FinishIt workflows.

   PostMerge assumes:
   - the PR is already merged
   - the feature/change branch is no longer needed locally
   - main should be refreshed from origin
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

1. **Canonical Workflow Template**
   <pre lang="bash">
   CURRENT_BRANCH=$(git branch --show-current)

   git checkout main
   git pull origin main

   git branch -d "$CURRENT_BRANCH"

   git push origin --delete "$CURRENT_BRANCH" || true

   git fetch --prune
   </pre>

1. **When Branch Delete Fails**
   <pre lang="markdown">
   If git branch -d fails because Git does not believe the branch is fully merged,
   the assistant should NOT automatically recommend force deletion.

   Instead, the assistant should recommend:

   - verify the PR was merged
   - verify main was pulled successfully
   - inspect the branch difference
   - only use git branch -D if the user confirms the branch is safely merged
   </pre>

1. **Branch Delete Troubleshooting**
   <pre lang="bash">
   git branch --merged main

   git log --oneline main.."$CURRENT_BRANCH"
   </pre>

1. **Force Delete Variant**
   <pre lang="markdown">
   Use only when:
   - the PR is confirmed merged
   - local branch work is no longer needed
   - git branch -d failed due to stale merge detection
   </pre>

   <pre lang="bash">
   git branch -D "$CURRENT_BRANCH"
   </pre>

1. **Workflow Preferences**
   <pre lang="markdown">
   Prefer:
   - simple cleanup after merge
   - preserving current branch before checkout
   - pulling main before deleting the old branch
   - safe branch deletion with git branch -d
   - deleting the remote branch too (tolerate failure if already gone)
   - pruning stale remote references

   Avoid:
   - deleting branches before main is updated
   - force deleting branches without confirmation
   - creating new work during cleanup
   - mixing cleanup with new ChangeIt or FinishIt workflows
   </pre>

1. **Relationship to Other Workflows**
   <pre lang="markdown">
   ChangeIt:
   - starts from main
   - creates issue
   - creates branch
   - commits change
   - creates PR

   FinishIt:
   - assumes branch already exists
   - commits completed work
   - pushes current branch
   - creates PR
   - beeps 3 times once the PR is open

   PostMerge:
   - assumes PR is already merged
   - returns to main
   - updates main
   - deletes merged local branch
   - deletes merged remote branch
   - prunes stale remotes
   </pre>

<br>Author: Mike Mattinson/Chat
<br>Updated: Aug/15/2026
