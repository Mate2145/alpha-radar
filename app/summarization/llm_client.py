import subprocess

import httpx

from app.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return self.provider != "fallback"

    @property
    def provider(self) -> str:
        return self.settings.llm_provider.lower().strip()

    @property
    def model_name(self) -> str:
        if self.provider == "openrouter":
            return f"openrouter:{self.settings.openrouter_model}"
        if self.provider == "codex_cli":
            return f"codex-cli:{self.settings.codex_model or 'default'}"
        if self.provider == "openai":
            return f"openai:{self.settings.openai_model}"
        return "fallback-rule-based"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider == "openai":
            return self._complete_openai_compatible(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                missing_key_message="OPENAI_API_KEY is not configured",
            )
        if self.provider == "openrouter":
            return self._complete_openai_compatible(
                api_key=self.settings.openrouter_api_key,
                base_url=self.settings.openrouter_base_url,
                model=self.settings.openrouter_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                missing_key_message="OPENROUTER_API_KEY is not configured",
            )
        if self.provider == "codex_cli":
            return self._complete_codex_cli(system_prompt, user_prompt)
        if self.provider == "fallback":
            raise RuntimeError("LLM_PROVIDER is set to fallback")

        raise RuntimeError(
            "LLM_PROVIDER must be one of: fallback, openai, openrouter, codex_cli"
        )

    def _complete_openai_compatible(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        missing_key_message: str,
    ) -> str:
        if not api_key:
            raise RuntimeError(missing_key_message)
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _complete_codex_cli(self, system_prompt: str, user_prompt: str) -> str:
        command = [
            self.settings.codex_command,
            "exec",
            "--ephemeral",
        ]
        if self.settings.codex_model:
            command.extend(["--model", self.settings.codex_model])
        command.append(system_prompt)

        try:
            result = subprocess.run(
                command,
                input=user_prompt,
                text=True,
                capture_output=True,
                timeout=self.settings.codex_timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Codex CLI command not found: {self.settings.codex_command}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"codex exec timed out after {self.settings.codex_timeout_seconds} seconds"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"codex exec failed: {detail}")
        content = result.stdout.strip()
        if not content:
            raise RuntimeError("codex exec returned no content")
        return content
