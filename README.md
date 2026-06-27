# astrbot_plugin_hearthstone

> 炉石传说卡牌查询与卡组图片生成 AstrBot 插件。移植自 [ZelKnow/Hearthbot](https://github.com/ZelKnow/Hearthbot) 的核心逻辑，适配 AstrBot v4 插件 API。

## 当前状态

- **核心能力**：查卡、查原画、按种族/标签检索、酒馆战棋查卡、卡组代码渲染、自动识别 `AAE...` 卡组代码。
- **实测环境**：AstrBot Docker / AstrBot v4.25.x 可加载运行。
- **资源策略**：插件主仓库不内置约 120MB 的 `hs-card-tiles` 卡组条图资源；首次部署可用脚本下载，后续游戏更新可用管理员指令补缺图。
- **兼容说明**：HSReplay 卡组分类接口在部分网络下可能被 Cloudflare 拦截；失败时会自动降级为按职业命名，不影响卡牌查询与基础卡组渲染。

## 中文指令

推荐优先使用中文指令；旧英文指令仍保留兼容。

| 功能 | 推荐指令 | 示例 | 说明 |
| --- | --- | --- | --- |
| 查构筑卡牌 | `/查卡 <卡牌名/关键词> [语言]` | `/查卡 雷诺` | 只显示可收藏构筑卡，过滤冒险、皮肤、衍生牌等非正常候选 |
| 查原画 | `/原画 <卡牌名/关键词> [语言]` | `/原画 雷诺` | 与 `/查卡` 使用同一套可收藏构筑过滤；不会再混入冒险/皮肤候选 |
| 查构筑种族/标签 | `/查标签 <种族/标签> [语言]` | `/查标签 野兽` | 按种族/标签列出构筑可收藏卡牌 |
| 查酒馆卡牌 | `/查酒馆 <卡牌名/关键词> [语言]` | `/查酒馆 铜须` | 默认走酒馆战棋卡池 |
| 查酒馆种族/标签 | `/查酒馆标签 <种族/标签> [语言]` | `/查酒馆标签 鱼人` | 按种族/标签列出酒馆战棋卡牌 |
| 渲染卡组 | `/卡组 <AAE卡组代码> [卡组名]` | `/卡组 AAE... 我的卡组` | 把炉石卡组代码渲染成卡组图片 |
| 自动渲染卡组 | 直接发送 `AAE...` 卡组代码 | `AAECA...` | 消息中出现完整卡组代码时自动识别并渲染 |
| 更新条图资源 | `/更新资源 [前缀...] [limit=数量]` | `/更新资源 CATA EDR limit=50` | 管理员指令，只补缺失条图，不覆盖已有文件 |

### 兼容的旧指令/别名

| 中文入口 | 兼容别名 |
| --- | --- |
| `/查卡` | `/炉石查卡`、`/卡牌`、`/card`、`/c` |
| `/原画` | `/ori`、`/o`、`/art` |
| `/查标签` | `/炉石标签`、`/tag`、`/tags`、`/t` |
| `/查酒馆` | `/酒馆`、`/酒馆卡牌`、`/bgcard`、`/bgs` |
| `/查酒馆标签` | `/酒馆标签`、`/酒馆查标签`、`/酒馆tag`、`/bgtag`、`/bgstags` |
| `/卡组` | `/deck`、`/d` |
| `/更新资源` | `/更新炉石资源`、`/hs更新资源`、`/更新炉石卡图` |

### 多结果选择与翻页

查询命中多张卡牌时，插件会返回候选列表：

```text
查询到 12 张构筑卡牌，当前页数[1/2]
回复数字选择卡牌，回复 p2 翻页
\1：雷诺·杰克逊，6费中立随从，探险者协会
...
```

- 回复 `1`：选择第 1 张卡。
- 回复 `\1` 或 `/1`：同样选择第 1 张卡。
- 回复 `p2` / `page 2` / `第2页`：翻到第 2 页。
- 选择会话约 5 分钟过期；如果回复了无效内容，会自动清理本次会话，避免影响普通聊天。

### 语言参数

查卡、原画、标签类指令支持语言参数，可放在指令最后，例如：

```text
/查卡 Reno enUS
/原画 雷诺 zhCN
/查标签 Beast enUS
```

常用语言：`zhCN`、`enUS`、`zhTW`、`jaJP`、`koKR`、`frFR`、`deDE`、`esES`、`esMX`、`itIT`、`plPL`、`ptBR`、`ruRU`、`thTH`。

## 安装教学

### 1. 放入 AstrBot 插件目录

在宿主机执行：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/Mer3y1338/astrbot_plugin_hearthstone.git
cd astrbot_plugin_hearthstone
```

### 2. 下载卡组条图资源（推荐）

`/卡组` 渲染需要 HearthSim 的卡牌条图资源，约 120MB。为了避免插件仓库过大，资源不直接放进 Git。

```bash
bash scripts/install_assets.sh
```

如果暂时不下载资源：

- `/查卡`、`/原画`、`/查标签` 仍可用。
- `/卡组` 可能提示缺少 `hs-card-tiles/Tiles` 或出现部分条图缺失。

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

## 配置教学

配置项由 `_conf_schema.json` 暴露，在 AstrBot WebUI 的插件设置里填写即可。

### 在 WebUI 中配置

1. 打开 AstrBot WebUI。
2. 进入「插件管理」。
3. 找到 `astrbot_plugin_hearthstone`。
4. 点击插件设置/配置。
5. 按下面表格填写配置。
6. 保存配置后重载插件或重启 AstrBot。

### 配置项说明

| 配置项 | 默认值 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| `blizz_id` | 空 | 否 | Blizzard API Client ID。不填时使用 HearthstoneJSON 图源，正常查卡/原画一般不需要填 |
| `blizz_sec` | 空 | 否 | Blizzard API Client Secret。只有你想走 Blizzard 官方 API 图源时才需要 |
| `max_response` | `8` | 否 | 搜索结果每页最多显示数量。建议 6-10，太大会刷屏 |
| `resource_proxy` | 空 | 否 | `/更新资源` 下载条图时使用的代理地址，例如 `http://<proxy-host>:<port>`；留空则直连 |

### 推荐配置

普通部署直接保持默认即可：

```json
{
  "blizz_id": "",
  "blizz_sec": "",
  "max_response": 8,
  "resource_proxy": ""
}
```

如果服务器访问 `art.hearthstonejson.com` 不稳定，可以只给资源更新配置代理：

```json
{
  "resource_proxy": "http://<proxy-host>:<port>"
}
```

> 注意：不要把真实代理地址、账号密码或 Token 提交到公开仓库。代理只填在 AstrBot 插件设置里。

## 资源更新教学

当炉石更新后，如果 `/卡组` 渲染提示缺少新系列条图，可以在聊天里用管理员指令补资源。

### 查看帮助

```text
/更新资源 帮助
```

### 更新全部缺失条图

```text
/更新资源
```

默认范围：可收藏构筑卡 + 酒馆战棋卡。插件只会新增本地缺失的图片，不会覆盖已有图片。

### 只更新指定前缀

```text
/更新资源 CATA EDR BG31
```

适合只补某几个新系列，速度更快。

### 小规模测试

```text
/更新资源 CATA limit=50
```

只下载前 50 张缺失图，确认网络没问题后再去掉 `limit=` 跑完整更新。

## 常见问题

### `/原画` 为什么以前会出现冒险、皮肤？

旧版 `/原画` 没有启用构筑可收藏过滤，所以搜索同名角色时可能混入英雄皮肤、冒险卡、不可收藏衍生牌等候选。新版 `/原画` 已和 `/查卡` 一样启用可收藏构筑过滤。

### `/卡组` 生成失败怎么办？

先确认三件事：

1. 卡组代码是否完整，以 `AAE` 开头，中间不要被空格截断。
2. 是否已经下载 `hs-card-tiles/Tiles` 条图资源。
3. 游戏更新后是否需要执行 `/更新资源` 补新卡条图。

### 图片发送失败怎么办？

插件会先下载远程图片，再用 AstrBot 图片组件发送 bytes，避免 QQ/NapCat 直接转发远程 URL 失败。如果仍失败，优先检查服务器是否能访问 HearthstoneJSON 图片域名。

## 给 Agent 的部署 Prompt

如果你是 Agent，要把这个插件部署到一台已有 AstrBot Docker 的服务器，请按下面做：

```text
目标：部署 astrbot_plugin_hearthstone 到 AstrBot 容器。
要求：最小改动；不要覆盖用户现有 AstrBot 配置；真实验证插件加载。
步骤：
1. 检查 `sudo docker ps` 中是否存在并运行 `astrbot` 容器。
2. 在宿主机 `/AstrBot/data/plugins/` 下 clone `https://github.com/Mer3y1338/astrbot_plugin_hearthstone.git`。
3. 进入插件目录执行 `bash scripts/install_assets.sh` 下载 `hs-card-tiles`；如果网络失败要如实报告，不许伪造成功。
4. 执行 `sudo docker exec astrbot python3 -m pip install -r /AstrBot/data/plugins/astrbot_plugin_hearthstone/requirements.txt`。
5. 执行 `sudo docker restart astrbot`。
6. 用 `docker inspect` 获取本次 StartedAt，再用 `sudo docker logs --since "$StartedAt" astrbot` 检查：
   - 必须出现 `Plugin astrbot_plugin_hearthstone (1.0.0)`
   - 不得出现 `插件 astrbot_plugin_hearthstone 载入失败`
   - 不得出现 `KeyError` 或 `TypeError`
7. 用 `/查卡 雷诺`、`/原画 雷诺`、`/卡组 <有效AAE卡组代码>` 做真实功能验证。
8. 最终报告真实命令结果和任何降级情况，例如 HSReplay 403 fallback。
```

## License

AGPL-3.0。核心逻辑来自 [ZelKnow/Hearthbot](https://github.com/ZelKnow/Hearthbot)。
