#!/bin/bash

# Util script to merge multiple branches as listed in a file into a new branch
# Used for dev.openlibrary.org "deploys"
# See make-integration-branch-sample.txt for a sample of the file format.

BRANCHES_FILE=$1
NEW_BRANCH=$2
ONLY_STARRED=$(grep '^\*\*' $BRANCHES_FILE | sed 's/\*\*//g' )

echo $ALL_BRANCHES
git checkout master
git pull origin master
git branch -D $NEW_BRANCH
git checkout -b $NEW_BRANCH

while read line; do
    branch=${line/\*\*/}
    if [[ -z $line || $line == "#"* ]] ; then
        :
    elif [[ ! -z $ONLY_STARRED && $line != "**"* ]] ; then
        :
    elif [[ $branch == "https://"* ]] ; then
        echo -e "---\n$branch"
        git pull $branch
    else
        echo -e "---\n$branch"
        git merge $branch
    fi
done <"$BRANCHES_FILE"
