<div align="center" dir="rtl">

<img src="../../assets/logo.png" alt="inspectorai-solana-chat" width="760"/>

# inspectorai-solana-chat

**واجهة سطر أوامر (CLI) بدون واجهة رسومية وجسر متوافق مع OpenAI لـ [محادثة سولانا السرية](https://solana.ai/chat).**
طلبات مُغلَفة بـ EHBP (HPKE)، ربط إثبات TEE، بثّ، استدعاء أدوات، جاهز لـ 9router.

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-14F195.svg)](../../LICENSE)
[![Tests](https://img.shields.io/badge/tests-20%20نجح-14F195.svg)](../../tests/)
[![Crypto](https://img.shields.io/badge/crypto-HPKE%20%C2%B7%20X25519%20%C2%B7%20AES--256--GCM-9945FF.svg)](../protocol-ehbp.md)
[![OpenAI](https://img.shields.io/badge/API-متوافق%20مع%20OpenAI-10A37F.svg)](../9router.md)
[![Telegram](https://img.shields.io/badge/المجتمع-Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/inspectoraiofc)

[English](../../README.md) · [Bahasa Indonesia](README.id.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md) · **العربية**

</div>

---

<div dir="rtl">

## ما هو solana.ai/chat؟

يشغّل محادثة سولانا النماذج داخل **بيئة تنفيذ سرّية** (Tinfoil TEE) على عتاد
سولانا. يشفّر المتصفح طلبك **مباشرةً إلى الـ enclave** باستخدام HPKE، فينفّذ
الـ enclave النموذج ويعود الرد مشفّرًا، وبذلك لا يرى الخادم الوسيط أي نص صريح.
تستخدم الواجهة صيغة جسم AEAD مقسّمة تُسمّى **EHBP** — وهذه هي الواجهة بأكملها.

هذا المستودع هو **العميل بلا واجهة** لتلك الواجهة: EHBP بلغة بايثون خالصة،
تحليل حزمة الإثبات، إضافةً إلى خادم محلي `POST /v1/chat/completions` كي تستخدمه
9router وCline وCursor وContinue وأي أداة بشكل OpenAI.

## النماذج المتاحة

**خمسة** نماذج، جميعها موقّعة داخل TEE. استخدم *public id* في حقل `model`.

| Public ID | Key | الاسم |
|---|---|---|
| `deepseek/deepseek-v4.1-flash:encrypted` | `deepseek-v4.1-flash` | DeepSeek V4.1 Flash *(افتراضي)* |
| `openai/gpt-oss-120b:encrypted` | `gpt-oss` | GPT-OSS 120B |
| `google/gemma-4-31b-it:encrypted` | `gemma-4-31b` | Gemma 4 31B |
| `z-ai/glm-5.3:encrypted` | `glm-5.3` | GLM 5.3 |
| `moonshotai/kimi-k3.1-pro:encrypted` | `kimi-k3.1-pro` | Kimi K3.1 Pro |

```bash
solana-chat models
```

## الرصيد — الإجابة الصادقة

لا يوجد في `solana.ai/chat` **تسجيل ولا حسابات ولا كود خصم ولا رصيد ائتماني.**
الوحدة هي *عدد الرسائل لكل جلسة وسيط*، محدودة بـ `session_limit` (كل ساعة)
و`chat_message_limit` (لكل محادثة) ضمن مخزون تجريبي مشترك (`demo_exhausted`).
لا يوجد مسار `/credits` ولا رقم لـ"مطالبته". الدليل الكامل وجدول رموز
الأخطاء في **[docs/quota.md](../quota.md)**.

## التثبيت

```bash
git clone https://gitlab.com/inspectorai/inspectorai-solana-chat.git
cd inspectorai-solana-chat
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
solana-chat doctor
```

تثبيت أمر واحد على VPS (systemd مع تقوية أمنية، مفتاح API يُولَّد تلقائيًا):

```bash
sudo REPO=https://gitlab.com/inspectorai/inspectorai-solana-chat.git bash deploy/install.sh
```

Docker:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:20129/v1/health
```

## الاستخدام

```bash
solana-chat ask "اشرح x402 في جملتين"
solana-chat ask -m kimi-k3.1-pro "اكتب هايكو عن الـ enclave" --usage
solana-chat attest -m deepseek-v4.1-flash --json

export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
solana-chat serve --host 127.0.0.1 --port 20129

curl -s http://127.0.0.1:20129/v1/chat/completions \
  -H "Authorization: Bearer $SOLANA_CHAT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-v4.1-flash:encrypted",
       "messages":[{"role":"user","content":"PONG?"}]}'
```

إعداد 9router:

```
Base URL  : http://127.0.0.1:20129/v1
API Key   : $SOLANA_CHAT_API_KEY
Type      : openai-compatible
Tool calls: مفعّل
```

## جدول القدرات

| الميزة | CLI | الجسر |
|---|---|---|
| إكمال المحادثة | ✅ | ✅ |
| البثّ (SSE) | — | ✅ |
| استدعاء الأدوات | — | ✅ (طبقة إعادة تحليل JSON) |
| قائمة النماذج | ✅ | ✅ |
| فحص الإثبات | ✅ | عبر `attest` |
| حفظ كوكي الجلسة | ✅ | ✅ |
| الصور / الرؤية | ❌ يرفضها الوسيط | ❌ |
| التضمينات / TTS / STT | ❌ | ❌ |

## البنية

```
src/solana_chat/   cli · client · hpke · server · session · catalog
tests/             30 اختبارًا، تشمل متجهات RFC 7748 / 5869
deploy/            وحدة systemd + مثبّت
examples/          إعداد 9router، اختبار curl سريع
docs/              المعمارية · البروتوكول · الحصة · الأمان
```

## المجتمع

- تلغرام: **[t.me/inspectoraiofc](https://t.me/inspectoraiofc)**
- المشكلات: [gitlab.com/inspectorai/inspectorai-solana-chat](https://gitlab.com/inspectorai/inspectorai-solana-chat/-/issues)

## الترخيص

MIT — راجع [LICENSE](../../LICENSE).

</div>
