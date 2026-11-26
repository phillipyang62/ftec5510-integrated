import json
import os
import ssl
import unittest
from unittest.mock import Mock, patch

from ai_mvp.models import (
    ModelUnavailable,
    OllamaModel,
    OpenAICompatibleModel,
    from_environment,
    remote_from_environment,
    session_model,
)


def connection_returning(data: dict, status: int = 200) -> Mock:
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = status
    response.read.return_value = json.dumps(data).encode("utf-8")
    return connection


class OllamaModelTests(unittest.TestCase):
    def test_requires_an_explicit_local_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(from_environment())
            self.assertEqual(from_environment(model_name="test-model").model, "test-model:latest")
        with patch.dict(os.environ, {"AI_MVP_OLLAMA_MODEL": "environment-model"}, clear=True):
            self.assertEqual(from_environment(model_name="cli-model").model, "cli-model:latest")
        with self.assertRaises(ValueError):
            OllamaModel("test-model", "https://ollama.com")
        with self.assertRaises(ValueError):
            OllamaModel("test-model:cloud")

    def test_refuses_to_send_a_prompt_to_a_remote_alias(self):
        tags = connection_returning({"models": [{
            "model": "local-alias:latest", "remote_host": "https://ollama.com"
        }]})
        with patch("ai_mvp.models.HTTPConnection", return_value=tags):
            with self.assertRaises(ModelUnavailable):
                OllamaModel("local-alias").generate("system", "user")
        tags.request.assert_called_once_with(
            "GET", "/api/tags", body=None, headers={"Accept": "application/json"}
        )

    def test_sends_profile_and_message_as_separate_roles(self):
        tags = connection_returning({"models": [{"model": "local-test:latest"}]})
        reply = connection_returning({
            "message": {"content": "<think>unused</think> 已按画像讲解。"}, "done": True
        })
        with patch("ai_mvp.models.HTTPConnection", side_effect=[tags, reply]):
            result = OllamaModel("local-test").generate("画像", "用户问题")

        self.assertEqual(result, "已按画像讲解。")
        self.assertEqual(reply.request.call_args.args, ("POST", "/api/chat"))
        body = json.loads(reply.request.call_args.kwargs["body"])
        self.assertEqual(body["messages"], [
            {"role": "system", "content": "画像"},
            {"role": "user", "content": "用户问题"},
        ])
        self.assertFalse(body["stream"])

    def test_rejects_redirects_without_opening_another_connection(self):
        redirect = connection_returning({}, status=307)
        with patch("ai_mvp.models.HTTPConnection", return_value=redirect) as connect:
            with self.assertRaisesRegex(ModelUnavailable, "307"):
                OllamaModel("local-test").generate("system", "user")
        connect.assert_called_once_with("127.0.0.1", 11434, timeout=90.0)


