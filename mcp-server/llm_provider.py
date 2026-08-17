import os
from abc import ABC, abstractmethod
import openai

# ============================================================
# 1. 定义抽象接口（LLM 提供者的标准契约）
# ============================================================
class LLMProvider(ABC):
    @abstractmethod
    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """根据系统提示和用户提示，返回 LLM 生成的原始文本响应"""
        pass

# ============================================================
# 2. 具体实现：DeepSeek 提供者（基于 OpenAI SDK）
# ============================================================
class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DeepSeek API key is missing.")
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )

    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            # 这里可以加上更优雅的异常处理
            raise RuntimeError(f"DeepSeek API 调用失败: {e}")

# ============================================================
# 3. (可选) 扩展：OpenAI 提供者
# ============================================================
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API 调用失败: {e}")

# ============================================================
# 4. 工厂函数：根据配置动态选择提供者
# ============================================================
def get_llm_provider() -> LLMProvider:
    provider_type = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    api_key = os.environ.get("DEEPSEEK_API_KEY") if provider_type == "deepseek" else os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(f"未配置 {provider_type.upper()}_API_KEY 环境变量")

    if provider_type == "deepseek":
        return DeepSeekProvider(api_key)
    elif provider_type == "openai":
        return OpenAIProvider(api_key)
    else:
        raise ValueError(f"不支持的 LLM_PROVIDER: {provider_type}")