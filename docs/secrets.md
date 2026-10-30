# GitHub Secrets 配置清单

配置位置：本仓库 `Settings → Secrets and variables → Actions → New repository secret`。
所有 key 只存 GitHub Secrets，**不进代码、不进 spec、不写任何文件**。
验证方式：配好后手动跑一次 `api-smoke` 工作流（Actions 页 → api-smoke → Run workflow），
它只报告每个 key「在/不在、通/不通」，不打印任何值。

## 现在就配（发音考卷盲测要用）

| Secret 名 | 值从哪来 | 用途 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI 平台的 API key | 写稿标注（GPT）＋回听转写（Whisper）＋TTS 候选 gpt-4o-mini-tts |
| `MINIMAX_API_KEY` | MiniMax 开放平台（platform.minimax.cn）账户管理 → 接口密钥 | TTS 主候选（speech-2.8-hd）；当前国内站接口只需 Bearer key，不需要 GroupId |

## 以后配（管线做到那一步再说）

| Secret 名 | 用途 |
|---|---|
| `PUSHPLUS_TOKEN` | 成品发布回执推送（与 tennislive 同一个 token 即可） |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | 若盲测后 Azure 进正式阵容，再配 |

## 注意

- OpenAI 的 TTS 模型（gpt-4o-mini-tts 等）官方已定 2027-01-06 关停：
  它在本仓只作盲测候选与写稿/回听工具，生产合成不硬绑它。
- MiniMax 在 tennislive 曾被全仓移除，但那是视频库范围内的决定；
  所有者 2026-10-30 已澄清：与本播客仓不冲突，本仓 MiniMax 仅限 TTS 合成，可正常使用。
