#!/bin/bash
set -e

BASE_URL="https://portabase-cli.s3.fr-par.scw.cloud/latest"
BINARY_NAME="portabase"
INSTALL_DIR="/usr/local/bin"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==> Portabase CLI Installer${NC}"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

if [ "$ARCH" == "x86_64" ]; then
    ARCH_TAG="amd64"
elif [ "$ARCH" == "arm64" ] || [ "$ARCH" == "aarch64" ]; then
    ARCH_TAG="arm64"
else
    echo -e "${RED}Error: Architecture '$ARCH' not supported.${NC}"
    exit 1
fi

if [ "$OS" == "darwin" ]; then
    OS_TAG="macos"
elif [ "$OS" == "linux" ]; then
    OS_TAG="linux"
else
    echo -e "${RED}Error: OS '$OS' not supported.${NC}"
    exit 1
fi

TARGET_FILE="${BINARY_NAME}-${OS_TAG}-${ARCH_TAG}"
DOWNLOAD_URL="${BASE_URL}/${TARGET_FILE}"

echo -e "Detected: ${GREEN}${OS_TAG} ${ARCH_TAG}${NC}"
echo -e "Downloading from: ${DOWNLOAD_URL}"

if ! curl -L --progress-bar -o "/tmp/$BINARY_NAME" "$DOWNLOAD_URL"; then
    echo -e "${RED}Download failed! Check your internet connection or if the version exists.${NC}"
    exit 1
fi

chmod +x "/tmp/$BINARY_NAME"

echo -e "Installing to $INSTALL_DIR (requires sudo)..."
if sudo mv "/tmp/$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"; then
    echo -e "${GREEN}✔ Installation successful!${NC}"
    echo -e "Run '${BINARY_NAME} --help' to get started."
else
    echo -e "${RED}Move failed.${NC}"
    exit 1
fi