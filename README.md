# astrbot_plugin_hearthstone

> 炉石传说卡牌查询与卡组图片生成 AstrBot 插件。移植自 [ZelKnow/Hearthbot](https://github.com/ZelKnow/Hearthbot) 的核心逻辑，适配 AstrBot v4 插件 API。

## 来源与实测状态

- **来源**：核心卡牌查询、卡组渲染、卡组分类逻辑来自 [ZelKnow/Hearthbot](https://github.com/ZelKnow/Hearthbot)，原项目基于 Nonebot2；本仓库将其移植为 AstrBot 插件，并保留 AGPL-3.0 许可证要求。
- **移植说明**：Nonebot2 命令入口已改写为 AstrBot `@filter.command()` / `@filter.regex()`；核心 `card_handler.py`、`deck_handler.py`、`archetype.py` 仅做 AstrBot 兼容与数据兼容性修复。
- **国内服务器实测**：已在国内服务器上的 AstrBot Docker 容器（AstrBot v4.25.5）中完成加载测试，确认插件可用；`/card` 卡牌查询链路已用“雷诺”做冒烟测试。HSReplay 卡组分类接口在当前网络下可能被 Cloudflare 403 拦截，插件会自动降级为按职业命名，不影响卡牌查询与基础卡组渲染。

## 功能

- `/card <卡牌名>`：查询卡牌并返回卡牌图片
- `/card <卡牌名> bg`：查询酒馆战棋卡牌
- `/tags <卡牌名>`：查看卡牌标签信息
- `/ori <卡牌名>`：查看卡牌原画
- `/deck <AAE卡组代码> [卡组名]`：把卡组代码渲染成卡组图片
- 自动识别消息中的 `AAE...` 卡组代码并渲染

## 安装

### 1. 放入 AstrBot 插件目录

```bash
cd /AstrBot/data/plugins
git clone https://github.com/Mer3y1338/astrbot_plugin_hearthstone.git
cd astrbot_plugin_hearthstone
```

### 2. 下载卡组图片资源（可选但推荐）

`/deck` 渲染需要 HearthSim 的卡牌条图资源，约 120MB。为了避免插件仓库过大，资源不直接放进 Git。

```bash
bash scripts/install_assets.sh
```

如果不下载资源，`/card`、`/tags`、`/ori` 仍可用；`/deck` 会提示缺少 `hs-card-tiles/Tiles`。

### 3. 安装依赖并重启 AstrBot

```bash
sudo docker exec astrbot python3 -m pip install -r /AstrBot/data/plugins/astrbot_plugin_hearthstone/requirements.txt
sudo docker restart astrbot
sudo docker logs astrbot --tail 200 | grep astrbot_plugin_hearthstone
```

成功标志类似：

```text
Plugin astrbot_plugin_hearthstone (1.0.0) by Mer3y1338
```

## 配置

`_conf_schema.json` 暴露了三个配置项：

| 配置 | 说明 |
| --- | --- |
| `blizz_id` | Blizzard API Client ID，可选。不填时使用 hearthstonejson 图源 |
| `blizz_sec` | Blizzard API Client Secret，可选 |
| `max_response` | 搜索结果每页最多返回数量，默认 8 |

## 说明

- HSReplay 卡组分类接口可能被 Cloudflare 拦截；失败时会自动降级为按职业命名，不影响卡牌查询和卡组图片生成。
- 本插件保留 AGPL-3.0 许可证要求；如果你在网络服务中运行修改版，需要按 AGPL 要求提供对应源代码。
- `hs-alter-name/alter.json` 是卡牌别名数据，体积很小，已随仓库附带。

## 给 Agent 的部署 Prompt

如果你是 Agent，要把这个插件部署到一台已有 AstrBot Docker 的服务器，请按下面做：

```text
目标：部署 astrbot_plugin_hearthstone 到 AstrBot 容器。
要求：最小改动；不要覆盖用户现有 AstrBot 配置；真实验证插件加载。
步骤：
1. 检查 `sudo docker ps` 中是否存在并运行 `astrbot` 容器。
2. 在宿主机 `/AstrBot/data/plugins/` 下 clone `https://github.com/Mer3y1338/astrbot_plugin_hearthstone.git`。
3. 进入插件目录执行 `bash scripts/install_assets.sh` 下载 `hs-card-tiles`，如果网络失败要如实报告；不许伪造成功。
4. 执行 `sudo docker exec astrbot python3 -m pip install -r /AstrBot/data/plugins/astrbot_plugin_hearthstone/requirements.txt`。
5. 执行 `sudo docker restart astrbot`。
6. 用 `docker inspect` 获取本次 StartedAt，再用 `sudo docker logs --since "$StartedAt" astrbot` 检查：
   - 必须出现 `Plugin astrbot_plugin_hearthstone (1.0.0)`
   - 不得出现 `插件 astrbot_plugin_hearthstone 载入失败`
   - 不得出现 `KeyError` 或 `TypeError`
7. 最终报告真实命令结果和任何降级情况（例如 HSReplay 403 fallback）。
```

## License

AGPL-3.0。核心逻辑来自 [ZelKnow/Hearthbot](https://github.com/ZelKnow/Hearthbot)。
