import os
import time
import json
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
from .config import settings

class GeminiAdapter:
    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self.base_url = settings.gemini_base_url
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        # Check if key needs refresh
        if not self.api_key or self.api_key.startswith("your_"):
            # Try reloading from .env
            env_file = settings.data_dir.parent / ".env"
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip("'").strip('"')
                            if val and not val.startswith("your_"):
                                self.api_key = val
                                self._client = None
                                break

        if not self.api_key or self.api_key.startswith("your_"):
            env_key = os.getenv("GEMINI_API_KEY", "")
            if env_key and not env_key.startswith("your_"):
                self.api_key = env_key
                self._client = None
            else:
                raise ValueError(
                    "GEMINI_API_KEY is not configured. Please supply a valid Gemini API key in the environment or .env to run autonomous LLM task execution."
                )

        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._client

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_retries: int = 5
    ) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """
        Sends chat completion request to Gemini through the OpenAI-compatible endpoint.
        Handles rate limits with exponential backoff and records token usage.
        Returns: (message_dict, token_usage_dict)
        """
        client = self._get_client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        delay = 2.0
        last_exception = None

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                message = choice.message

                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                }

                # Format response as clean dictionary
                msg_dict: Dict[str, Any] = {
                    "role": message.role or "assistant",
                    "content": message.content or "",
                    "tool_calls": []
                }

                if message.tool_calls:
                    for tc in message.tool_calls:
                        msg_dict["tool_calls"].append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        })

                # Pacing sleep for free-tier RPM limits
                time.sleep(2.0)
                return msg_dict, usage

            except Exception as e:
                err_str = str(e)
                last_exception = e
                # Rate limit (429) or transient network error
                if "429" in err_str or "rate limit" in err_str.lower() or "resource_exhausted" in err_str.lower() or "timeout" in err_str.lower():
                    # Check if this is a daily quota exhaustion (e.g. retry in 6h1m28s)
                    if ("retry in" in err_str and ("h" in err_str or "d" in err_str)) or "perday" in err_str.lower():
                        raise RuntimeError(f"Daily Google Gemini Free-Tier Quota Exceeded (RPD limit reached). Please provide a key with available daily quota or wait for daily reset: {err_str}")

                    import re
                    match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                    if match:
                        wait_seconds = float(match.group(1)) + 2.0
                        if wait_seconds > 60.0:
                            raise RuntimeError(f"Gemini API quota wait time is too long ({wait_seconds:.0f}s). Daily quota may be exhausted: {err_str}")
                    else:
                        wait_seconds = max(delay, 5.0)
                    time.sleep(wait_seconds)
                    delay = wait_seconds * 1.5
                else:
                    raise e

        raise RuntimeError(f"Gemini API request failed after {max_retries} retries: {str(last_exception)}")

llm_adapter = GeminiAdapter()
