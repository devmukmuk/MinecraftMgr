#!/bin/sh
# Installs MinecraftMgr's shared git hooks into this clone's .git/hooks/.
# Re-run after cloning or if tools/git-hooks/* changes -- .git/hooks/ isn't
# tracked by git, so it doesn't update itself.

set -e
repo_root=$(git rev-parse --show-toplevel)

for hook in commit-msg pre-push; do
    cp "$repo_root/tools/git-hooks/$hook" "$repo_root/.git/hooks/$hook"
    chmod +x "$repo_root/.git/hooks/$hook"
    echo "Installed $hook hook into .git/hooks/."
done
