# Fund AI Advisor (Prompt Builder) — Design Spec

**Date:** 2026-05-22  
**Status:** Approved  
**Route:** `/advisor`  
**Nav label:** 基金 AI 助手

## Summary

Add a lightweight page that (1) builds a high-quality Chinese prompt from optional tags for users to paste into DeepSeek Chat (with web search enabled), and (2) parses pasted AI responses to extract 6-digit fund codes and link to in-catalog fund detail pages. No LLM or search API keys on the server.

## Goals

- Help users ask external AI: “What funds are worth watching recently?” with clear structure and constraints.
- Optional tags narrow scope (industry, fund type, style, horizon) without requiring selection.
- After AI responds elsewhere, paste back to resolve fund codes against the local `funds` table and link to `/funds/{code}` when present.

## Non-Goals

- Server-side DeepSeek or search API integration.
- Multi-turn chat, conversation history, or stored pasted content.
- Injecting MySQL dashboard metrics (sector flow, peer rank, etc.) into prompts.
- User accounts, favorites, or rate limiting in v1 (optional later for public ECS).

## User Flow

1. Open `/advisor`.
2. Optionally select tags (all optional).
3. Review generated prompt; click **复制提示词**.
4. Follow collapsed instructions: open https://chat.deepseek.com → enable **联网搜索** → paste and send.
5. Paste AI reply into textarea; click **解析基金代码**.
6. See list: code, name (if in DB), link to detail or “未在基金目录”.

## Page Layout

- **Section ① Tags:** chips/dropdowns for industry (multi), fund type, style, observation focus.
- **Section ② Prompt:** read-only preview, updates when tags change.
- **Section ③ Copy** + collapsible usage steps for DeepSeek web.
- **Section ④ Paste** textarea + parse button.
- **Section ⑤ Results** table/cards with `in_catalog` and `detail_url`.
- **Footer:** disclaimer — AI-generated, not investment advice.

Site-wide nav (dashboard, funds catalog, sectors, etc.) gains link: **基金 AI 助手** → `{url_prefix}/advisor`.

## Tag Dimensions

| Dimension | UI | Prompt clause (when set) |
|-----------|-----|---------------------------|
| Industry / theme | Multi-select chips | 重点关注行业/主题：{values} |
| Fund type | Multi or single select | 基金类型偏好：{values} |
| Style | 偏进攻 / 偏稳健 | 风险风格：{value} |
| Observation | 短期热点 / 中长期配置 | 观察周期倾向：{value} |

Preset chip values (v1, static in template or constants):

- Industries: 新能源, 医药, 科技, 消费, 红利, 军工, 半导体 (extensible list)
- Fund types: 股票型, 混合型, 指数型, 债券型, QDII
- Style: 偏进攻, 偏稳健
- Observation: 短期热点, 中长期配置

## Prompt Template (Server-Side)

Fixed instructions (always included):

- Role: 公募基金研究助手；**不构成投资建议**。
- Use **recent** public analysis (broker views, financial media depth, public fund report summaries).
- Structure: 2–4 sentences on sector/market logic, then **3–5** funds.
- Per fund: 6-digit code, full name, rationale, one-line risk.
- Cite checkable sources by title; **do not fabricate URLs**.
- Append tag clauses only for selected dimensions.

Default user intent embedded in prompt:

> 结合近期权威公开分析，推荐 3～5 只值得关注的公募基金，并说明推荐逻辑。

No MySQL metrics in prompt body.

## API

### `GET /api/advisor/prompt`

Query params (optional, repeated or comma-separated per implementation):

- `industries`, `fund_types`, `style`, `observation`

Response:

```json
{ "prompt": "..." }
```

### `POST /api/advisor/parse`

Request:

```json
{ "text": "<pasted AI response>" }
```

Response:

```json
{
  "items": [
    {
      "code": "000001",
      "name": "华夏成长混合",
      "in_catalog": true,
      "detail_url": "/funds/000001"
    },
    {
      "code": "999999",
      "name": null,
      "in_catalog": false,
      "detail_url": null
    }
  ]
}
```

- Extract `\b[0-9]{6}\b`, dedupe, preserve first-seen order.
- Batch `SELECT code, short_name AS name FROM funds WHERE code IN (...)`.
- `detail_url` must respect `url_prefix` from app config (same as other pages).

Errors:

- Empty `text` → 400 with message.
- No codes found → 200 with `items: []` and client shows friendly empty state.

## Implementation Modules

| Module | Responsibility |
|--------|----------------|
| `fund_platform/advisor_prompt.py` | Build prompt string from tag selections |
| `fund_platform/advisor_parse.py` | Regex extract + batch catalog lookup |
| `quant_trading/funds/app.py` | `GET /advisor`, `GET /api/advisor/prompt`, `POST /api/advisor/parse` |
| `quant_trading/funds/templates/advisor.html` | UI, copy button, fetch/parse JS |

Reuse: `fund_platform.queries` or new `get_funds_by_codes(conn, codes: list[str])` for batch lookup.

## Frontend Behavior

- Tag change → refresh prompt via API or client-side mirror of template (prefer API for single source of truth).
- `navigator.clipboard.writeText` for copy; fallback `select` + execCommand if needed.
- Parse: POST JSON, render results; link opens `/funds/{code}` in same tab.
- Loading/disabled states on parse button.

## Security & Privacy

- No third-party API keys.
- Pasted text not persisted in v1.
- Parse endpoint is stateless; optional future rate limit on ECS.

## Testing Checklist

- [ ] Prompt with no tags includes base instructions only.
- [ ] Each tag dimension appends correct Chinese clause.
- [ ] Copy works in modern browsers.
- [ ] Parse: two in-catalog codes + one unknown → correct `in_catalog` and URLs.
- [ ] Parse: empty paste → appropriate message.
- [ ] `url_prefix` prefix applied to `detail_url` and nav links.

## Approved Decisions (2026-05-22)

- Interaction: prompt builder only (not in-app LLM).
- Tags: optional (scheme 1).
- External analysis via user’s DeepSeek web + 联网搜索.
- Output expectation communicated in prompt: 3–5 funds with clear logic.
- Post-parse catalog linking: **yes** (option B).
- Route `/advisor`, nav **基金 AI 助手**.
