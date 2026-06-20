"""
Runtime patches applied at every Python startup — including subprocesses like `hermes gateway`.

Replaces build-time file patching (patch_adapter.py, patch_gateway.py).
"""
import json
import sys
import uuid
from types import SimpleNamespace


def _apply_gemini_adapter_patch():
    """
    Replace GeminiNativeAdapter._stream_completion with a non-SSE implementation
    that prevents delta tool-call truncation.
    """
    try:
        import agent.gemini_native_adapter as _m
    except ImportError:
        return

    def _patched_stream_completion(self, *, model, request, timeout=None):
        url = f"{self.base_url}/models/{model}:generateContent"

        def _generator():
            try:
                response = self._http.post(
                    url, json=request, headers=self._headers(), timeout=timeout
                )
                if response.status_code != 200:
                    raise _m.gemini_http_error(response)
                payload = response.json()
                candidates = payload.get("candidates") or []
                if not candidates:
                    return
                cand = candidates[0] if isinstance(candidates[0], dict) else {}
                parts = (
                    ((cand.get("content") or {}).get("parts") or [])
                    if isinstance(cand, dict)
                    else []
                )

                reasoning_pieces = [
                    p["text"]
                    for p in parts
                    if isinstance(p, dict)
                    and p.get("thought") is True
                    and isinstance(p.get("text"), str)
                ]
                if reasoning_pieces:
                    yield _m._make_stream_chunk(model=model, reasoning="".join(reasoning_pieces))

                text_pieces = [
                    p["text"]
                    for p in parts
                    if isinstance(p, dict)
                    and isinstance(p.get("text"), str)
                    and p.get("text")
                    and p.get("thought") is not True
                ]
                if text_pieces:
                    yield _m._make_stream_chunk(model=model, content="".join(text_pieces))

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
                        yield _m._make_stream_chunk(
                            model=model,
                            tool_call_delta={
                                "index": tool_call_index,
                                "id": f"call_{uuid.uuid4().hex[:12]}",
                                "name": name,
                                "arguments": args_str,
                                "extra_content": _m._tool_call_extra_from_part(part),
                            },
                        )
                        tool_call_index += 1

                finish_reason_raw = str(cand.get("finishReason") or "")
                mapped = (
                    "tool_calls"
                    if tool_call_index > 0
                    else _m._map_gemini_finish_reason(finish_reason_raw)
                )
                finish_chunk = _m._make_stream_chunk(model=model, finish_reason=mapped)
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
                raise _m.GeminiAPIError(
                    f"Gemini mock streaming request failed: {exc}",
                    code="gemini_stream_error",
                ) from exc

        return _generator()

    target_class = next(
        (
            getattr(_m, name)
            for name in dir(_m)
            if isinstance(getattr(_m, name), type)
            and hasattr(getattr(_m, name), "_stream_completion")
        ),
        None,
    )
    if target_class is None:
        print(
            "sitecustomize [WARN]: _stream_completion not found in"
            " agent.gemini_native_adapter — patch skipped",
            file=sys.stderr,
        )
        return

    target_class._stream_completion = _patched_stream_completion


def _preseed_cron():
    """
    Import cron.scheduler_provider while sys.path is clean, caching it in
    sys.modules before hermes adds plugins/ to the path. This prevents
    plugins/cron/ from shadowing the core cron package on later imports.
    """
    try:
        import cron.scheduler_provider  # noqa: F401
    except ImportError:
        pass


_apply_gemini_adapter_patch()
_preseed_cron()
