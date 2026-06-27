#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File          : card_handler.py
@Description   : Handle Hearthstone card.
@Date          : 2021/08/12 22:40:39
@Author        : ZelKnow
@Github        : https://github.com/ZelKnow
"""
__author__ = "ZelKnow"

from hearthstone import cardxml, stringsfile
from hearthstone.cardxml import CardXML
from hearthstone.enums import CardSet, CardType, GameTag, Locale, Race, Rarity, MultiClassGroup
import math
import json
import os
import re
import httpx
import logging
logger = logging.getLogger("Hearthstone")
from functools import cmp_to_key

path = os.path.dirname(__file__)
with open(os.path.join(path, "hs-alter-name", "alter.json"),
          encoding="utf-8") as json_file:
    alter = json.load(json_file)
supported_langs = [locale.name for locale in Locale.__members__.values()]
translation = stringsfile.load_globalstrings('zhCN')

CONSTRUCTED_EXCLUDED_SETS = {
    "BATTLEGROUNDS",
    "HERO_SKINS",
    "LETTUCE",
    "PLACEHOLDER_202204",
    "TB",
    "VANILLA",
}


def card_compare(a, b):
    if a.collectible == b.collectible:
        if type(a.card_set) is int:
            return -1
        elif type(b.card_set) is int:
            return 1
        elif a.card_set.is_standard == b.card_set.is_standard:
            if a.card_set.numerator == b.card_set.numerator:
                return 1 if a.cost < b.cost else -1
            else:
                return 1 if a.card_set.numerator > b.card_set.numerator else -1
        else:
            return 1 if a.card_set.is_standard else -1
    else:
        return 1 if a.collectible else -1


def loc_name(self, locale):
    return self.strings[GameTag.CARDNAME][locale]


def set_name(self, locale):
    return self.strings[GameTag.CARD_SET][locale]


def loc_text(self, locale):
    return self.strings[GameTag.CARDTEXT_INHAND][locale]


def loc_flavor(self, locale):
    return self.strings[GameTag.FLAVORTEXT][locale]


def translate(data):
    return translation.get(data.name_global, {'TEXT': data.name}).get('TEXT', data.name)


def get_card_class(card):
    card_class = "/".join([translate(card_class) for card_class in card.classes])
    if card_class in ['INVALID', '']:
        card_class = '无职业'

    return card_class


def get_card_races(card):
    races = list(getattr(card, "races", None) or [])
    if not races and card.race != Race.INVALID:
        races = [card.race]
    return [race for race in races if race != Race.INVALID]


CardXML.loc_name = loc_name
CardXML.loc_text = loc_text
CardXML.loc_flavor = loc_flavor


def create_access_token(client_id, client_secret, region='us'):
    if (region == 'cn'):
        url = 'https://www.battlenet.com.cn/oauth/token'
    else:
        url = "https://%s.battle.net/oauth/token" % region
    body = {"grant_type": 'client_credentials'}
    response = httpx.post(url,
                          data=body,
                          auth=(client_id, client_secret),
                          timeout=9).json()
    return response["access_token"]


class CardHandler():
    def __init__(self, Blizz_ID, Blizz_Sec):
        db, _ = cardxml.load()
        self.cards_list = self._init_cards(db)
        self.bgs_list = self._init_bgs(db)
        self.Blizz_ID = Blizz_ID
        self.Blizz_Sec = Blizz_Sec
        self.use_offi = False
        if Blizz_ID and Blizz_Sec:
            try:
                self.token = create_access_token(Blizz_ID, Blizz_Sec)
                self.use_offi = True
            except:
                logger.info("未填写暴雪API信息或获取token失败，改为使用hearthstonejson提供的API")

    def _init_cards(self, db):
        cards_list = []
        for card in db:
            if db[card].type != CardType.ENCHANTMENT and "zhCN" in db[
                    card].strings[GameTag.CARDNAME]:
                db[card].alter = alter.get(
                    db[card].strings[GameTag.CARDNAME]["zhCN"], [])
                cards_list.append(db[card])
        cards_list.sort(key=cmp_to_key(card_compare), reverse=True)
        return cards_list

    def _init_bgs(self, db):
        temp = {}
        bgs = {}
        for card in db:
            if (GameTag.TECH_LEVEL in db[card].tags and db[card].card_set
                    not in [CardSet.VANILLA, CardSet.CORE]):
                temp[db[card].dbf_id] = db[card]
        missing_pairs = []
        for card in temp:
            if 1429 in temp[card].tags:
                bgs[card] = temp[card]
                pair_id = temp[card].tags[1429]
                if pair_id in temp:
                    bgs[pair_id] = temp[pair_id]
                else:
                    missing_pairs.append(pair_id)
        if missing_pairs:
            logger.warning(f"Skipped {len(missing_pairs)} missing Battlegrounds pair cards")
        return bgs.values()

    def _is_collectible_constructed_card(self, card):
        if not card.collectible:
            return False
        card_set = getattr(card.card_set, "name", str(card.card_set))
        if card_set in CONSTRUCTED_EXCLUDED_SETS:
            return False
        if card.type == CardType.HERO and card.cost == 0 and str(card.id).startswith("HERO_"):
            return False
        return True

    def first_handle(self, terms, is_bgs, max_response, collectible_only=False,
                     list_mode="card", search_mode="name"):
        cards = []
        search_list = self.bgs_list if is_bgs else self.cards_list
        matcher = self.search_race if search_mode == "race" else self.search
        for card in search_list:
            if collectible_only and not is_bgs and not self._is_collectible_constructed_card(card):
                continue
            if all([matcher(term, card, is_bgs) for term in terms]):
                cards.append(card)
        num_cards = len(cards)
        if num_cards == 0:
            hint = "找不到相应的卡牌" if search_mode == "name" else "找不到符合该种族/标签的卡牌"
        elif num_cards == 1:
            hint = ""
        else:
            hint = self.second_handle(cards, 1, is_bgs, max_response, list_mode)
        return cards, hint

    def second_handle(self, cards, page, is_bgs, max_response, list_mode="card"):
        num_cards = len(cards)
        page_size = min(max_response, num_cards)
        page_count = math.ceil(num_cards / page_size)
        page = min(page_count, max(1, page))
        offset = (page - 1) * page_size
        if list_mode == "race":
            scope = "酒馆种族卡牌" if is_bgs else "构筑种族卡牌"
        else:
            scope = "酒馆卡牌" if is_bgs else "构筑卡牌"
        action = "查看 tag" if list_mode == "tags" else "选择卡牌"
        page_hint = (
            "查询到%d张%s，当前页数[%d/%d]\n"
            "回复数字%s，回复 p2 翻页\n" %
            (num_cards, scope, page, page_count, action)
        )
        hint = page_hint + "\n".join(
            self.stringify_card(cards[i], i + 1, is_bgs)
            for i in range(offset, min(offset + page_size, num_cards)))
        return hint

    def search(self, term, card, is_bgs):
        if re.match(r"\d+[\\/]\d+[\\/]\d+", term):
            cost = card.tags[GameTag.TECH_LEVEL] if is_bgs else card.cost
            attack = card.atk
            health = (card.durability
                      if card.type == CardType.WEAPON else card.health)
            if [cost, attack,
                    health] == list(map(int, re.split(r"[\\/]", term))):
                return True
        elif any([term in altername for altername in card.alter]):
            return True
        elif term in card.loc_name("zhCN").lower():
            return True
        return False

    def search_race(self, term, card, is_bgs):
        term = term.strip().lower()
        if not term:
            return False
        races = get_card_races(card)
        all_race = Race.ALL in races
        all_aliases = {"全种族", "全部种族", "全部", "融合", "融合怪", "all"}
        for race in Race.__members__.values():
            if race == Race.INVALID:
                continue
            cn = translate(race).lower()
            names = {race.name.lower(), cn}
            if len(cn) == 1:
                names.add(f"{cn}族")
            if term in names:
                return race in races or all_race or (race == Race.ALL and term in all_aliases)
        return term in all_aliases and all_race

    def stringify_card(self, card, index, is_bgs):
        card_class = get_card_class(card)
        cost = "%d星" % card.tags[GameTag.TECH_LEVEL] if is_bgs else "%d费" % card.cost
        card_type = translate(card.type)
        name = card.loc_name("zhCN")
        gold = "（金）" if is_bgs and 1429 not in card.tags else ""
        card_set = ("无" if type(card.card_set) is int else
                    translate(card.card_set))
        races = "/".join(translate(race) for race in get_card_races(card))
        race_text = "，%s" % races if races else ""
        return ("\\%d：%s%s，%s%s%s，%s%s" %
                (index, name, gold, cost, card_class, card_type, card_set, race_text))

    async def get_pic(self, card, args):
        if self.use_offi:
            return await self.get_pic_offi(card, args)
        else:
            return self.get_pic_hsj(card, args)

    def get_pic_hsj(self, card, args):
        if args["is_bgs"]:
            if 1429 not in card.tags:
                return (
                    "https://art.hearthstonejson.com/v1/bgs/latest/%s/512x/%s_triple.png"
                    % (args["lang"], card.id))
            else:
                return (
                    "https://art.hearthstonejson.com/v1/bgs/latest/%s/512x/%s.png"
                    % (args["lang"], card.id))
        else:
            return (
                "http://art.hearthstonejson.com/v1/render/latest/%s/512x/%s.png"
                % (args["lang"], card.id))

    async def get_pic_offi(self, card, args):
        if not self.token:
            return None
        locale = args["lang"]
        locale = locale[0:2] + "_" + locale[2:4]
        game_mode = "battlegrounds" if args["is_bgs"] else "constructed"
        url = "https://api.blizzard.com/hearthstone/cards/%d?locale=%s&gameMode=%s&access_token=%s" % (
            card.dbf_id, locale, game_mode, self.token)
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            if resp:
                card_data = resp.json()
                if args["is_bgs"]:
                    if 1429 not in card.tags:
                        return card_data["battlegrounds"]["imageGold"]
                    else:
                        return card_data["battlegrounds"]["image"]
                else:
                    return card_data["image"]

    def get_ori(self, card):
        return "https://art.hearthstonejson.com/v1/orig/%s.png" % card.id

    def get_tags(self, card, args):
        lang = args["lang"]
        name = "名称：%s" % card.loc_name(lang)
        card_id = "\nid：%s" % card.id
        health = (card.durability
                  if card.type == CardType.WEAPON else card.health)
        cost = ("\n酒馆等级：%d星" % card.tags[GameTag.TECH_LEVEL]
                if args["is_bgs"] else "\n费用：%d费" % card.cost)
        stats = ("\n身材：%s/%s" %
                 (card.atk, health) if card.atk + health > 0 else "")
        races = get_card_races(card)
        race = ("\n种族：%s" % "/".join(translate(r) for r in races)
                if races else "")
        rarity = ("\n稀有度：%s" % translate(card.rarity)
                  if card.rarity != Rarity.INVALID else "")
        text = "\n" + card.loc_text(lang) if len(card.description) else ""
        flavor = ("\n卡牌趣文：" +
                  card.loc_flavor(lang) if len(card.flavortext) else "")
        card_class = ("\n职业：%s" % get_card_class(card))
        card_set = "\n扩展包：%s" % ("无" if type(card.card_set) is int else
                                 translate(card.card_set))
        collectible = "\n可否收藏：%s" % ("是" if card.collectible else "否")
        tags = (name + card_id + text + flavor + card_class + race + card_set +
                cost + stats + rarity + collectible)
        return tags
