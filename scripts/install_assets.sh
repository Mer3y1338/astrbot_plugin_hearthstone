#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$ROOT/hs-alter-name/alter.json" ]; then
  echo "[assets] hs-alter-name missing, cloning..."
  git clone --depth 1 https://github.com/ZelKnow/hs-alter-name.git "$ROOT/hs-alter-name"
else
  echo "[assets] hs-alter-name already exists"
fi

if [ ! -d "$ROOT/hs-card-tiles/Tiles" ]; then
  echo "[assets] hs-card-tiles missing, cloning ~120MB..."
  rm -rf "$ROOT/hs-card-tiles"
  git clone --depth 1 https://github.com/HearthSim/hs-card-tiles.git "$ROOT/hs-card-tiles"
else
  echo "[assets] hs-card-tiles already exists"
fi

echo "[assets] done"
