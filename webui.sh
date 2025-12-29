#!/bin/bash

# This script launches Image Vibe Seeker by calling the launcher.py
# It assumes you have Python 3 installed on your system PATH.
# Pass --share to this script to expose the UI to the local network.

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Launch the app
python3 launcher.py "$@"

# Keep the window open if there's an error
if [ $? -ne 0 ]; then
    echo "An error occurred during startup."
    read -p "Press Enter to close..."
fi
