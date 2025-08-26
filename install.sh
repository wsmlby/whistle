#!/bin/bash
set -e

# Configuration
GITHUB_REPO="wsmlby/whistle"
INSTALL_DIR="/opt/whistle"
BINARY_NAME="whistle"
INSTALL_PATH="$INSTALL_DIR/$BINARY_NAME"

# Check for root privileges
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use sudo." >&2
    exit 1
fi

# Check for curl
if ! command -v curl &> /dev/null; then
    echo "curl is not installed. Please install it to continue." >&2
    exit 1
fi

echo "Fetching the latest release information from $GITHUB_REPO..."

# Get the download URL for the 'whistle' asset from the latest release
# This uses the GitHub API and some basic text processing to extract the URL.
# A more robust solution would use 'jq', but that is not a default utility.
DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep "browser_download_url" | grep -o 'https://[^"]*' | grep "${BINARY_NAME}$")

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Could not find a download URL for the '$BINARY_NAME' binary in the latest release." >&2
    echo "Please check the repository '$GITHUB_REPO' and make sure a release with the binary asset exists." >&2
    exit 1
fi

echo "Downloading $BINARY_NAME from $DOWNLOAD_URL..."

# Create the installation directory
mkdir -p "$INSTALL_DIR"

# Download the binary to a temporary file
TMP_FILE=$(mktemp)
curl -L --progress-bar -o "$TMP_FILE" "$DOWNLOAD_URL"

echo "Installing $BINARY_NAME to $INSTALL_PATH..."

# Move the binary to the installation path
mv "$TMP_FILE" "$INSTALL_PATH"

# Make the binary executable
chmod +x "$INSTALL_PATH"

echo ""
echo "$BINARY_NAME installed successfully to $INSTALL_PATH"
echo "Make sure to add '$INSTALL_DIR' to your PATH to run it directly."
echo "You can do this by adding the following line to your shell profile (e.g., ~/.bashrc or ~/.zshrc):"
echo "export PATH=\$PATH:$INSTALL_DIR"
