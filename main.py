"""
astrbot_plugin_hearthstone — 炉石传说卡牌查询与卡组生成

移植自 ZelKnow/Hearthbot (Nonebot2 → AstrBot)
原始作者: ZelKnow | 移植: Mer3y1338
"""
import re
import time
import asyncio
from io import BytesIO

import httpx
import astrbot.core.message.components as Comp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .card_handler import CardHandler, supported_langs
from .deck_handler import DeckHandler, supported_locale
from .archetype import _update_archetypes_loop
from .asset_updater import update_missing_tiles


# ── 多轮对话状态 ──────────────────────────────────────────────
# user_id → {cards, args, cmd_type, last_active}
_sessions: dict = {}
SESSION_TTL = 300  # 5分钟过期


def _clean_sessions():
    """清理过期 session"""
    now = time.time()
    expired = [uid for uid, s in _sessions.items() if now - s.get("last_active", 0) > SESSION_TTL]
    for uid in expired:
        del _sessions[uid]


def _session_key(event: AstrMessageEvent) -> str:
    """Return a stable per-conversation/per-user key for multi-turn card selection."""
    sender = event.get_sender_id() or "unknown"
    return f"{event.unified_msg_origin}:{sender}"


@register("astrbot_plugin_hearthstone", "Mer3y1338",
          "🔥 炉石传说卡牌查询与卡组生成插件 — 多语言搜索/原画/tags/卡组渲染",
          "1.0.0", "https://github.com/Mer3y1338/astrbot_plugin_hearthstone")
class HearthstonePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 读取配置
        cfg = context.get_config() or {}
        self.blizz_id = cfg.get("blizz_id", "")
        self.blizz_sec = cfg.get("blizz_sec", "")
        try:
            self.max_response = max(1, int(cfg.get("max_response", 8) or 8))
        except (TypeError, ValueError):
            self.max_response = 8
        self.resource_proxy = (cfg.get("resource_proxy", "") or "").strip()
        self._resource_update_lock = asyncio.Lock()

        # 初始化处理器
        self.cardhandler = CardHandler(self.blizz_id, self.blizz_sec)
        self.deckhandler = DeckHandler()

        # 启动卡组分类数据每日更新
        self._archetype_task = asyncio.create_task(_update_archetypes_loop())

    async def terminate(self):
        """Cancel background task on plugin unload/reload."""
        task = getattr(self, "_archetype_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # ── 卡牌搜索 /card ─────────────────────────────────────────
    @filter.command("card", alias={"c", "C", "CARD", "Card"})
    async def cmd_card(self, event: AstrMessageEvent):
        yield await self._handle_first(event, "card")
        event.stop_event()

    # ── 构筑可收藏卡牌搜索 /查卡 ────────────────────────────────
    @filter.command("查卡", alias={"炉石查卡", "卡牌"})
    async def cmd_card_cn(self, event: AstrMessageEvent):
        yield await self._handle_first(
            event, "card", collectible_only=True,
            usage="/查卡 <卡牌名/关键词> [语言]"
        )
        event.stop_event()

    # ── 构筑种族/标签检索 /tag ─────────────────────────────────
    @filter.command("tag", alias={"tags", "t", "T", "TAGS", "Tags"})
    async def cmd_tags(self, event: AstrMessageEvent):
        yield await self._handle_first(
            event, "card", collectible_only=True,
            usage="/tag <种族/标签> [语言]，例如：/tag 野兽",
            search_mode="race", list_mode="race"
        )
        event.stop_event()

    # ── 酒馆战棋卡牌搜索 /查酒馆 ───────────────────────────────
    @filter.command("查酒馆", alias={"酒馆", "酒馆卡牌", "bgcard", "bgs"})
    async def cmd_bgs_card(self, event: AstrMessageEvent):
        yield await self._handle_first(
            event, "card", is_bgs_default=True,
            usage="/查酒馆 <卡牌名/关键词> [语言]"
        )
        event.stop_event()

    # ── 酒馆战棋种族/标签检索 /酒馆tag ─────────────────────────
    @filter.command("酒馆tag", alias={"酒馆标签", "bgtag", "bgstags"})
    async def cmd_bgs_tags(self, event: AstrMessageEvent):
        yield await self._handle_first(
            event, "card", is_bgs_default=True,
            usage="/酒馆tag <种族/标签> [语言]，例如：/酒馆tag 鱼人",
            search_mode="race", list_mode="race"
        )
        event.stop_event()

    # ── 原画 /ori ──────────────────────────────────────────────
    @filter.command("ori", alias={"o", "O", "ORI", "Ori", "art", "原画"})
    async def cmd_ori(self, event: AstrMessageEvent):
        yield await self._handle_first(event, "ori")
        event.stop_event()

    # ── 卡组 /deck ─────────────────────────────────────────────
    @filter.command("deck", alias={"d", "D", "DECK", "Deck", "卡组"})
    async def cmd_deck(self, event: AstrMessageEvent):
        msg = event.get_message_str()
        parts = msg.split()[1:]  # strip command
        if not parts:
            yield event.plain_result("⚠️ 用法：/deck <AAE卡组代码> [卡组名称]")
            event.stop_event()
            return

        locale = "zhCN"
        if len(parts[0]) == 4 and parts[0][0].isalpha():
            lang = parts[0][1:]
            if lang[0:2].lower() + lang[2:4].upper() in supported_locale:
                locale = lang
                parts = parts[1:]

        decks, names = self._parse_deck_args(parts)
        async for item in self._render_decks(event, decks, names, locale):
            yield item
        event.stop_event()


    # ── 更新卡组条图资源 /更新资源 ───────────────────────────────
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("更新资源", alias={"更新炉石资源", "hs更新资源", "更新炉石卡图"})
    async def cmd_update_resources(self, event: AstrMessageEvent):
        msg = event.get_message_str()
        parts = msg.strip().split()[1:]
        prefixes = []
        limit = None
        for part in parts:
            if part in {"help", "帮助", "-h", "--help"}:
                yield event.plain_result(
                    "用法：/更新资源 [前缀...] [limit=数量]\n"
                    "示例：/更新资源 CATA EDR BG31\n"
                    "代理请在插件设置里的 resource_proxy 填写；留空则直连"
                )
                event.stop_event()
                return
            if part.startswith("limit="):
                try:
                    limit = max(0, int(part.split("=", 1)[1]))
                except ValueError:
                    yield event.plain_result("❌ limit 必须是数字，例如：/更新资源 CATA limit=50")
                    event.stop_event()
                    return
            else:
                prefixes.append(part)

        if self._resource_update_lock.locked():
            yield event.plain_result("⏳ 已有资源更新任务在运行，请稍后再试。")
            event.stop_event()
            return

        proxy_hint = self.resource_proxy or "直连"
        scope = " ".join(prefixes) if prefixes else "可收藏构筑卡 + 酒馆战棋"
        yield event.plain_result(f"⏳ 开始更新炉石条图资源...\n范围：{scope}\n网络：{proxy_hint}")

        async with self._resource_update_lock:
            try:
                result = await update_missing_tiles(
                    self.cardhandler,
                    proxy=self.resource_proxy,
                    prefixes=prefixes,
                    limit=limit,
                )
                yield event.plain_result(result.summary())
            except Exception as e:
                logger.error(f"Resource update failed: {e}")
                yield event.plain_result(f"❌ 资源更新失败：{e}")
        event.stop_event()

    # ── 自动识别卡组代码 ───────────────────────────────────────
    @filter.regex(r"AAE[+\-0-9=A-Za-z/]{30,500}")
    async def on_deck_code(self, event: AstrMessageEvent):
        msg = event.get_message_str()
        m = re.search(r"AAE[+\-0-9=A-Za-z/]{30,500}", msg)
        if m:
            deck_code = m.group(0).strip()
            img = await self._make_deck_img(deck_code, "", "zhCN")
            if isinstance(img, str):
                yield event.plain_result(img)
            else:
                image_bytes = self._pil_to_bytes(img)
                yield event.chain_result([Comp.Image.fromBytes(image_bytes)])
            event.stop_event()

    # ── 多轮翻页/选卡 ──────────────────────────────────────────
    @filter.event_message_type(filter.EventMessageType.ALL, priority=200)
    async def on_message(self, event: AstrMessageEvent):
        _clean_sessions()
        key = _session_key(event)
        if key not in _sessions:
            return

        raw = event.get_message_str().strip()
        session = _sessions[key]
        session["last_active"] = time.time()

        # 选卡：兼容 1、\1、/1 三种输入。纯数字默认选择卡牌，避免被主 LLM 当普通聊天。
        pick = re.fullmatch(r"(?:[/\\]\s*)?([1-9]\d*)", raw)
        if pick:
            num = int(pick.group(1)) - 1
            if num >= len(session["cards"]):
                yield event.plain_result("❌ 输入的编号超过结果总数量，请重新输入。")
                event.stop_event()
                return
            card = session["cards"][num]
            yield await self._make_card_msg(event, card, session["args"], session["cmd_type"])
            event.stop_event()
            return

        # 翻页：改为 p2 / page 2 / 第2页，避免和选卡数字冲突。
        page_match = re.fullmatch(r"(?:p|page|第)\s*([1-9]\d*)\s*(?:页)?", raw, re.IGNORECASE)
        if page_match:
            page = int(page_match.group(1))
            session["page"] = page
            hint = self.cardhandler.second_handle(
                session["cards"], page,
                session["args"]["is_bgs"],
                self.max_response,
                session.get("list_mode", session["cmd_type"])
            )
            yield event.plain_result(hint)
            event.stop_event()
            return

        # 如果发的是新命令，忽略 session，让其它插件/命令处理。
        if raw.startswith("/") or raw.startswith("!"):
            return

        # 无效输入 → 清除 session，避免长期劫持普通聊天。
        del _sessions[key]

    # ── 内部方法 ───────────────────────────────────────────────

    async def _handle_first(
        self, event: AstrMessageEvent, cmd_type: str,
        is_bgs_default: bool = False, collectible_only: bool = False,
        usage: str | None = None, search_mode: str = "name",
        list_mode: str | None = None
    ):
        """处理 card/tags/ori 命令的第一轮"""
        msg = event.get_message_str()
        parts = msg.strip().split()[1:]  # strip command
        args = {"lang": "zhCN", "is_bgs": is_bgs_default}
        terms = []

        for part in parts:
            if len(part) == 4 and part[0:2].lower() + part[2:4].upper() in supported_langs:
                args["lang"] = part[0:2].lower() + part[2:4].upper()
            elif part.lower() in ("bg", "bgs") or part == "酒馆":
                args["is_bgs"] = True
            else:
                terms.append(part)

        if not terms:
            return event.plain_result(f"⚠️ 用法：{usage or '/card <卡牌名/关键词> [bg] [语言]'}")

        cards, hint = self.cardhandler.first_handle(
            terms, args["is_bgs"], self.max_response,
            collectible_only=collectible_only,
            list_mode=list_mode or cmd_type,
            search_mode=search_mode
        )

        if len(cards) == 1:
            return await self._make_card_msg(event, cards[0], args, cmd_type)
        elif len(cards) == 0:
            return event.plain_result(hint)

        # 多结果 → 存 session 供翻页
        _sessions[_session_key(event)] = {
            "cards": cards,
            "args": args,
            "cmd_type": cmd_type,
            "list_mode": list_mode or cmd_type,
            "page": 1,
            "last_active": time.time(),
        }
        return event.plain_result(hint)

    async def _make_card_msg(self, event: AstrMessageEvent, card, args, cmd_type):
        """生成单张卡牌的回复"""
        if cmd_type == "card":
            url = await self.cardhandler.get_pic(card, args)
            return await self._image_url_result(event, url)
        elif cmd_type == "tags":
            return event.plain_result(self.cardhandler.get_tags(card, args))
        elif cmd_type == "ori":
            url = self.cardhandler.get_ori(card)
            return await self._image_url_result(event, url)

    def _parse_deck_args(self, parts: list) -> tuple:
        """解析 deck 命令参数"""
        if len(parts) == 0:
            return [], []
        if parts[-1].startswith("AAE"):
            return parts, [""] * len(parts)
        if len(parts) >= 2 and parts[1].startswith("AAE"):
            return parts[:-1], [parts[-1]] * (len(parts) - 1)
        decks = parts[::2]
        names = parts[1::2]
        return decks, names

    async def _render_decks(self, event, decks: list, names: list, locale: str):
        """渲染卡组图片"""
        if not decks:
            yield event.plain_result("⚠️ 未提供有效的卡组代码")
            return

        deck_imgs = []
        for i, code in enumerate(decks):
            try:
                name = names[i] if i < len(names) else ""
                img = self.deckhandler.deck_to_image(code, name, locale)
                deck_imgs.append(img)
            except Exception as e:
                logger.error(f"Deck render failed for {code[:20]}...: {e}")
                yield event.plain_result(f"❌ 卡组 {i+1} 生成失败，请检查代码格式！")
                return

        if len(deck_imgs) == 1:
            result = deck_imgs[0]
        else:
            result = self.deckhandler.merge(deck_imgs)

        image_bytes = self._pil_to_bytes(result)
        yield event.chain_result([Comp.Image.fromBytes(image_bytes)])

    async def _make_deck_img(self, code: str, name: str, locale: str):
        """生成单个卡组图片，返回 base64 URL 或错误字符串"""
        try:
            img = self.deckhandler.deck_to_image(code, name, locale)
            return img
        except Exception as e:
            logger.error(f"Deck render failed: {e}")
            return f"❌ 卡组生成失败，请检查代码格式：{e}"

    async def _image_url_result(self, event: AstrMessageEvent, url: str):
        """Download remote image first, then send bytes to avoid QQ/NapCat rich media URL failures."""
        if not url:
            return event.plain_result("❌ 图片资源不可用：没有可发送的图片地址")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            content_type = resp.headers.get("content-type", "").split(";", 1)[0].lower()
            if resp.status_code != 200 or not content_type.startswith("image/"):
                logger.warning(
                    f"Hearthstone image unavailable: status={resp.status_code} "
                    f"content_type={content_type or 'unknown'} url={url}"
                )
                return event.plain_result(f"❌ 图片资源不可用：HTTP {resp.status_code}")
            return event.chain_result([Comp.Image.fromBytes(resp.content)])
        except Exception as e:
            logger.error(f"Hearthstone image download failed: {url}: {e}")
            return event.plain_result(f"❌ 图片下载失败：{e}")

    @staticmethod
    def _pil_to_bytes(img) -> bytes:
        """PIL Image → JPEG bytes for Comp.Image.fromBytes."""
        img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
