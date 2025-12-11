#!/bin/bash

set -e

REPO="ton-user/ton-repo"
VERSION="latest"
BIN_NAME="portabase"
INSTALL_DIR="/usr/local/bin"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}==> Installation de Portabase CLI...${NC}"

OS="$(uname -s)"
ARCH="$(uname -m)"

case $OS in
    Linux)
        PLATFORM="linux"
        ;;
    Darwin)
        PLATFORM="macos"
        ;;
    *)
        echo -e "${RED}Erreur: OS non supporté ($OS)${NC}"
        exit 1
        ;;
esac

if [ "$ARCH" == "x86_64" ]; then
    ARCH_TAG="amd64"
elif [ "$ARCH" == "arm64" ] || [ "$ARCH" == "aarch64" ]; then
    ARCH_TAG="arm64"
else
    echo -e "${RED}Erreur: Architecture non supportée ($ARCH)${NC}"
    exit 1
fi

DOWNLOAD_URL="https://github.com/$REPO/releases/latest/download/$BIN_NAME-$PLATFORM-$ARCH_TAG"

echo -e "Détection: $OS ($ARCH)"
echo -e "Téléchargement depuis: $DOWNLOAD_URL"

if ! curl -L --progress-bar -o /tmp/$BIN_NAME "$DOWNLOAD_URL"; then
    echo -e "${RED}Erreur lors du téléchargement. Vérifiez votre connexion ou la version.${NC}"
    exit 1
fi

chmod +x /tmp/$BIN_NAME

echo -e "Installation dans $INSTALL_DIR (nécessite sudo)..."
if sudo mv /tmp/$BIN_NAME $INSTALL_DIR/$BIN_NAME; then
    echo -e "${GREEN}==> Portabase installé avec succès !${NC}"
    echo -e "Tapez 'portabase --help' pour commencer."
else
    echo -e "${RED}Erreur lors du déplacement du binaire.${NC}"
    exit 1
fi