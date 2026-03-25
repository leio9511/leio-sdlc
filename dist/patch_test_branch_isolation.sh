#!/bin/bash
sed -i 's/git checkout master || git checkout main/git stash push -m "temp_test_stash" \&\& git checkout master || git checkout main/g' scripts/test_branch_isolation.sh
sed -i '/git checkout $ORIGINAL_BRANCH || true/a \    git stash pop -q || true' scripts/test_branch_isolation.sh
