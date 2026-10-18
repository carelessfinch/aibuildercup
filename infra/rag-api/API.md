# Literature RAG API: guide for the frontend

Base URL: the Cloud Run URL of the `rag-api` service (e.g. `https://rag-api-xxxxx.a.run.app`). Interactive docs with "Try it out" buttons are at `/docs`, and the machine-readable schema at `/openapi.json` (you can generate a TypeScript client from it).

## Login and authorization

`POST /v1/auth/login` exchanges a demo username/password for a 12-hour token. Send that token on every protected call as `Authorization: Bearer <token>`. `X-Service-Key: <service-key>` is reserved for server-to-server calls from research-api; never put this key in the browser bundle.

`GET /health` (and its Cloud Run-safe `/healthz` alias) is open. `POST /v1/auth/login` is open. Every other `/v1` route, including `GET /v1/auth/me`, requires authorization. When `AUTH_SECRET` is unset for local development, protected routes are open and the API logs a loud warning; deployed services always set the secret.

Login requests are limited to 5 attempts per minute per IP. A wrong username and a wrong password return the same `401` message. Passwords are PBKDF2-SHA256 hashes from Secret Manager; the token payload is base64url JSON `{sub, iat, exp}` signed with HMAC-SHA256, and `exp` is `iat + 43,200` seconds. The same token also verifies on research-api.

```http
POST /v1/auth/login
{"username": "demo-user", "password": "..."}
```
```json
{"token": "...", "username": "demo-user", "expires_at": 1792273827}
```

`GET /v1/auth/me` with the bearer token returns `{"username": "demo-user"}`. CORS is controlled by the backend's `CORS_ORIGINS` setting.

## Endpoints

| Method and path | What it's for | Uses Gemini? |
|---|---|---|
| `GET /health` (alias `/healthz`, which Cloud Run blocks) | Is the service up; how many passages; `search_mode` should be `hybrid` | no |
| `POST /v1/auth/login` | Exchange demo credentials for a bearer token | no |
| `GET /v1/auth/me` | Confirm the signed-in username | no |
| `GET /v1/agents` | The agents you can talk to and the model name | no |
| `GET /v1/sources` | The 10 indexed books and papers (for a filter dropdown) | no |
| `POST /v1/search` | Direct literature search, returns passages with citations | no |
| `GET /v1/sources/{source_id}/pages?first=N&last=M` | Full text of up to 4 pages (to open a citation) | no |
| `POST /v1/chat` | Ask an agent; returns when the answer is complete | yes |
| `POST /v1/chat/stream` | Same, streamed live (tool calls, then the answer as it's written) | yes |
| `GET /v1/sessions/{session_id}` | Conversation so far, to restore a chat after reload | no |
| `DELETE /v1/sessions/{session_id}` | Forget a conversation | no |

Errors come back as `{"detail": "..."}` with status 400/404 (bad input), 401 (missing/invalid token), 413 (message over 4,000 characters), 429 (rate limit: show the message to the user) or 502 (the agent or Gemini failed).

## Agents

- `literature_assistant` (default): answers plasma physics and etching questions with citations.
- `professor_reviewer`: paste a simulation setup or result; it checks it against the literature and replies with `VERDICT: PASS / REVISE / ESCALATE`, a summary, one line per rubric check, and requested changes.

Both agents share sessions, so a user can ask the assistant something and then send the same conversation to the Professor by reusing the `session_id` with `"agent": "professor_reviewer"`.

## Search

```http
POST /v1/search
Authorization: Bearer <token>
{"query": "electron temperature in a low-pressure ICP", "top_k": 5, "source_ids": null, "kind": null}
```
`kind` is `textbook`, `paper` or `vendor_model`. Response:
```json
{"status": "success", "mode": "hybrid", "query": "...",
 "results": [{"citation": "Lieberman & Lichtenberg (2005). Principles of ... p. 334, PDF p. 371.",
              "source_id": "lieberman2005", "kind": "textbook", "section": "Chapter 10 > 10.2 ...",
              "pdf_pages": [371, 371], "printed_pages": ["334", "334"], "score": 0.03, "text": "..."}]}
```

## Chat (one response)

```http
POST /v1/chat
Authorization: Bearer <token>
{"message": "Why is Te nearly independent of power in a global model?",
 "agent": "literature_assistant", "session_id": null}
```
The user ID is the token's `sub` (the signed-in username); the API does not trust a user ID from the request body or session query string. Leave `session_id` null for a new conversation and send back the one you receive to continue it. Response:
```json
{"session_id": "9b1e...", "agent": "literature_assistant",
 "answer": "Te is set by particle balance ... [Lieberman & Lichtenberg (2005). ... PDF p. 371.]",
 "citations": [{"citation": "...", "source_id": "lieberman2005", "pdf_pages": [371, 371], "section": "...", "snippet": "first 300 characters"}],
 "tool_calls": [{"name": "search_literature", "args": {"query": "...", "top_k": 5}}],
 "model": "gemini-3.8-flash", "elapsed_s": 6.4}
```
Citations appear in the answer text in square brackets, exactly matching a `citation` string, so you can turn them into clickable chips that open `/v1/sources/{source_id}/pages?first={pdf_pages[0]}`.

## Chat (streaming)

Same request body, `POST /v1/chat/stream`. The response is Server-Sent Events, in this order:

| event | data |
|---|---|
| `session` | `{"session_id", "agent", "model"}` |
| `tool_call` | `{"name", "args"}`: the agent is searching or reading pages (show "Searching: ...") |
| `tool_result` | `{"name", "status", "citations": [...]}`: new sources found |
| `text` | `{"delta": "..."}`: the next piece of the answer; append it |
| `done` | `{"session_id", "answer", "citations", "tool_calls", "elapsed_s"}`: the final answer; replace the streamed text with it |
| `error` | `{"message"}` |

A tool call and its result can repeat several times before any text. Browser `EventSource` only does GET, so read the stream with `fetch`:

```js
async function chatStream(body, on) {
  const res = await fetch(`${API}/v1/chat/stream`, {
    method: "POST",
    headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`},
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += value;
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      const event = block.match(/^event: (.*)$/m)?.[1];
      const data = JSON.parse(block.match(/^data: (.*)$/m)?.[1] ?? "null");
      on(event, data);   // e.g. on("text", {delta}) -> append to the message bubble
    }
  }
}
```

## Things to know

- Sessions are kept in the service's memory: they survive while the service is warm and are lost when it scales to zero or redeploys. If `GET /v1/sessions/...` returns 404, start a new chat.
- Answers take several seconds (the agent searches first), so show the tool-call steps while waiting; that's also the most interesting part of the demo.
- The first request after the service has been idle waits while it starts and loads the index (not measured yet; expect tens of seconds). Show a loading state.
- Rate limits per IP: 10 chat messages, 60 searches and 5 login attempts a minute, plus a daily cap on all chat messages.
