import json
import logging
import time

import requests

from .config import settings
from .diagnostics import diagnostics
from .github_tools import github


logger = logging.getLogger("ai_backend_doctor.agent")


class BackendAgent:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.AI_MODEL
        self.url = "https://api.openai.com/v1/responses"
        self.timeout = 60

    def _check_config(self):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

    def _extract_output_text(self, data):
        direct_text = data.get("output_text")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()

        parts = []
        output = data.get("output", [])
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content", [])
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())

        result = "\n".join(parts).strip()
        if not result:
            raise RuntimeError("OpenAI returned a response, but no text output was found")
        return result

    def _call_ai(self, instructions, input_text):
        self._check_config()
        started = time.monotonic()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
        }

        try:
            response = requests.post(
                self.url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            logger.error("OpenAI request timed out after %ss", self.timeout)
            raise TimeoutError(
                f"AI request timed out after {self.timeout} seconds"
            ) from exc
        except requests.RequestException as exc:
            logger.error("OpenAI request failed: %s", type(exc).__name__)
            raise RuntimeError("AI provider request failed") from exc
        finally:
            logger.info("AI request finished in %.2fs", time.monotonic() - started)

        if not response.ok:
            try:
                error_data = response.json()
            except Exception:
                error_data = {"message": response.text[:500]}
            raise RuntimeError(
                f"OpenAI API error {response.status_code}: {error_data}"
            )

        return self._extract_output_text(response.json())

    def diagnose(self, user_message="Check my backend"):
        report = diagnostics.run()
        prompt = f"""
You are an AI backend diagnostic engineer.

Analyze the diagnostic report for the user's backend.

Rules:
- Do not modify files or deploy anything during diagnosis.
- Never expose secrets, API keys, tokens, or credentials.
- Separate confirmed facts from likely causes.
- Identify the exact files/functions that should be inspected.
- Give concrete, testable recommendations.

Return:
1. Overall status
2. Confirmed problems
3. Likely causes
4. Files/functions to inspect
5. Recommended fix
6. Verification plan

User request:
{user_message}

Diagnostic report:
{json.dumps(report, indent=2)}
"""
        answer = self._call_ai(prompt, user_message)
        return {
            "user_request": user_message,
            "diagnostics": report,
            "ai_analysis": answer,
        }

    def inspect_file(self, path):
        file_data = github.read_file(path)
        content = file_data["content"]
        prompt = f"""
Analyze this backend source file as a senior backend engineer.

File: {path}

Rules:
- Do not modify the file.
- Do not expose secrets.
- Base findings on the supplied code.
- Distinguish confirmed bugs from possible issues.
- Give concrete fixes and verification steps.

Review:
- functionality
- bugs and edge cases
- reliability/timeouts
- security
- performance
- maintainability

Source code follows.
"""
        answer = self._call_ai(prompt, content)
        return {
            "file": path,
            "analysis": answer,
        }


agent = BackendAgent()
