"""Optional local Ollama and explicitly enabled remote chat generation."""

import json
import os
import re
import ssl
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.parse import urlsplit


_DEFAULT_URL = "http://127.0.0.1:11434"
_DEFAULT_TIMEOUT = 90.0
_REMOTE_TIMEOUT = 30.0
_DEEPSEEK_HOST = "api.deepseek.com"
_OPENAI_HOST = "api.openai.com"
_GEMINI_HOST = "generativelanguage.googleapis.com"
_DEFAULT_REMOTE_URL = f"https://{_DEEPSEEK_HOST}/v1"
_DEFAULT_REMOTE_MODEL = "deepseek-flash"
_REMOTE_PROVIDERS = {
    "deepseek": {"name": "DeepSeek", "model": _DEFAULT_REMOTE_MODEL},
    "openai": {"name": "OpenAI", "model": "gpt-4.1-mini"},
    "gemini": {"name": "Gemini", "model": "gemini-3.1-flash-lite"},
}
_CHAT_COMPLETIONS = "/v1/chat/completions"
_MAX_RESPONSE_BYTES = 1_000_000
_CLOUD_MODEL = re.compile(r"(?:-|:)cloud(?::[^/]*)?$", re.IGNORECASE)
_MODEL_ERRORS = {
    "authentication_failed": ("平台身份验证失败，请在模型设置重新填写对应平台的 API Key。", "Authentication failed. Enter the API key for the selected provider in model settings."),
    "balance_exhausted": ("平台返回余额不足，请检查该平台账户的余额和计费状态。", "The provider reported insufficient balance. Check the account balance and billing status."),
    "permission_denied": ("平台拒绝访问，请检查账户权限、地区支持和项目限制。", "Access was denied. Check account permissions, regional availability and project restrictions."),
    "model_not_found": ("平台未找到所选模型，请检查模型名称和账户的模型访问权限。", "The selected model was not found. Check its name and your account's model access."),
    "rate_limited": ("平台限制了请求频率或额度，请检查平台配额并稍后重试。", "The provider limited the request rate or quota. Check the provider quota and try again later."),
    "request_rejected": ("平台拒绝了请求参数，请检查模型配置和 API 兼容性。", "The provider rejected the request parameters. Check the model configuration and API compatibility."),
    "timeout": ("模型请求超时，请检查网络连接，或缩短问题后重试。", "The model request timed out. Check the connection or try a shorter question."),
    "network_error": ("无法连接模型平台，请检查服务端网络、DNS 和连接配置。", "Cannot connect to the model provider. Check server networking, DNS and connection settings."),
    "tls_error": ("模型平台的 TLS 证书验证失败，请检查服务端证书与网络配置。", "TLS verification failed. Check server certificates and network configuration."),
    "provider_unavailable": ("模型服务暂不可用，请稍后重试或在模型设置切换服务。", "The model service is unavailable. Try again later or select another provider in model settings."),
    "invalid_response": ("模型平台返回了不兼容的数据，请检查 API 配置。", "The provider returned incompatible data. Check the API configuration."),
    "empty_response": ("模型未返回可显示的回答，请调整问题或更换模型后重试。", "The model returned no displayable answer. Adjust the question or select another model."),
    "output_truncated": ("模型回答达到输出上限，请缩短问题后重试。", "The answer reached the output limit. Try a shorter question."),
    "provider_policy": ("模型平台限制了这次回答，请调整问题。", "The provider restricted this response. Rephrase the question."),
    "response_too_large": ("模型平台返回的数据超过大小限制，请缩短问题后重试。", "The provider response exceeded the size limit. Try a shorter question."),
    "local_model_missing": ("本地未安装所选模型，请在模型设置选择已安装的 Ollama 模型。", "The selected local model is not installed. Select an installed Ollama model in model settings."),
}


class ModelUnavailable(RuntimeError):
    """Carry a sanitized failure category without disclosing provider response bodies."""

    def __init__(self, message, *, code="provider_unavailable", http_status=None, retryable=False):
        super().__init__(message)
        self.code = code if code in _MODEL_ERRORS else "provider_unavailable"
        self.http_status = http_status
        self.retryable = retryable

    def as_dict(self):
        zh, en = _MODEL_ERRORS[self.code]
        status = {"state": "unavailable", "code": self.code, "retryable": self.retryable,
                  "message": {"zh": zh, "en": en}}
        if self.http_status is not None:
            status["http_status"] = self.http_status
        return status


