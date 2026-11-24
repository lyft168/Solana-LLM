<div align="center">

<img src="../../assets/logo.png" alt="inspectorai-solana-chat" width="760"/>

# inspectorai-solana-chat

**CLI headless + jembatan kompatibel-OpenAI untuk [Solana Confidential Chat](https://solana.ai/chat).**
Permintaan tersegel EHBP (HPKE), pengikatan atestasi TEE, streaming, tool call, siap 9router.

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-14F195.svg)](../../LICENSE)
[![Tests](https://img.shields.io/badge/tests-30%20lulus-14F195.svg)](../../tests/)
[![Crypto](https://img.shields.io/badge/crypto-HPKE%20%C2%B7%20X25519%20%C2%B7%20AES--256--GCM-9945FF.svg)](../protocol-ehbp.md)
[![OpenAI](https://img.shields.io/badge/API-kompatibel%20OpenAI-10A37F.svg)](../9router.md)
[![9router](https://img.shields.io/badge/9router-siap-ff6b00.svg)](../../examples/9router.json)
[![Telegram](https://img.shields.io/badge/komunitas-Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/inspectoraiofc)

[English](../../README.md) · **Bahasa Indonesia** · [中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md) · [العربية](README.ar.md)

</div>

---

## Apa itu solana.ai/chat?

Chat milik Solana menjalankan model di dalam **enclave rahasia** (Tinfoil TEE)
di perangkat keras Solana. Browser mengenkripsi prompt **langsung ke enclave**
memakai HPKE, enclave menjalankan model, dan balasan kembali terenkripsi
sehingga relay tidak pernah melihat isinya. Aplikasi web memakai format body
AEAD berchunk bernama **EHBP** — itu seluruh API-nya.

Repo ini adalah **klien headless**-nya: EHBP murni Python, parser atestasi,
plus server lokal `POST /v1/chat/completions` supaya 9router, Cline, Cursor,
Continue dan tool berbentuk OpenAI bisa memakainya.

## Model yang tersedia

Ada **lima** model, semuanya tersegel TEE. Pakai *public id* sebagai field
`model` di mana pun.

| Public ID | Key | Nama tampilan |
|---|---|---|
| `deepseek/deepseek-v4.1-flash:encrypted` | `deepseek-v4.1-flash` | DeepSeek V4.1 Flash *(default)* |
| `openai/gpt-oss-120b:encrypted` | `gpt-oss` | GPT-OSS 120B |
| `google/gemma-4-31b-it:encrypted` | `gemma-4-31b` | Gemma 4 31B |
| `z-ai/glm-5.3:encrypted` | `glm-5.3` | GLM 5.3 |
| `moonshotai/kimi-k3.1-pro:encrypted` | `kimi-k3.1-pro` | Kimi K3.1 Pro |

```bash
solana-chat models
```

## Soal kredit — jawaban jujur

`solana.ai/chat` **tidak punya pendaftaran, akun, kode promo, maupun saldo
kredit.** Satuannya adalah *pesan per sesi relay*, dibatasi `session_limit`
(per jam) dan `chat_message_limit` (per percakapan) terhadap kumpulan demo
bersama (`demo_exhausted`). Tidak ada endpoint `/credits` dan tidak ada angka
untuk "diklaim". Bukti lengkap + tabel kode error:
**[docs/quota.md](../quota.md)** (Inggris).

## Instalasi

```bash
git clone https://gitlab.com/inspectorai/inspectorai-solana-chat.git
cd inspectorai-solana-chat
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
solana-chat doctor
```

VPS sekali jalan (systemd unit, di-hardening, API key dibuat otomatis):

```bash
sudo REPO=https://gitlab.com/inspectorai/inspectorai-solana-chat.git bash deploy/install.sh
```

Docker:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:20129/v1/health
```

## Cara pakai

**CLI sekali tembak:**

```bash
solana-chat ask "jelaskan x402 dalam dua kalimat"
solana-chat ask -m kimi-k3.1-pro "tulis haiku soal enclave" --usage
solana-chat attest -m deepseek-v4.1-flash --json
```

**Jembatan OpenAI (yang diajak bicara 9router):**

```bash
export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
solana-chat serve --host 127.0.0.1 --port 20129

curl -s http://127.0.0.1:20129/v1/chat/completions \
  -H "Authorization: Bearer $SOLANA_CHAT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-v4.1-flash:encrypted",
       "messages":[{"role":"user","content":"PONG?"}]}'
```

**9router:**

```
Base URL  : http://127.0.0.1:20129/v1
API Key   : $SOLANA_CHAT_API_KEY
Type      : openai-compatible
Tool call : aktif
```

JSON provider: [`examples/9router.json`](../../examples/9router.json) ·
panduan: [docs/9router.md](../9router.md).

## Matriks kemampuan

| Fitur | CLI | Jembatan |
|---|---|---|
| chat completion | ✅ | ✅ |
| streaming (SSE) | — | ✅ |
| tool call / function calling | — | ✅ (shim parse JSON) |
| daftar model | ✅ | ✅ |
| inspeksi atestasi | ✅ | via `solana-chat attest` |
| cookie sesi tersimpan | ✅ | ✅ |
| vision / gambar | ❌ ditolak relay | ❌ |
| embedding / TTS / STT | ❌ | ❌ |

## Struktur

```
src/solana_chat/
  cli.py        models · ask · attest · serve · session · doctor
  client.py     session → attest → seal → complete
  hpke.py       EHBP: X25519 · HKDF-SHA256 · AES-256-GCM · framing
  server.py     jembatan kompatibel-OpenAI (SSE + tool call)
  session.py    cookie relay + memo atestasi (0600)
  catalog.py    tabel lima model
tests/          30 tes, termasuk vektor RFC 7748 / 5869
deploy/         unit systemd + installer
examples/       konfigurasi 9router, smoke test curl
```

Selengkapnya: [arsitektur](../architecture.md) ·
[format EHBP](../protocol-ehbp.md) · [keamanan](../security.md).

## Komunitas

- Telegram: **[t.me/inspectoraiofc](https://t.me/inspectoraiofc)**
- Issue: [gitlab.com/inspectorai/inspectorai-solana-chat](https://gitlab.com/inspectorai/inspectorai-solana-chat/-/issues)

## Lisensi

MIT — lihat [LICENSE](../../LICENSE).
