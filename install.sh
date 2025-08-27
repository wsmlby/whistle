#!/bin/bash
set -e


# Configuration
GITHUB_REPO="wsmlby/whistle"
# Allow override by environment variable or first argument
INSTALL_DIR="${INSTALL_DIR:-/usr/bin}"
if [ -n "$1" ]; then
    INSTALL_DIR="$1"
fi
BINARY_NAME="whistle"
INSTALL_PATH="$INSTALL_DIR/$BINARY_NAME"

# Check dependencies
if ! command -v curl &> /dev/null; then
    echo "Error: curl is not installed. Please install it to continue." >&2
    exit 1
fi

# Determine if sudo is needed
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "Error: This script requires root privileges. Please run as root or install sudo." >&2
        exit 1
    fi
fi

echo "Fetching the latest release information from $GITHUB_REPO..."

# Get the download URL for the 'whistle' asset from the latest release
DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep "browser_download_url" | grep -o 'https://[^"]*' | grep "${BINARY_NAME}$")

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Could not find a download URL for the '$BINARY_NAME' binary in the latest release." >&2
    echo "Please check the repository '$GITHUB_REPO' and make sure a release with the binary asset exists." >&2
    exit 1
fi

echo "Downloading $BINARY_NAME from $DOWNLOAD_URL..."

# Download the binary to a temporary file
TMP_FILE=$(mktemp)
curl -L --progress-bar -o "$TMP_FILE" "$DOWNLOAD_URL"

echo "Installing $BINARY_NAME to $INSTALL_PATH..."

# Create the installation directory, move the binary, and make it executable
$SUDO mkdir -p "$INSTALL_DIR"
$SUDO mv "$TMP_FILE" "$INSTALL_PATH"
$SUDO chmod +x "$INSTALL_PATH"

echo ""
echo "$BINARY_NAME installed successfully to $INSTALL_PATH"
echo "Make sure to add '$INSTALL_DIR' to your PATH to run it directly."
echo "You can do this by adding the following line to your shell profile (e.g., ~/.bashrc or ~/.zshrc):"
echo "export PATH=\$PATH:$INSTALL_DIR"