class RemoteModelTests(unittest.TestCase):
    def test_session_providers_use_their_genuine_https_hosts_and_protocols(self):
        for provider, host, model_name in (
            ("deepseek", "api.deepseek.com", "deepseek-flash"),
            ("openai", "api.openai.com", "gpt-4.1-mini"),
            ("gemini", "generativelanguage.googleapis.com", "gemini-3.1-flash-lite"),
        ):
            with self.subTest(provider=provider):
                payload = ({"candidates": [{"content": {"parts": [{"text": "Vendor answer"}]}, "finishReason": "STOP"}]}
                           if provider == "gemini" else {"choices": [{"message": {"content": "Vendor answer"}, "finish_reason": "stop"}]})
                reply = connection_returning(payload)
                with patch("ai_mvp.models.HTTPSConnection", return_value=reply) as connect:
                    selected, model = session_model({"provider": provider, "api_key": "fake-key", "allow_billing": True})
                    connect.assert_not_called()
                    self.assertEqual(model.generate("system", "user"), "Vendor answer")
                self.assertEqual((selected, model.provider, model.model), (provider, provider, model_name))
                connect.assert_called_once_with(host, 443, timeout=30.0)
                request = reply.request.call_args
                body = json.loads(request.kwargs["body"])
                if provider == "gemini":
                    self.assertEqual(request.args, ("POST", "/v1beta/models/gemini-3.1-flash-lite:generateContent"))
                    self.assertEqual(request.kwargs["headers"]["x-goog-api-key"], "fake-key")
                    self.assertEqual(body["systemInstruction"]["parts"], [{"text": "system"}])
                else:
                    self.assertEqual(request.args, ("POST", "/v1/chat/completions"))
                    self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer fake-key")
                    self.assertEqual(body["model"], model_name)
                    if provider == "openai":
                        self.assertEqual(body["max_completion_tokens"], 320)
                        self.assertIs(body["store"], False)
                    else:
                        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_vendor_http_errors_keep_actionable_categories_without_upstream_bodies(self):
        model = OpenAICompatibleModel("test-model", "https://provider.example", "fake-key")
        for status, code in ((400, "request_rejected"), (401, "authentication_failed"), (402, "balance_exhausted"),
                             (403, "permission_denied"), (404, "model_not_found"), (429, "rate_limited"),
                             (503, "provider_unavailable")):
            with self.subTest(status=status):
                reply = connection_returning({"error": "private-upstream-body"}, status=status)
                with patch("ai_mvp.models.HTTPSConnection", return_value=reply):
                    with self.assertRaises(ModelUnavailable) as raised:
                        model.generate("system", "user")
                detail = raised.exception.as_dict()
                self.assertEqual((detail["code"], detail["http_status"]), (code, status))
                self.assertNotIn("private-upstream-body", json.dumps(detail))
                self.assertNotIn("fake-key", json.dumps(detail))
                reply.getresponse.return_value.read.assert_not_called()

    def test_network_timeout_and_tls_failures_are_distinct(self):
        model = OpenAICompatibleModel("test-model", "https://provider.example", "fake-key")
        for error, code in ((OSError("private-network-details"), "network_error"),
                            (TimeoutError("private-timeout"), "timeout"),
                            (ssl.SSLCertVerificationError("private-certificate-details"), "tls_error")):
            with self.subTest(code=code):
                connection = Mock()
                connection.request.side_effect = error
                with patch("ai_mvp.models.HTTPSConnection", return_value=connection):
                    with self.assertRaises(ModelUnavailable) as raised:
                        model.generate("system", "user")
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("private-", json.dumps(raised.exception.as_dict()))

    def test_gemini_invalid_key_http_400_exposes_only_the_whitelisted_reason(self):
        _, model = session_model({"provider": "gemini", "api_key": "fake-key", "allow_billing": True})
        reply = connection_returning({"error": {
            "message": "private-vendor-body fake-key",
            "details": [{"reason": "API_KEY_INVALID", "metadata": {"private": "private-metadata"}}],
        }}, status=400)
        with patch("ai_mvp.models.HTTPSConnection", return_value=reply):
            with self.assertRaises(ModelUnavailable) as raised:
                model.generate("system", "user")
        detail = raised.exception.as_dict()
        self.assertEqual((detail["code"], detail["http_status"]), ("authentication_failed", 400))
        self.assertNotIn("private-", json.dumps(detail))
        self.assertNotIn("fake-key", json.dumps(detail))

    def test_key_alone_cannot_enable_remote_requests(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake-deepseek-key"}, clear=True):
            self.assertIsNone(remote_from_environment())
        with patch.dict(os.environ, {
            "AI_MVP_REMOTE_ENABLED": "1", "AI_MVP_REMOTE_API_KEY": "previous-provider-key",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                remote_from_environment()

    def test_key_and_cli_opt_in_use_deepseek_defaults_without_connecting_at_startup(self):
        reply = connection_returning({"choices": [{
            "message": {"content": "按画像回答。"}, "finish_reason": "stop"
        }]})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake-deepseek-key"}, clear=True):
            with patch("ai_mvp.models.HTTPSConnection", return_value=reply) as connect:
                model = remote_from_environment(enabled=True)
                self.assertEqual((model.host, model.model), ("api.deepseek.com", "deepseek-flash"))
                connect.assert_not_called()
                self.assertEqual(model.generate("画像", "问题"), "按画像回答。")
        body = json.loads(reply.request.call_args.kwargs["body"])
        connect.assert_called_once_with("api.deepseek.com", 443, timeout=30.0)
        self.assertEqual(reply.request.call_args.args, ("POST", "/v1/chat/completions"))
        self.assertEqual(reply.request.call_args.kwargs["headers"]["Authorization"], "Bearer fake-deepseek-key")
        self.assertEqual(body["max_tokens"], 320)
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_custom_provider_requires_an_explicit_model(self):
        with patch.dict(os.environ, {
            "AI_MVP_REMOTE_ENABLED": "1",
            "AI_MVP_REMOTE_API_KEY": "fake-api-key",
            "AI_MVP_REMOTE_BASE_URL": "https://custom-provider.example/v1",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "AI_MVP_REMOTE_MODEL"):
                remote_from_environment()

    def test_default_provider_honors_an_explicit_model_override(self):
        reply = connection_returning({"choices": [{"message": {"content": "回答"}, "finish_reason": "stop"}]})
        with patch.dict(os.environ, {
            "AI_MVP_REMOTE_ENABLED": "1",
            "DEEPSEEK_API_KEY": "fake-deepseek-key",
            "AI_MVP_REMOTE_MODEL": "deepseek-v4-pro",
        }, clear=True):
            with patch("ai_mvp.models.HTTPSConnection", return_value=reply):
                model = remote_from_environment()
                self.assertEqual(model.model, "deepseek-v4-pro")
                model.generate("画像", "问题")
        body = json.loads(reply.request.call_args.kwargs["body"])
        self.assertEqual(body["max_tokens"], 320)
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_remote_url_must_be_https_and_must_not_embed_credentials(self):
        for url in ("http://provider.example", "https://private-token@provider.example"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "AI_MVP_REMOTE_BASE_URL") as error:
                    OpenAICompatibleModel("test-model", url, "fake-api-key")
                self.assertNotIn("private-token", str(error.exception))

    def test_single_chat_request_uses_configured_model_and_bearer_header(self):
        reply = connection_returning({"choices": [{
            "message": {"content": " 已按画像讲解。 "}, "finish_reason": "stop"
        }]})
        with patch("ai_mvp.models.HTTPSConnection", return_value=reply) as connect:
            with patch.dict(os.environ, {
                "AI_MVP_REMOTE_ENABLED": "1",
                "AI_MVP_REMOTE_BASE_URL": "https://provider.example/v1/",
                "AI_MVP_REMOTE_MODEL": "test-model",
                "AI_MVP_REMOTE_API_KEY": "fake-api-key",
                "AI_MVP_REMOTE_TIMEOUT_SECONDS": "12",
            }, clear=True):
                model = remote_from_environment()
                connect.assert_not_called()
                self.assertEqual(model.generate("画像", "用户问题"), "已按画像讲解。")

        connect.assert_called_once_with("provider.example", 443, timeout=12.0)
        reply.request.assert_called_once()
        self.assertEqual(reply.request.call_args.args, ("POST", "/v1/chat/completions"))
        self.assertEqual(reply.request.call_args.kwargs["headers"]["Authorization"], "Bearer fake-api-key")
        body = json.loads(reply.request.call_args.kwargs["body"])
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["messages"], [
            {"role": "system", "content": "画像"},
            {"role": "user", "content": "用户问题"},
        ])
        self.assertEqual(body["max_tokens"], 320)
        self.assertFalse(body["stream"])

    def test_http_errors_do_not_read_upstream_body_redirect_or_retry(self):
        model = OpenAICompatibleModel("test-model", "https://provider.example", "fake-api-key")
        for status in (307, 429, 503):
            with self.subTest(status=status):
                reply = connection_returning({"error": "fake-api-key"}, status=status)
                with patch("ai_mvp.models.HTTPSConnection", return_value=reply) as connect:
                    with self.assertRaisesRegex(ModelUnavailable, str(status)) as error:
                        model.generate("profile", "message")
                connect.assert_called_once()
                reply.request.assert_called_once()
                reply.getresponse.return_value.read.assert_not_called()
                self.assertNotIn("fake-api-key", str(error.exception))

    def test_refuses_truncated_or_secret_echoing_responses(self):
        model = OpenAICompatibleModel("test-model", "https://provider.example", "fake-api-key")
        for reason, content in (("length", "truncated"), ("stop", "Echo fake-api-key")):
            with self.subTest(reason=reason):
                reply = connection_returning({"choices": [{
                    "message": {"content": content}, "finish_reason": reason
                }]})
                with patch("ai_mvp.models.HTTPSConnection", return_value=reply):
                    with self.assertRaisesRegex(ModelUnavailable, "no final answer"):
                        model.generate("profile", "message")
