"""
astrbot_plugin_hearthstone — 炉石传说卡牌查询与卡组生成

移植自 ZelKnow/Hearthbot (Nonebot2 → AstrBot)
原始作者: ZelKnow | 移植: Mer3y1338
"""
import re
import base64
import time
import asyncio
from io import BytesIO

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .card_handler import CardHandler, supported_langs
from .deck_handler import DeckHandler, supported_locale
from .archetype import _update_archetypes_loop


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
        self.max_response = cfg.get("max_response", 8)

        # 初始化处理器
        self.cardhandler = CardHandler(self.blizz_id, self.blizz_sec)
        self.deckhandler = DeckHandler()

        # 启动卡组分类数据每日更新
        asyncio.create_task(_update_archetypes_loop())

    # ── 卡牌搜索 /card ─────────────────────────────────────────
    @filter.command("card", alias={"c", "C", "CARD", "Card"})
    async def cmd_card(self, event: AstrMessageEvent):
        yield await self._handle_first(event, "card")

    # ── 卡牌标签 /tags ─────────────────────────────────────────
    @filter.command("tags", alias={"t", "T", "TAGS", "Tags", "tag"})
    async def cmd_tags(self, event: AstrMessageEvent):
        yield await self._handle_first(event, "tags")

    # ── 原画 /ori ──────────────────────────────────────────────
    @filter.command("ori", alias={"o", "O", "ORI", "Ori", "art"})
    async def cmd_ori(self, event: AstrMessageEvent):
        yield await self._handle_first(event, "ori")

    # ── 卡组 /deck ─────────────────────────────────────────────
    @filter.command("deck", alias={"d", "D", "DECK", "Deck"})
    async def cmd_deck(self, event: AstrMessageEvent):
        msg = event.get_message_str()
        parts = msg.split()[1:]  # strip command
        if not parts:
            yield event.plain_result("⚠️ 用法：/deck <AAE卡组代码> [卡组名称]")
            return

        locale = "zhCN"
        if len(parts[0]) == 4 and parts[0][0].isalpha():
            lang = parts[0][1:]
            if lang[0:2].lower() + lang[2:4].upper() in supported_locale:
                locale = lang
                parts = parts[1:]

        decks, names = self._parse_deck_args(parts)
        yield await self._render_decks(event, decks, names, locale)

    # ── 自动识别卡组代码 ───────────────────────────────────────
    @filter.regex(r"AAE[+\-0-9=A-Za-z/ ]{30,}")
    async def on_deck_code(self, event: AstrMessageEvent):
        msg = event.get_message_str()
        m = re.search(r"AAE[+\-0-9=A-Za-z/ ]{50,140}", msg)
        if m:
            deck_code = m.group(0).strip()
            img = await self._make_deck_img(deck_code, "", "zhCN")
            if isinstance(img, str):
                yield event.plain_result(img)
            else:
                url = self._pil_to_base64(img)
                yield event.image_result(url)

    # ── 多轮翻页/选卡 ──────────────────────────────────────────
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        _clean_sessions()
        user = event.get_sender_id()
        if user not in _sessions:
            return

        raw = event.get_message_str().strip()

        # 如果发的是新命令，忽略 session
        if raw.startswith("/") or raw.startswith("!"):
            return

        session = _sessions[user]
        session["last_active"] = time.time()

        # 选卡: /N 格式
        if re.match(r"[/\\]\s*[1-9]\d*$", raw):
            num = int(raw[1:]) - 1
            if num >= len(session["cards"]):
                yield event.plain_result("❌ 输入的编号超过结果总数量，请重新输入。")
                return
            card = session["cards"][num]
            yield await self._make_card_msg(event, card, session["args"], session["cmd_type"])
            return

        # 翻页: 纯数字
        if raw.isdigit():
            page = int(raw)
            hint = self.cardhandler.second_handle(
                session["cards"], page,
                session["args"]["is_bgs"],
                self.max_response
            )
            yield event.plain_result(hint)
            return

        # 过期/无效输入 → 清除 session
        del _sessions[user]

    # ── 内部方法 ───────────────────────────────────────────────

    async def _handle_first(self, event: AstrMessageEvent, cmd_type: str):
        """处理 card/tags/ori 命令的第一轮"""
        msg = event.get_message_str()
        parts = msg.strip().split()[1:]  # strip command
        args = {"lang": "zhCN", "is_bgs": False}
        terms = []

        for part in parts:
            if len(part) == 4 and part[0:2].lower() + part[2:4].upper() in supported_langs:
                args["lang"] = part[0:2].lower() + part[2:4].upper()
            elif part.lower() in ("bg", "bgs"):
                args["is_bgs"] = True
            else:
                terms.append(part)

        if not terms:
            return event.plain_result("⚠️ 用法：/card <卡牌名/关键词> [bg] [语言]")

        cards, hint = self.cardhandler.first_handle(terms, args["is_bgs"], self.max_response)

        if len(cards) == 1:
            return await self._make_card_msg(event, cards[0], args, cmd_type)
        elif len(cards) == 0:
            return event.plain_result(hint)

        # 多结果 → 存 session 供翻页
        _sessions[event.get_sender_id()] = {
            "cards": cards,
            "args": args,
            "cmd_type": cmd_type,
            "last_active": time.time(),
        }
        return event.plain_result(hint)

    async def _make_card_msg(self, event: AstrMessageEvent, card, args, cmd_type):
        """生成单张卡牌的回复"""
        if cmd_type == "card":
            url = await self.cardhandler.get_pic(card, args)
            return event.image_result(url)
        elif cmd_type == "tags":
            return event.plain_result(self.cardhandler.get_tags(card, args))
        elif cmd_type == "ori":
            url = self.cardhandler.get_ori(card)
            return event.image_result(url)

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

        url = self._pil_to_base64(result)
        yield event.image_result(url)

    async def _make_deck_img(self, code: str, name: str, locale: str):
        """生成单个卡组图片，返回 base64 URL 或错误字符串"""
        try:
            img = self.deckhandler.deck_to_image(code, name, locale)
            return img
        except Exception as e:
            logger.error(f"Deck render failed: {e}")
            return f"❌ 卡组生成失败，请检查代码格式：{e}"

    @staticmethod
    def _pil_to_base64(img) -> str:
        """PIL Image → base64:// data URI"""
        img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"base64://{b64}"
