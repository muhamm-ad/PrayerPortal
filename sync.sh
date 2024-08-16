#!/bin/bash

# Define constants and variables for paths
USER_NAME=$(id -un)
CIRCUITPY_REPO="./CIRCUITPY"
CIRCUITPY_DRIVE="/media/${USER_NAME}/CIRCUITPY/"
SYNC_DIRECTION=${1}

# Function to ensure directory exists, otherwise create it
prepare_directory() {
    if [ ! -d "$1" ]; then
        echo "Directory $1 does not exist. Creating it now..."
        mkdir -p "$1"
        if [ $? -ne 0 ]; then
            echo "Failed to create the directory $1."
            exit 1
        fi
    fi
}

# Function to perform rsync and check for errors
perform_rsync() {
    rsync -avh --exclude='..?*' "$1" "$2"
    if [ $? -ne 0 ]; then
        echo "An error occurred during the rsync operation."
        exit 1
    else
        echo "Operation completed successfully."
    fi
}

# Check if SYNC_DIRECTION is provided
if [ -z "$SYNC_DIRECTION" ]; then
    echo "Usage: $0 {push|pull}"
    exit 1
fi

# Check if CIRCUITPY drive is mounted
if [ ! -d "$CIRCUITPY_DRIVE" ]; then
    echo "CIRCUITPY drive not found at $CIRCUITPY_DRIVE. Make sure the drive is mounted."
    exit 1
fi

# Synchronize based on the provided direction
case $SYNC_DIRECTION in
    push)
        echo "Starting file push to CIRCUITPY..."
        perform_rsync "$CIRCUITPY_REPO/" "$CIRCUITPY_DRIVE"
        ;;
    pull)
        echo "Starting file pull from CIRCUITPY..."
        prepare_directory "$CIRCUITPY_REPO"
        perform_rsync "$CIRCUITPY_DRIVE" "$CIRCUITPY_REPO/"
        ;;
    *)
        echo "Invalid argument. Use 'push' to send files or 'pull' to receive files."
        exit 1
        ;;
esac