def _with_default_tag(name: str) -> str:
    if ":" in name.rsplit("/", 1)[-1]:
        return name
    return f"{name}:latest"


def _gemini_auth_error(response):
    try:
        raw = response.read(16_385)
        if len(raw) > 16_384:
            return False
        payload = json.loads(raw)
    except (OSError, HTTPException, ValueError, RecursionError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    details = error.get("details", []) if isinstance(error, dict) else []
    return isinstance(details, list) and any(
        isinstance(detail, dict) and detail.get("reason") in {"API_KEY_INVALID", "API_KEY_EXPIRED", "CREDENTIALS_MISSING"}
        for detail in details
    )


def _request_json(
    connection: HTTPConnection,
    source: str,
    method: str,
    path: str,
    data: dict | None = None,
    *,
    auth_headers: dict[str, str] | None = None,
) -> dict:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if auth_headers:
        headers.update(auth_headers)

    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            code = {400: "request_rejected", 401: "authentication_failed", 402: "balance_exhausted",
                    403: "permission_denied", 404: "model_not_found", 408: "timeout",
                    413: "request_rejected", 422: "request_rejected", 429: "rate_limited"}.get(
                        response.status, "provider_unavailable")
            if source == "Gemini" and response.status == 400 and _gemini_auth_error(response):
                code = "authentication_failed"
            raise ModelUnavailable(f"{source} returned HTTP {response.status}", code=code,
                                   http_status=response.status, retryable=response.status in {408, 429} or response.status >= 500)
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except ssl.SSLCertVerificationError:
        raise ModelUnavailable(f"Cannot verify {source}", code="tls_error") from None
    except TimeoutError:
        raise ModelUnavailable(f"Timed out reading {source}", code="timeout", retryable=True) from None
    except (OSError, HTTPException, ValueError):
        raise ModelUnavailable(f"Cannot read from {source}", code="network_error", retryable=True) from None
    finally:
        connection.close()

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ModelUnavailable(f"{source} response exceeds the size limit", code="response_too_large")
    try:
        result = json.loads(raw)
    except (ValueError, RecursionError):
        raise ModelUnavailable(f"{source} returned invalid JSON", code="invalid_response") from None
    if not isinstance(result, dict):
        raise ModelUnavailable(f"{source} returned an invalid response", code="invalid_response")
    return result


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


class OllamaModel:
    provider = "ollama"

    def __init__(self, model: str, url: str = _DEFAULT_URL, timeout: float = _DEFAULT_TIMEOUT):
        endpoint = urlsplit(url)
        if (
            endpoint.scheme != "http"
            or endpoint.hostname not in {"127.0.0.1", "::1", "localhost"}
            or endpoint.username is not None
            or endpoint.path not in {"", "/"}
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("AI_MVP_OLLAMA_URL must be an HTTP loopback origin")
        self.host = "::1" if endpoint.hostname == "::1" else "127.0.0.1"
        port = endpoint.port
        if port == 0:
            raise ValueError("AI_MVP_OLLAMA_URL must use a nonzero port")
        self.port = port if port is not None else 11434
        if not model or any(char.isspace() for char in model) or _CLOUD_MODEL.search(model):
            raise ValueError("AI_MVP_OLLAMA_MODEL must name an installed local model")
        self.model = _with_default_tag(model)
        if not 1 <= timeout <= 300:
            raise ValueError("AI_MVP_OLLAMA_TIMEOUT_SECONDS must be between 1 and 300")
        self.timeout = timeout

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        # A direct loopback connection ignores proxy settings and never follows redirects.
        connection = HTTPConnection(self.host, self.port, timeout=self.timeout)
        return _request_json(connection, "local Ollama", method, path, data)

    def installed_models(self) -> list[str]:
        tags = self._request("GET", "/api/tags").get("models")
        if not isinstance(tags, list):
            raise ModelUnavailable("Ollama returned an invalid model list", code="invalid_response")
        names = set()
        for entry in tags:
            if not isinstance(entry, dict) or entry.get("remote_host") or entry.get("remote_model"):
                continue
            name = entry.get("model") or entry.get("name")
            if isinstance(name, str) and name and not any(c.isspace() for c in name) and not _CLOUD_MODEL.search(name):
                names.add(_with_default_tag(name))
        return sorted(names)

    def generate(self, system: str, user: str) -> str:
        # Check aliases before sending a prompt, since they may point to a remote model.
        if self.model not in self.installed_models():
            raise ModelUnavailable("The configured model is not installed locally", code="local_model_missing")

        result = self._request(
            "POST",
            "/api/chat",
            {
                "model": self.model,
                "messages": _messages(system, user),
                "stream": False,
                "think": False,
                "options": {"temperature": 0.2, "num_predict": 320},
            },
        )
        message = result.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            content = content.rsplit("</think>", 1)[-1].strip()
        if not isinstance(content, str) or not content or "<think>" in content:
            raise ModelUnavailable("The local model returned no final answer", code="empty_response")
        if result.get("done") is not True or result.get("done_reason") == "length":
            raise ModelUnavailable("The local model did not finish its reply", code="output_truncated")
        return content


def _validate_remote_config(api_key: str, timeout: float) -> None:
    if not api_key or any(not 33 <= ord(char) <= 126 for char in api_key):
        raise ValueError("The remote API key must contain printable ASCII characters without spaces")
    if not 1 <= timeout <= 120:
        raise ValueError("AI_MVP_REMOTE_TIMEOUT_SECONDS must be between 1 and 120")


def _remote_text(content, api_key: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ModelUnavailable("The remote model returned no final answer", code="empty_response")
    if api_key in content:
        raise ModelUnavailable("The remote model returned no final answer", code="invalid_response")
    return content.strip()


class OpenAICompatibleModel:
    def __init__(self, model: str, url: str, api_key: str, timeout: float = _REMOTE_TIMEOUT):
        invalid_url = "AI_MVP_REMOTE_BASE_URL must be an HTTPS origin with an optional /v1 path"
        try:
            endpoint = urlsplit(url)
            port = endpoint.port
        except ValueError:
            raise ValueError(invalid_url) from None
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or port == 0
            or endpoint.username is not None
            or endpoint.path not in {"", "/", "/v1", "/v1/"}
            or any(char in url for char in "?#\\")
            or any(char.isspace() or not char.isprintable() for char in url)
        ):
            raise ValueError(invalid_url)
        if not model or any(char.isspace() for char in model):
            raise ValueError("AI_MVP_REMOTE_MODEL must name a model")
        _validate_remote_config(api_key, timeout)
        self.host = endpoint.hostname
        self.port = port if port is not None else 443
        self.model = model
        self.timeout = timeout
        self._api_key = api_key
        self.provider = {_OPENAI_HOST: "openai", _DEEPSEEK_HOST: "deepseek"}.get(self.host, "custom")

    def generate(self, system: str, user: str) -> str:
        # HTTPSConnection verifies TLS and sends only one request to the configured host.
        connection = HTTPSConnection(self.host, self.port, timeout=self.timeout)
        payload = {
            "model": self.model,
            "messages": _messages(system, user),
            "stream": False,
        }
        if self.host == _OPENAI_HOST and self.port == 443:
            payload.update(max_completion_tokens=320, store=False)
        else:
            payload["max_tokens"] = 320
        if self.host == _DEEPSEEK_HOST and self.port == 443:
            payload["thinking"] = {"type": "disabled"}
        result = _request_json(
            connection,
            "remote model provider",
            "POST",
            _CHAT_COMPLETIONS,
            payload,
            auth_headers={"Authorization": f"Bearer {self._api_key}"},
        )
        choices = result.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelUnavailable("The remote model returned no final answer", code="invalid_response")
        choice = choices[0]
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if choice.get("finish_reason") not in (None, "stop"):
            code = "output_truncated" if choice.get("finish_reason") == "length" else "provider_policy"
            raise ModelUnavailable("The remote model returned no final answer", code=code)
        return _remote_text(content, self._api_key)


class GeminiModel:
    provider = "gemini"
    model = _REMOTE_PROVIDERS["gemini"]["model"]

    def __init__(self, api_key: str, timeout: float = _REMOTE_TIMEOUT):
        _validate_remote_config(api_key, timeout)
        self._api_key = api_key
        self.timeout = timeout

    def generate(self, system: str, user: str) -> str:
        connection = HTTPSConnection(_GEMINI_HOST, 443, timeout=self.timeout)
        result = _request_json(
            connection,
            "Gemini",
            "POST",
            f"/v1beta/models/{self.model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": 512, "thinkingConfig": {"thinkingLevel": "MINIMAL"}},
            },
            auth_headers={"x-goog-api-key": self._api_key},
        )
        candidates = result.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            feedback = result.get("promptFeedback")
            code = "provider_policy" if isinstance(feedback, dict) and feedback.get("blockReason") else "invalid_response"
            raise ModelUnavailable("The remote model returned no final answer", code=code)
        candidate = candidates[0]
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if candidate.get("finishReason") != "STOP" or not isinstance(parts, list):
            code = "output_truncated" if candidate.get("finishReason") == "MAX_TOKENS" else "provider_policy"
            raise ModelUnavailable("The remote model returned no final answer", code=code)
        answer = "".join(part["text"] for part in parts
                         if isinstance(part, dict) and not part.get("thought") and isinstance(part.get("text"), str))
        return _remote_text(answer, self._api_key)


