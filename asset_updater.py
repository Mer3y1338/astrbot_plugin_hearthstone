"""Hearthstone tile asset updater for astrbot_plugin_hearthstone.

Adds missing hs-card-tiles/Tiles/<CARD_ID>.png files from HearthstoneJSON.
Only writes new files; never overwrites existing tiles.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from hearthstone.enums import GameTag

PLUGIN_DIR = Path(__file__).resolve().parent
TILE_DIR = PLUGIN_DIR / "hs-card-tiles" / "Tiles"
STAGING_DIR = PLUGIN_DIR / ".asset-staging"
TILE_URL = "https://art.hearthstonejson.com/v1/tiles/{card_id}.png"


@dataclass
class UpdateResult:
    scanned: int = 0
    missing: int = 0
    added: int = 0
    skipped_404: int = 0
    bad_content: int = 0
    failed: int = 0
    duration: float = 0.0
    proxy: str = "直连"
    prefixes: list[str] = field(default_factory=list)
    manifest: str = ""
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "✅ 炉石资源更新完成" if self.failed == 0 else "⚠️ 炉石资源更新完成（部分失败）",
            f"扫描候选：{self.scanned}",
            f"本地缺失：{self.missing}",
            f"成功新增：{self.added}",
            f"CDN无图：{self.skipped_404}",
            f"非图片响应：{self.bad_content}",
            f"下载失败：{self.failed}",
            f"耗时：{self.duration:.1f}s",
            f"网络：{self.proxy}",
        ]
        if self.prefixes:
            lines.append("前缀：" + ", ".join(self.prefixes))
        if self.manifest:
            lines.append(f"manifest：{self.manifest}")
        if self.added == 0 and self.missing == 0:
            lines[0] = "✅ 当前资源已是最新，无需更新。"
        if self.failures:
            lines.append("失败样例：" + "; ".join(self.failures[:5]))
        return "\n".join(lines)


def _target_size() -> tuple[int, int]:
    if TILE_DIR.exists():
        for p in TILE_DIR.glob("*.png"):
            try:
                with Image.open(p) as img:
                    return img.size
            except Exception:
                continue
    # Existing hs-card-tiles are usually close to this size; used only if dir is empty.
    return (130, 34)


def _card_id(card) -> str:
    return str(getattr(card, "id", "") or "").strip()


def _is_constructed_candidate(card_handler, card) -> bool:
    fn = getattr(card_handler, "_is_collectible_constructed_card", None)
    if callable(fn):
        return bool(fn(card))
    return bool(getattr(card, "collectible", False))


def _collect_candidates(card_handler, prefixes: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []

    def add(card):
        cid = _card_id(card)
        if cid and cid not in seen:
            seen.add(cid)
            ids.append(cid)

    for card in getattr(card_handler, "cards_list", []) or []:
        if _is_constructed_candidate(card_handler, card):
            add(card)

    for card in getattr(card_handler, "bgs_list", []) or []:
        if GameTag.TECH_LEVEL in getattr(card, "tags", {}):
            add(card)

    clean_prefixes = [p.strip().upper() for p in (prefixes or []) if p.strip()]
    if clean_prefixes:
        ids = [cid for cid in ids if any(cid.upper().startswith(prefix) for prefix in clean_prefixes)]
    return ids


async def _fetch_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, card_id: str,
                     target_size: tuple[int, int]) -> tuple[str, str]:
    final = TILE_DIR / f"{card_id}.png"
    if final.exists():
        return card_id, "exists"

    url = TILE_URL.format(card_id=card_id)
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "image/*,*/*;q=0.8"}
    async with sem:
        try:
            resp = await client.get(url, headers=headers)
        except Exception as exc:
            return card_id, f"failed:{type(exc).__name__}:{exc}"

    content_type = resp.headers.get("content-type", "").split(";", 1)[0].lower()
    if resp.status_code == 404:
        return card_id, "404"
    if resp.status_code != 200:
        return card_id, f"failed:http_{resp.status_code}"
    if not content_type.startswith("image/"):
        return card_id, f"bad_content:{content_type or 'unknown'}"

    try:
        with Image.open(BytesIO(resp.content)) as img:
            img = img.convert("RGBA")
            if img.size != target_size:
                img = img.resize(target_size, Image.LANCZOS)
            tmp = final.with_suffix(final.suffix + ".tmp")
            img.save(tmp, format="PNG")
            os.replace(tmp, final)
    except Exception as exc:
        return card_id, f"failed:image:{type(exc).__name__}:{exc}"
    return card_id, "added"


async def update_missing_tiles(card_handler, proxy: str = "", prefixes: list[str] | None = None,
                               limit: int | None = None, concurrency: int = 8) -> UpdateResult:
    started = time.monotonic()
    clean_prefixes = [p.strip().upper() for p in (prefixes or []) if p.strip()]
    result = UpdateResult(proxy=proxy or "直连", prefixes=clean_prefixes)

    TILE_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    candidates = _collect_candidates(card_handler, clean_prefixes)
    result.scanned = len(candidates)
    missing = [cid for cid in candidates if not (TILE_DIR / f"{cid}.png").exists()]
    result.missing = len(missing)
    if limit is not None:
        missing = missing[:max(0, limit)]
    if not missing:
        result.duration = time.monotonic() - started
        return result

    target_size = _target_size()
    client_args = {
        "timeout": httpx.Timeout(15.0),
        "follow_redirects": True,
        "trust_env": False,
    }
    if proxy:
        client_args["proxy"] = proxy

    added_ids: list[str] = []
    sem = asyncio.Semaphore(max(1, int(concurrency or 1)))
    async with httpx.AsyncClient(**client_args) as client:
        tasks = [_fetch_one(client, sem, cid, target_size) for cid in missing]
        for card_id, status in await asyncio.gather(*tasks):
            if status == "added":
                result.added += 1
                added_ids.append(card_id)
            elif status == "404":
                result.skipped_404 += 1
            elif status.startswith("bad_content"):
                result.bad_content += 1
                result.failures.append(f"{card_id}:{status}")
            elif status == "exists":
                pass
            else:
                result.failed += 1
                result.failures.append(f"{card_id}:{status}")

    if added_ids:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run_manifest = STAGING_DIR / f"added-tiles-{stamp}.txt"
        run_manifest.write_text("\n".join(added_ids) + "\n", encoding="utf-8")
        with (STAGING_DIR / "added-tiles-manifest.txt").open("a", encoding="utf-8") as f:
            for cid in added_ids:
                f.write(f"{stamp}\t{cid}.png\n")
        result.manifest = str(run_manifest.relative_to(PLUGIN_DIR))

    result.duration = time.monotonic() - started
    return result
