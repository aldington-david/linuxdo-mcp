"""Shared polite request spacing. Callers hold cookies.locked() across the HTTP request."""
from email.utils import parsedate_to_datetime
import json
import math
import os
import random
import tempfile
import time

from . import cookies

DEFAULTS = {
    "min_seconds": 1.0, "max_seconds": 1.8,
    "search_min_seconds": 2.2, "search_max_seconds": 3.2,
    "rate_limit_cooldown_seconds": 60.0, "challenge_cooldown_seconds": 120.0,
}


class Deferred(RuntimeError):
    def __init__(self, code, seconds):
        self.code = code
        reason = "站点限流" if code == "rate_limited" else "站点防护"
        super().__init__(f"{reason}冷却中，约 {math.ceil(seconds)} 秒后可重试；本次未继续访问论坛，凭证已保留。")


def policy():
    path = cookies.CACHE.parent / "request-policy.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        settings = {}
    except (OSError, ValueError):
        raise RuntimeError("无法读取 request-policy.json，请检查格式和权限。") from None
    if not isinstance(settings, dict) or set(settings) - set(DEFAULTS):
        raise RuntimeError("request-policy.json 含不支持的配置，请参照默认模板。")
    values = {**DEFAULTS, **settings}
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values.values()):
        raise RuntimeError("请求间隔必须是有限的数字。")
    if not (0.2 <= values["min_seconds"] <= values["max_seconds"] <= 30
            and values["min_seconds"] <= values["search_min_seconds"] <= values["search_max_seconds"] <= 30
            and 1 <= values["rate_limit_cooldown_seconds"] <= 3600
            and 1 <= values["challenge_cooldown_seconds"] <= 3600):
        raise RuntimeError("请求间隔范围不正确：普通间隔 0.2–30 秒，搜索间隔不小于普通下限；冷却配置 1–3600 秒。")
    return values


def _read():
    path = cookies.CACHE.parent / "request-state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError
        for name in ("next_request_at", "next_search_at", "cooldown_until"):
            value = state.get(name, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError
        if state.get("cooldown_code", "rate_limited") not in ("rate_limited", "blocked"):
            raise ValueError
        return state
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise RuntimeError("无法读取论坛请求节奏状态，已停止发送请求；请检查 request-state.json 的格式和权限。") from None


def _write(state):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cookies.CACHE.parent,
                                         prefix=".request-", delete=False) as stream:
            temporary = stream.name
            json.dump(state, stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, cookies.CACHE.parent / "request-state.json")
    except OSError:
        raise RuntimeError("无法保存论坛请求节奏状态，已停止继续请求，请检查缓存目录权限。") from None
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def before_request(path):
    values, state = policy(), _read()
    now = time.time()
    remaining = state.get("cooldown_until", 0) - now
    if remaining > 0:
        raise Deferred(state.get("cooldown_code", "rate_limited"), remaining)
    search = path.split("?", 1)[0] == "/search.json"
    due = max(state.get("next_request_at", 0), state.get("next_search_at", 0) if search else 0)
    # Idle/network time counts toward the gap. Bound ordinary waiting if the clock moves backwards.
    wait = min(max(0, due - now), max(values["max_seconds"], values["search_max_seconds"]))
    if wait:
        time.sleep(wait)
    started = time.time()
    state["next_request_at"] = started + random.uniform(values["min_seconds"], values["max_seconds"])
    if search:
        state["next_search_at"] = started + random.uniform(values["search_min_seconds"], values["search_max_seconds"])
    state.update(cooldown_until=0, cooldown_code="rate_limited")
    _write(state)
    return values


def _retry_after(headers, now):
    value = str(headers.get("retry-after", "")).strip()
    try:
        if value.isdigit():
            seconds = float(value)
        else:
            target = parsedate_to_datetime(value).timestamp()
            origin = parsedate_to_datetime(headers["date"]).timestamp() if headers.get("date") else now
            seconds = target - origin
        return max(1.0, seconds) if math.isfinite(seconds) else None
    except (ValueError, TypeError, OverflowError, IndexError):
        return None


def cool_down(headers, code, values=None):
    # Use the request's validated policy even if an editor changes the file mid-response.
    values, state = policy() if values is None else values, _read()
    now = time.time()
    delay = _retry_after({str(k).lower(): v for k, v in headers.items()}, now)
    fallback = values["rate_limit_cooldown_seconds" if code == "rate_limited" else "challenge_cooldown_seconds"]
    delay = fallback if delay is None else max(delay, fallback) if code == "blocked" else delay
    state.update(cooldown_until=max(state.get("cooldown_until", 0), now + delay), cooldown_code=code)
    _write(state)
    return math.ceil(state["cooldown_until"] - now)
