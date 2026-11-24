<div align="center">

<img src="../../assets/logo.png" alt="inspectorai-solana-chat" width="760"/>

# inspectorai-solana-chat

**CLI sin interfaz + puente compatible con OpenAI para [Solana Confidential Chat](https://solana.ai/chat).**
Peticiones selladas con EHBP (HPKE), vinculación de atestación TEE, streaming, tool calls, listo para 9router.

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-14F195.svg)](../../LICENSE)
[![Tests](https://img.shields.io/badge/tests-30%20ok-14F195.svg)](../../tests/)
[![Crypto](https://img.shields.io/badge/crypto-HPKE%20%C2%B7%20X25519%20%C2%B7%20AES--256--GCM-9945FF.svg)](../protocol-ehbp.md)
[![OpenAI](https://img.shields.io/badge/API-compatible%20OpenAI-10A37F.svg)](../9router.md)
[![Telegram](https://img.shields.io/badge/comunidad-Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/inspectoraiofc)

[English](../../README.md) · [Bahasa Indonesia](README.id.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md) · **Español** · [العربية](README.ar.md)

</div>

---

## ¿Qué es solana.ai/chat?

El chat de Solana ejecuta modelos dentro de un **enclave confidencial**
(Tinfoil TEE) en hardware Solana. El navegador cifra tu prompt **directamente
al enclave** con HPKE, el enclave ejecuta el modelo y la respuesta vuelve
cifrada, de modo que el relé nunca ve nada en claro. La web habla un formato
de cuerpo AEAD por bloques llamado **EHBP**: eso es toda la API.

Este repositorio es el **cliente sin interfaz**: EHBP en Python puro, análisis
de atestación y un servidor local `POST /v1/chat/completions` para que
9router, Cline, Cursor, Continue y cualquier herramienta con forma de OpenAI
lo usen directamente.

## Modelos disponibles

Hay **cinco**, todos sellados por TEE. Usa el *public id* como campo `model`.

| Public ID | Key | Nombre |
|---|---|---|
| `deepseek/deepseek-v4.1-flash:encrypted` | `deepseek-v4.1-flash` | DeepSeek V4.1 Flash *(por defecto)* |
| `openai/gpt-oss-120b:encrypted` | `gpt-oss` | GPT-OSS 120B |
| `google/gemma-4-31b-it:encrypted` | `gemma-4-31b` | Gemma 4 31B |
| `z-ai/glm-5.3:encrypted` | `glm-5.3` | GLM 5.3 |
| `moonshotai/kimi-k3.1-pro:encrypted` | `kimi-k3.1-pro` | Kimi K3.1 Pro |

```bash
solana-chat models
```

## Créditos: la respuesta honesta

`solana.ai/chat` **no tiene registro, cuentas, código promocional ni saldo de
créditos.** La unidad es *mensajes por sesión de relé*, limitados por
`session_limit` (por hora) y `chat_message_limit` (por conversación) contra un
pool de demo compartido (`demo_exhausted`). No existe `/credits` ni ningún
número que "reclamar". Evidencia completa y tabla de códigos de error:
**[docs/quota.md](../quota.md)**.

## Instalación

```bash
git clone https://gitlab.com/inspectorai/inspectorai-solana-chat.git
cd inspectorai-solana-chat
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
solana-chat doctor
```

VPS en una línea (systemd endurecido, clave API generada):

```bash
sudo REPO=https://gitlab.com/inspectorai/inspectorai-solana-chat.git bash deploy/install.sh
```

Docker:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:20129/v1/health
```

## Uso

```bash
solana-chat ask "explica x402 en dos frases"
solana-chat ask -m kimi-k3.1-pro "escribe un haiku sobre enclaves" --usage
solana-chat attest -m deepseek-v4.1-flash --json

export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
solana-chat serve --host 127.0.0.1 --port 20129

curl -s http://127.0.0.1:20129/v1/chat/completions \
  -H "Authorization: Bearer $SOLANA_CHAT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-v4.1-flash:encrypted",
       "messages":[{"role":"user","content":"PONG?"}]}'
```

9router:

```
Base URL  : http://127.0.0.1:20129/v1
API Key   : $SOLANA_CHAT_API_KEY
Type      : openai-compatible
Tool calls: activado
```

## Matriz de capacidades

| Función | CLI | Puente |
|---|---|---|
| chat completion | ✅ | ✅ |
| streaming (SSE) | — | ✅ |
| tool calls | — | ✅ (shim de re-parseo JSON) |
| lista de modelos | ✅ | ✅ |
| inspección de atestación | ✅ | vía `attest` |
| cookie de sesión persistente | ✅ | ✅ |
| visión / imágenes | ❌ el relé lo rechaza | ❌ |
| embeddings / TTS / STT | ❌ | ❌ |

## Estructura

```
src/solana_chat/   cli · client · hpke · server · session · catalog
tests/             30 pruebas, vectores RFC 7748 / 5869 incluidos
deploy/            unidad systemd + instalador
examples/          configuración 9router, smoke test curl
docs/              arquitectura · protocolo · cuota · seguridad
```

## Comunidad

- Telegram: **[t.me/inspectoraiofc](https://t.me/inspectoraiofc)**
- Issues: [gitlab.com/inspectorai/inspectorai-solana-chat](https://gitlab.com/inspectorai/inspectorai-solana-chat/-/issues)

## Licencia

MIT — ver [LICENSE](../../LICENSE).