def _timeout_from_environment(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be a number") from None


def from_environment(*, model_name: str | None = None) -> OllamaModel | None:
    model = (model_name if model_name is not None else os.environ.get("AI_MVP_OLLAMA_MODEL", "")).strip()
    if not model:
        return None
    timeout = _timeout_from_environment("AI_MVP_OLLAMA_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT)
    return OllamaModel(model, os.environ.get("AI_MVP_OLLAMA_URL", _DEFAULT_URL).strip(), timeout)


def remote_from_environment(*, enabled: bool = False) -> OpenAICompatibleModel | None:
    if not enabled and os.environ.get("AI_MVP_REMOTE_ENABLED") != "1":
        return None
    base_url = os.environ.get("AI_MVP_REMOTE_BASE_URL", _DEFAULT_REMOTE_URL).strip()
    deepseek = base_url.rstrip("/").lower() in {
        f"https://{_DEEPSEEK_HOST}", _DEFAULT_REMOTE_URL,
        f"https://{_DEEPSEEK_HOST}:443", f"https://{_DEEPSEEK_HOST}:443/v1",
    }
    model = os.environ.get("AI_MVP_REMOTE_MODEL", _DEFAULT_REMOTE_MODEL if deepseek else "").strip()
    if not model:
        raise ValueError("AI_MVP_REMOTE_MODEL must name a model")
    key_name = "DEEPSEEK_API_KEY" if deepseek else "AI_MVP_REMOTE_API_KEY"
    api_key = os.environ.get(key_name, "")
    if not api_key:
        raise ValueError(f"{key_name} must be a nonempty API key")
    return OpenAICompatibleModel(
        model,
        base_url,
        api_key,
        _timeout_from_environment("AI_MVP_REMOTE_TIMEOUT_SECONDS", _REMOTE_TIMEOUT),
    )


def model_options(local, remote):
    try:
        probe = OllamaModel("model-catalog", os.environ.get("AI_MVP_OLLAMA_URL", _DEFAULT_URL).strip(), timeout=3)
        ollama = {"status": "ready", "models": probe.installed_models()}
    except (ModelUnavailable, ValueError):
        ollama = {"status": "unavailable", "models": []}
    return {"ollama": ollama, "deepseek_model": _DEFAULT_REMOTE_MODEL, "remote_providers": _REMOTE_PROVIDERS,
            "startup": {"local": local.model if local else None, "remote": remote.model if remote else None}}


def session_model(settings):
    if not isinstance(settings, dict):
        raise ValueError("Model settings must be an object")
    provider = settings.get("provider")
    if provider == "default":
        return provider, None
    if provider == "ollama":
        model_name = settings.get("model")
        if not isinstance(model_name, str) or not 1 <= len(model_name.strip()) <= 160:
            raise ValueError("Select an installed Ollama model")
        return provider, from_environment(model_name=model_name)
    if isinstance(provider, str) and provider in _REMOTE_PROVIDERS:
        api_key = settings.get("api_key")
        if not isinstance(api_key, str) or not 1 <= len(api_key.strip()) <= 512:
            raise ValueError("Enter a valid API key for the selected provider")
        if settings.get("allow_billing") is not True:
            raise ValueError("Confirm the selected provider's API billing terms")
        timeout = _timeout_from_environment("AI_MVP_REMOTE_TIMEOUT_SECONDS", _REMOTE_TIMEOUT)
        api_key = api_key.strip()
        if provider == "gemini":
            return provider, GeminiModel(api_key, timeout)
        url = _DEFAULT_REMOTE_URL if provider == "deepseek" else f"https://{_OPENAI_HOST}/v1"
        return provider, OpenAICompatibleModel(_REMOTE_PROVIDERS[provider]["model"], url, api_key, timeout)
    raise ValueError("Unsupported model provider")
