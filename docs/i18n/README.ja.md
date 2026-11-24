<div align="center">

<img src="../../assets/logo.png" alt="inspectorai-solana-chat" width="760"/>

# inspectorai-solana-chat

**[Solana 機密チャット](https://solana.ai/chat) 用のヘッドレス CLI と OpenAI 互換ブリッジ。**
EHBP(HPKE 封印)リクエスト、TEE アテステーション結合、ストリーミング、ツールコール、9router 対応。

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-14F195.svg)](../../LICENSE)
[![Tests](https://img.shields.io/badge/tests-30%20passed-14F195.svg)](../../tests/)
[![Crypto](https://img.shields.io/badge/crypto-HPKE%20%C2%B7%20X25519%20%C2%B7%20AES--256--GCM-9945FF.svg)](../protocol-ehbp.md)
[![OpenAI](https://img.shields.io/badge/API-OpenAI%20%E4%BA%92%E6%8F%9B-10A37F.svg)](../9router.md)
[![Telegram](https://img.shields.io/badge/community-Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/inspectoraiofc)

[English](../../README.md) · [Bahasa Indonesia](README.id.md) · [中文](README.zh-CN.md) · **日本語** · [Español](README.es.md) · [العربية](README.ar.md)

</div>

---

## solana.ai/chat とは

Solana のチャットは **機密実行環境**(Tinfoil TEE)の中でモデルを動かします。
ブラウザは HPKE でプロンプトを **enclave 宛に** 暗号化し、enclave がモデルを
実行、応答も暗号化されて戻るためリレーは平文を一切見ません。Web アプリが話す
のは **EHBP** と呼ばれるチャンク化 AEAD ボディ形式 — これが API のすべてです。

本リポジトリはその **ヘッドレスクライアント** です。純 Python の EHBP 実装、
アテステーション解析、そしてローカル `POST /v1/chat/completions` サーバーを
備え、9router・Cline・Cursor・Continue など OpenAI 形式のツールからそのまま
使えます。

## 利用可能なモデル

**5 つ** すべて TEE 封印済み。`model` フィールドには *public id* を指定します。

| Public ID | Key | 表示名 |
|---|---|---|
| `deepseek/deepseek-v4.1-flash:encrypted` | `deepseek-v4.1-flash` | DeepSeek V4.1 Flash *(既定)* |
| `openai/gpt-oss-120b:encrypted` | `gpt-oss` | GPT-OSS 120B |
| `google/gemma-4-31b-it:encrypted` | `gemma-4-31b` | Gemma 4 31B |
| `z-ai/glm-5.3:encrypted` | `glm-5.3` | GLM 5.3 |
| `moonshotai/kimi-k3.1-pro:encrypted` | `kimi-k3.1-pro` | Kimi K3.1 Pro |

```bash
solana-chat models
```

## クレジットについて — 正直な答え

`solana.ai/chat` には **登録・アカウント・プロモコード・クレジット残高は
ありません。** 単位は *リレーセッションあたりのメッセージ数* で、
`session_limit`(毎時)と `chat_message_limit`(会話あたり)で制限され、
共有デモプール(`demo_exhausted`)に縛られます。`/credits` エンドポイントも
「受け取る」数字も存在しません。根拠とエラーコード表:
**[docs/quota.md](../quota.md)**。

## インストール

```bash
git clone https://gitlab.com/inspectorai/inspectorai-solana-chat.git
cd inspectorai-solana-chat
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
solana-chat doctor
```

VPS ワンライナー(systemd、ハードニング、API キー自動生成):

```bash
sudo REPO=https://gitlab.com/inspectorai/inspectorai-solana-chat.git bash deploy/install.sh
```

Docker:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:20129/v1/health
```

## 使い方

```bash
solana-chat ask "x402 を二文で説明して"
solana-chat ask -m kimi-k3.1-pro "enclave の俳句を書いて" --usage
solana-chat attest -m deepseek-v4.1-flash --json

export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
solana-chat serve --host 127.0.0.1 --port 20129

curl -s http://127.0.0.1:20129/v1/chat/completions \
  -H "Authorization: Bearer $SOLANA_CHAT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-v4.1-flash:encrypted",
       "messages":[{"role":"user","content":"PONG?"}]}'
```

9router 設定:

```
Base URL  : http://127.0.0.1:20129/v1
API Key   : $SOLANA_CHAT_API_KEY
Type      : openai-compatible
ツールコール : 有効
```

## 機能対応表

| 機能 | CLI | ブリッジ |
|---|---|---|
| chat completion | ✅ | ✅ |
| ストリーミング(SSE) | — | ✅ |
| ツールコール | — | ✅(JSON 再解析シム) |
| モデル一覧 | ✅ | ✅ |
| アテステーション確認 | ✅ | `attest` 経由 |
| セッション cookie 永続化 | ✅ | ✅ |
| 画像入力 | ❌ リレーが拒否 | ❌ |
| 埋め込み / TTS / STT | ❌ | ❌ |

## 構成

```
src/solana_chat/   cli · client · hpke · server · session · catalog
tests/             30 テスト(RFC 7748 / 5869 ベクタ含む)
deploy/            systemd ユニット + インストーラ
examples/          9router 設定、curl スモークテスト
docs/              アーキテクチャ · プロトコル · クォータ · セキュリティ
```

## コミュニティ

- Telegram: **[t.me/inspectoraiofc](https://t.me/inspectoraiofc)**
- Issues: [gitlab.com/inspectorai/inspectorai-solana-chat](https://gitlab.com/inspectorai/inspectorai-solana-chat/-/issues)

## ライセンス

MIT — [LICENSE](../../LICENSE) を参照。
