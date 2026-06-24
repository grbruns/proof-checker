#!/bin/bash

# Install path: /usr/local/bin/git-hook.sh
# Working Directory: /home/git-hook/capstone-openLogic
cd /home/git-hook/capstone-openLogic

# This file is used to keep track of when the git-hook was last run
TS_FILE="/home/git-hook/git-hook.timestamp"

# The minimum number of seconds between runs of the git-hook script
MIN_INTERVAL=15

# The log file for the git-hook service
LOG_FILE=/home/git-hook/git-hook-service.log

# The nginx log file for the git-hook URL
TAIL_FILE=/var/log/nginx/git-hook.log

LIVE_PATH="/var/www/live/public_html"
LIVE_BACKEND="backend"

DEV_PATH="/var/www/dev/public_html"
DEV_BACKEND="backend-dev"

# Get the currently checked-out branch of a git repository
function getCurrentBranch {
    git branch | awk '/^\*/{print $2}'
}

# Function that updates a public_html folder, given a path as first argument
function updatePublicHtml {
    CID=$(git rev-parse HEAD)
    cd frontend
    cp *.html *.css *.js *.php "$1/"
    cp -r assets "$1/"
    <index.html sed "s/GIT_VERSION_TAG/$CID/" >"$1/index.html"
    cd ..
}

# Function that updates backend and restarts service, given file/service name as first argument
function updateBackend {
    # Delete previous build of backend
    [[ -f backend/backend ]] && rm backend/backend
    cd backend
    GONOSUMDB=* GOFLAGS=-mod=mod go build -o backend . >>$LOG_FILE 2>&1
    if [[ -x ./backend ]]; then
        sudo systemctl stop $1
        sleep 1
        cp backend /usr/local/bin/$1
        sudo systemctl start $1
        >>$LOG_FILE echo "[$1]: Backend recompiled and restarted."
    else
        >>$LOG_FILE echo "[$1]: Backend did not build successfully."
    fi
    cd ..
}

# Update only branches which have changed
function updateChangedBranches {
    # Pull both branches
    git fetch --all
    git checkout master
    git pull
    git checkout dev
    git pull

    # Get latest commit id from both branches
    MASTER_REV=$(git rev-parse refs/heads/master)
    DEV_REV=$(git rev-parse refs/heads/dev)

    # If the revision.txt has not been created previously, create it now.
    [[ ! -f "$LIVE_PATH/revision.txt" ]] && touch "$LIVE_PATH/revision.txt"
    [[ ! -f "$DEV_PATH/revision.txt" ]] && touch "$DEV_PATH/revision.txt"

    # Get the deployed commit ids
    MASTER_DEPLOYED_REV=$(<"$LIVE_PATH/revision.txt")
    DEV_DEPLOYED_REV=$(<"$DEV_PATH/revision.txt")

    # Compare current commit ids and deployed commit ids
    if [[ "$MASTER_REV" != "$MASTER_DEPLOYED_REV" ]]; then
        >>$LOG_FILE echo "[Git-Hook]: Updating LIVE from ($MASTER_DEPLOYED_REV) to ($MASTER_REV)."
        git checkout master
        git reset --hard HEAD
        git pull origin master
        updatePublicHtml "$LIVE_PATH"
        updateBackend "$LIVE_BACKEND"

        echo "$MASTER_REV" > "$LIVE_PATH/revision.txt"
    fi

    if [[ "$DEV_REV" != "$DEV_DEPLOYED_REV" ]]; then
        >>$LOG_FILE echo "[Git-Hook]: Updating DEV from ($DEV_DEPLOYED_REV) to ($DEV_REV)."
        git checkout dev
        git reset --hard HEAD
        git pull origin dev
        updatePublicHtml "$DEV_PATH"
        updateBackend "$DEV_BACKEND"

        echo "$DEV_REV" > "$DEV_PATH/revision.txt"
    fi
}

function runGitHook {
    touch "$TS_FILE"
    >>$LOG_FILE echo "[Git-Hook]: Started at `date`"

    updateChangedBranches
}

# Check if it has been at least 
function shouldRunGitHook {
    LAST_RUN_TIMESTAMP=$(stat -c '%Y' "$TS_FILE") || LAST_RUN_TIMESTAMP=0
    CURRENT_TIMESTAMP=$(date +'%s')

    if [[ $(( $LAST_RUN_TIMESTAMP - $CURRENT_TIMESTAMP )) -gt $MIN_INTERVAL ]]; then
        echo "Running git-hook, over $MIN_INTERVAL seconds since last run."
        runGitHook
    fi
}

# Check for initial deploy
if [[ ! -f "$TS_FILE" ]]; then
    runGitHook
fi

# Use tail to monitor the nginx log file for the git-hook URL
# Important: follow by name, rather than by inode. This means
# that the hook can continue working after log rotation.

tail --follow=name --retry $TAIL_FILE | while read; do
    shouldRunGitHook && runGitHook
done