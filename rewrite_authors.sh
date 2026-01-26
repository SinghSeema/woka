#!/bin/bash
# Script to rewrite Git commit history to use SinghSeema as the author

# Set the new author information
NEW_NAME="SinghSeema"
NEW_EMAIL="seema.tomar85@gmail.com"
OLD_EMAIL="ranjit@motorfloor.com"

echo "This script will rewrite Git history to change all commits from:"
echo "  RanjitMotorFloor <ranjit@motorfloor.com>"
echo "To:"
echo "  $NEW_NAME <$NEW_EMAIL>"
echo ""
echo "⚠️  WARNING: This will rewrite Git history and require a force push!"
echo "⚠️  Make sure you have a backup and coordinate with any collaborators!"
echo ""
read -p "Do you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# Rewrite the commit history
git filter-branch --env-filter "
if [ \"\$GIT_COMMITTER_EMAIL\" = \"$OLD_EMAIL\" ]; then
    export GIT_COMMITTER_NAME=\"$NEW_NAME\"
    export GIT_COMMITTER_EMAIL=\"$NEW_EMAIL\"
fi
if [ \"\$GIT_AUTHOR_EMAIL\" = \"$OLD_EMAIL\" ]; then
    export GIT_AUTHOR_NAME=\"$NEW_NAME\"
    export GIT_AUTHOR_EMAIL=\"$NEW_EMAIL\"
fi
" --tag-name-filter cat -- --branches --tags

echo ""
echo "✅ History rewritten!"
echo ""
echo "To push the changes, run:"
echo "  git push --force-with-lease origin main"
echo ""
echo "⚠️  Use --force-with-lease instead of --force for safety!"

