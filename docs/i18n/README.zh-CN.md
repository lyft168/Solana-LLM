<div align="center">

<img src="../../assets/logo.png" alt="inspectorai-solana-chat" width="760"/>

# inspectorai-solana-chat

**面向 [Solana 机密聊天](https://solana.ai/chat) 的无头 CLI 与 OpenAI 兼容桥。**
EHBP(HPKE 密封)请求、TEE 证明绑定、流式输出、工具调用,可直接接入 9router。

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-14F195.svg)](../../LICENSE)
[![Tests](https://img.shields.io/badge/tests-20%20通过-14F195.svg)](../../tests/)
[![Crypto](https://img.shields.io/badge/crypto-HPKE%20%C2%B7%20X25519%20%C2%B7%20AES--256--GCM-9945FF.svg)](../protocol-ehbp.md)
[![OpenAI](https://img.shields.io/badge/API-兼容%20OpenAI-10A37F.svg)](../9router.md)
[![Telegram](https://img.shields.io/badge/社区-Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/inspectoraiofc)

[English](../../README.md) · [Bahasa Indonesia](README.id.md) · **中文** · [日本語](README.ja.md) · [Español](README.es.md) · [العربية](README.ar.md)

</div>

---

## solana.ai/chat 是什么

Solana 的聊天功能在 **机密执行环境**(Tinfoil TEE)中运行模型。浏览器用
HPKE 把提示词 **直接加密给 enclave**,模型在其中运行,回复同样加密返回,
中继服务器看不到任何明文。网页使用一种名为 **EHBP** 的分块 AEAD 报文格式——
这就是它全部的 API。

本仓库是该协议的 **无头客户端**:纯 Python 实现 EHBP、解析证明包,并附带本地
`POST /v1/chat/completions` 服务器,让 9router、Cline、Cursor、Continue 以及
任何 OpenAI 形态的工具都能直接使用。

## 可用模型

共 **五个**,全部由 TEE 密封。任何地方的 `model` 字段都用 *public id*。

| Public ID | Key | 名称 |
|---|---|---|
| `deepseek/deepseek-v4.1-flash:encrypted` | `deepseek-v4.1-flash` | DeepSeek V4.1 Flash *(默认)* |
| `openai/gpt-oss-120b:encrypted` | `gpt-oss` | GPT-OSS 120B |
| `google/gemma-4-31b-it:encrypted` | `gemma-4-31b` | Gemma 4 31B |
| `z-ai/glm-5.3:encrypted` | `glm-5.3` | GLM 5.3 |
| `moonshotai/kimi-k3.1-pro:encrypted` | `kimi-k3.1-pro` | Kimi K3.1 Pro |

```bash
solana-chat models
```

## 额度 —— 诚实的回答

`solana.ai/chat` **没有注册、没有账号、没有优惠码、没有积分余额。**
计量单位是 *每个中继会话的消息数*,受 `session_limit`(每小时)与
`chat_message_limit`(每个会话)限制,共享同一演示池(`demo_exhausted`)。
没有 `/credits` 端点,也没有可以"领取"的数字。完整证据与错误码表见
**[docs/quota.md](../quota.md)**。

## 安装

```bash
git clone https://gitlab.com/inspectorai/inspectorai-solana-chat.git
cd inspectorai-solana-chat
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
solana-chat doctor
```

VPS 一键安装(systemd、自动加固、自动生成 API key):

```bash
sudo REPO=https://gitlab.com/inspectorai/inspectorai-solana-chat.git bash deploy/install.sh
```

Docker:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:20129/v1/health
```

## 使用

```bash
solana-chat ask "用两句话解释 x402"
solana-chat ask -m kimi-k3.1-pro "写一首关于 enclave 的俳句" --usage
solana-chat attest -m deepseek-v4.1-flash --json

export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
solana-chat serve --host 127.0.0.1 --port 20129

curl -s http://127.0.0.1:20129/v1/chat/completions \
  -H "Authorization: Bearer $SOLANA_CHAT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-v4.1-flash:encrypted",
       "messages":[{"role":"user","content":"PONG?"}]}'
```

9router 配置:

```
Base URL  : http://127.0.0.1:20129/v1
API Key   : $SOLANA_CHAT_API_KEY
Type      : openai-compatible
工具调用   : 开启
```

## 能力对照

| 功能 | CLI | 桥 |
|---|---|---|
| chat completion | ✅ | ✅ |
| 流式(SSE) | — | ✅ |
| 工具调用 | — | ✅(JSON 重解析适配) |
| 模型列表 | ✅ | ✅ |
| 证明包查看 | ✅ | 通过 `attest` |
| 会话 cookie 持久化 | ✅ | ✅ |
| 图像输入 | ❌ 中继拒绝 | ❌ |
| 向量 / TTS / STT | ❌ | ❌ |

## 目录结构

```
src/solana_chat/   cli · client · hpke · server · session · catalog
tests/             30 项测试,含 RFC 7748 / 5869 向量
deploy/            systemd 单元 + 安装脚本
examples/          9router 配置、curl 冒烟测试
docs/              架构 · 协议 · 额度 · 安全 · 9router
```

## 社区

- Telegram: **[t.me/inspectoraiofc](https://t.me/inspectoraiofc)**
- 问题反馈: [gitlab.com/inspectorai/inspectorai-solana-chat](https://gitlab.com/inspectorai/inspectorai-solana-chat/-/issues)

## 许可证

MIT — 见 [LICENSE](../../LICENSE)。
