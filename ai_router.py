import os
import requests

class AIRouter:
    def __init__(self):
        self.providers = [
            "openai",
            "gemini",
            "groq",
            "openrouter",
            "together",
            "fireworks",
        ]

    def ask(self, prompt: str) -> dict:
        for provider in self.providers:
            key = os.getenv(f"{provider.upper()}_API_KEY", "").strip()
            if not key:
                continue

            try:
                if provider == "openai":
                    return self._openai(prompt, key)
                if provider == "gemini":
                    return self._gemini(prompt, key)
                if provider == "groq":
                    return self._openai_compatible(
                        prompt,
                        key,
                        "https://api.groq.com/openai/v1/chat/completions",
                        os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                        provider,
                    )
                if provider == "openrouter":
                    return self._openai_compatible(
                        prompt,
                        key,
                        "https://openrouter.ai/api/v1/chat/completions",
                        os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free"),
                        provider,
                    )
                if provider == "together":
                    return self._openai_compatible(
                        prompt,
                        key,
                        "https://api.together.xyz/v1/chat/completions",
                        os.getenv("TOGETHER_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"),
                        provider,
                    )
                if provider == "fireworks":
                    return self._openai_compatible(
                        prompt,
                        key,
                        "https://api.fireworks.ai/inference/v1/chat/completions",
                        os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p1-8b-instruct"),
                        provider,
                    )
            except Exception as e:
                last_error = str(e)
                continue

        return {
            "provider": "none",
            "error": "No fallback API key is configured or all configured providers failed.",
            "answer": "No cloud fallback brain is active. Add at least one API key in Render Environment Variables.",
        }

    def _openai(self, prompt: str, key: str) -> dict:
        return self._openai_compatible(
            prompt,
            key,
            "https://api.openai.com/v1/chat/completions",
            os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "openai",
        )

    def _openai_compatible(self, prompt: str, key: str, url: str, model: str, provider: str) -> dict:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are NEXUS Cloud fallback AI. Be practical, precise, and do not claim actions you did not perform."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "provider": provider,
            "model": model,
            "answer": data["choices"][0]["message"]["content"],
        }

    def _gemini(self, prompt: str, key: str) -> dict:
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        r = requests.post(
            url,
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ]
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        return {
            "provider": "gemini",
            "model": model,
            "answer": answer,
        }
