import re
import os
import agent

filepath = os.path.join(os.path.dirname(agent.__file__), "gemini_native_adapter.py")

with open(filepath, "r") as f:
    content = f.read()

target = """    def _stream_completion(self, *, model: str, request: Dict[str, Any], timeout: Any = None) -> Iterator[_GeminiStreamChunk]:
        url = f"{self.base_url}/models/{model}:streamGenerateContent?alt=sse"
        stream_headers = dict(self._headers())
        stream_headers["Accept"] = "text/event-stream"

        def _generator() -> Iterator[_GeminiStreamChunk]:
            try:
                with self._http.stream("POST", url, json=request, headers=stream_headers, timeout=timeout) as response:
                    if response.status_code != 200:
                        response.read()
                        raise gemini_http_error(response)
                    tool_call_indices: Dict[str, Dict[str, Any]] = {}
                    for event in _iter_sse_events(response):
                        for chunk in translate_stream_event(event, model, tool_call_indices):
                            yield chunk
            except httpx.HTTPError as exc:
                raise GeminiAPIError(
                    f"Gemini streaming request failed: {exc}",
                    code="gemini_stream_error",
                ) from exc

        return _generator()"""

replacement = """    def _stream_completion(self, *, model: str, request: Dict[str, Any], timeout: Any = None) -> Iterator[_GeminiStreamChunk]:
        url = f"{self.base_url}/models/{model}:generateContent"
        def _generator() -> Iterator[_GeminiStreamChunk]:
            try:
                response = self._http.post(url, json=request, headers=self._headers(), timeout=timeout)
                if response.status_code != 200:
                    raise gemini_http_error(response)
                payload = response.json()
                candidates = payload.get("candidates") or []
                if not candidates:
                    return
                cand = candidates[0] if isinstance(candidates[0], dict) else {}
                parts = ((cand.get("content") or {}).get("parts") or []) if isinstance(cand, dict) else []
                
                reasoning_pieces = [p["text"] for p in parts if isinstance(p, dict) and p.get("thought") is True and isinstance(p.get("text"), str)]
                if reasoning_pieces:
                    yield _make_stream_chunk(model=model, reasoning="".join(reasoning_pieces))
                
                text_pieces = [p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str) and p.get("text") and p.get("thought") is not True]
                if text_pieces:
                    yield _make_stream_chunk(model=model, content="".join(text_pieces))
                
                tool_call_index = 0
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    fc = part.get("functionCall")
                    if isinstance(fc, dict) and fc.get("name"):
                        name = str(fc["name"])
                        try:
                            args_str = json.dumps(fc.get("args") or {}, ensure_ascii=False)
                        except (TypeError, ValueError):
                            args_str = "{}"
                        yield _make_stream_chunk(
                            model=model,
                            tool_call_delta={
                                "index": tool_call_index,
                                "id": f"call_{uuid.uuid4().hex[:12]}",
                                "name": name,
                                "arguments": args_str,
                                "extra_content": _tool_call_extra_from_part(part),
                            },
                        )
                        tool_call_index += 1
                
                finish_reason_raw = str(cand.get("finishReason") or "")
                mapped = "tool_calls" if tool_call_index > 0 else _map_gemini_finish_reason(finish_reason_raw)
                finish_chunk = _make_stream_chunk(model=model, finish_reason=mapped)
                usage_meta = payload.get("usageMetadata") or {}
                if usage_meta:
                    finish_chunk.usage = SimpleNamespace(
                        prompt_tokens=int(usage_meta.get("promptTokenCount") or 0),
                        completion_tokens=int(usage_meta.get("candidatesTokenCount") or 0),
                        total_tokens=int(usage_meta.get("totalTokenCount") or 0),
                        prompt_tokens_details=SimpleNamespace(
                            cached_tokens=int(usage_meta.get("cachedContentTokenCount") or 0),
                        ),
                    )
                yield finish_chunk
            except Exception as exc:
                raise GeminiAPIError(
                    f"Gemini mock streaming request failed: {exc}",
                    code="gemini_stream_error",
                ) from exc
        return _generator()"""

if target in content:
    content = content.replace(target, replacement)
    with open(filepath, "w") as f:
        f.write(content)
    print("SUCCESS: gemini_native_adapter.py patched successfully!")
else:
    print("WARNING: Target code not found in gemini_native_adapter.py. Check file content/indentation.")
