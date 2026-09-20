import json
import requests

from .config import settings
from .diagnostics import diagnostics
from .github_tools import github


class BackendAgent:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.AI_MODEL

        self.url = "https://api.openai.com/v1/responses"

    def _check_config(self):
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured"
            )

    def _call_ai(self, instructions, input_text):
        self._check_config()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
        }

        response = requests.post(
            self.url,
            headers=headers,
            json=payload,
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        return data.get("output_text", "")

    def diagnose(self, user_message="Check my backend"):
        report = diagnostics.run()

        prompt = f"""
You are an AI backend diagnostic engineer.

The user owns and controls this backend.

Your job is to analyze the diagnostic information and
explain problems clearly.

Do NOT modify files.
Do NOT deploy anything.
Do NOT expose secrets.

Return:

1. Overall status
2. Detected problems
3. Likely cause
4. Files that should be inspected
5. Recommended fix
6. Tests that should be performed

User request:
{user_message}

Diagnostic report:
{json.dumps(report, indent=2)}
"""

        answer = self._call_ai(
            instructions=prompt,
            input_text=user_message,
        )

        return {
            "user_request": user_message,
            "diagnostics": report,
            "ai_analysis": answer,
        }

    def inspect_file(self, path):
        file_data = github.read_file(path)

        prompt = f"""
Analyze the following backend source file.

File:
{path}

Code:
{file_data["content"]}

Explain:

- What this file does
- Possible bugs
- Reliability problems
- Security concerns
- Performance issues
- Possible improvements

Do not modify the file.
"""

        answer = self._call_ai(
            instructions=prompt,
            input_text=file_data["content"],
        )

        return {
            "file": path,
            "analysis": answer,
        }


agent = BackendAgent()
