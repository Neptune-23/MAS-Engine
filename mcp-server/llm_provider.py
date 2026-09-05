import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    @abstractmethod
    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        current_state: Optional[str] = None,
    ) -> str:
        pass


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "deepseek-coder"):
        try:
            from openai import OpenAI

            self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
            self.model = model
        except ImportError:
            raise ImportError("请先安装 openai 库: pip install openai") from None

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        current_state: Optional[str] = None,
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 调用失败: {e}") from e


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        try:
            from openai import OpenAI

            self.client = OpenAI(api_key=api_key)
            self.model = model
        except ImportError:
            raise ImportError("请先安装 openai 库: pip install openai") from None

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        current_state: Optional[str] = None,
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"OpenAI API 调用失败: {e}") from e


class LocalLLMProvider(LLMProvider):
    """本地 7B 多 LoRA 动态路由提供者 (标准 HTTP 直连: 8000 端口)"""

    STATE_MODEL_MAP = {
        "requirement_extraction": "mas-architect",
        "requirement_analysis": "mas-architect",
        "resource_loading": "mas-architect",
        "code_construction": "mas-developer",
        "web_testing": "mas-tester",
        "self_healing": "mas-fixer",
        "fix_apply": "mas-fixer",
        "delivery_completed": "mas-auditor",
    }

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/v1",
        api_key: str = "none",
        default_model: str = "mas-developer",
    ):
        raw_url = str(base_url).strip()
        url_match = re.search(r"https?://[0-9a-zA-Z\.\:\-_]+(?:\/[0-9a-zA-Z\.\:\-_]*)*", raw_url)
        if url_match:
            clean_url = url_match.group(0)
        else:
            clean_url = re.sub(r"[\[\]\(\)\s]", "", raw_url)
            if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
                clean_url = f"http://{clean_url}"

        clean_url = clean_url.rstrip("/")
        if not clean_url.endswith("/v1"):
            clean_url = f"{clean_url}/v1"

        self.endpoint = f"{clean_url}/chat/completions"
        self.api_key = api_key
        self.default_model = default_model

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        current_state: Optional[str] = None,
    ) -> str:
        target_model = self.default_model
        if current_state:
            state_key = str(current_state).lower()
            target_model = self.STATE_MODEL_MAP.get(state_key, self.default_model)

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": max(0.01, float(temperature)),
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"本地模型返回 HTTP {e.code} 错误: {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"本地模型推理服务请求失败: {e}") from e


def get_llm_provider() -> LLMProvider:
    provider_type = os.getenv("LLM_PROVIDER", "local").lower()

    if provider_type == "local":
        base_url = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8000/v1")
        default_model = os.getenv("LOCAL_LLM_MODEL", "mas-developer")
        return LocalLLMProvider(base_url=base_url, default_model=default_model)

    elif provider_type == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-coder")
        return DeepSeekProvider(api_key=api_key, model=model)

    elif provider_type == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("未配置 OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        return OpenAIProvider(api_key=api_key, model=model)

    else:
        raise ValueError(f"未知的 LLM 提供者: {provider_type} (支持: local, deepseek, openai)")
