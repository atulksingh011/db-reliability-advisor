import json

from google import genai

from ..contracts.models import AnalysisPackage
from .base import AIInterpretation, AIProvider
from .prompts import SYSTEM_PROMPT


class GeminiOutputError(RuntimeError):
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


class GeminiAIProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        if not model:
            raise ValueError("GEMINI_MODEL is required when AI_PROVIDER=gemini")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def analyze(self, package: AnalysisPackage) -> AIInterpretation:
        response = self._generate(
            f"{SYSTEM_PROMPT}\nAnalysis package (Contract B):\n"
            f"{package.model_dump_json(by_alias=True)}"
        )
        if not response.text:
            raise GeminiOutputError("Gemini returned an empty interpretation")
        try:
            return AIInterpretation.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise GeminiOutputError(
                "Gemini returned invalid structured output", response.text
            ) from exc

    def repair(
        self,
        package: AnalysisPackage,
        errors: list[str],
        original_response: str | None = None,
    ) -> AIInterpretation:
        response = self._generate(
            f"{SYSTEM_PROMPT}\nRepair exactly one prior structured-output attempt.\n"
            f"Validation errors: {json.dumps(errors)}\n"
            f"Original response: {original_response or '(unavailable)'}\n"
            f"Contract B: {package.model_dump_json(by_alias=True)}\n"
            "Correct structure and grounding only. Do not add evidence, measurements, queries, "
            "charts, or HTML. Return only the defined structured output."
        )
        if not response.text:
            raise GeminiOutputError("Gemini repair returned an empty interpretation")
        try:
            return AIInterpretation.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise GeminiOutputError(
                "Gemini repair returned invalid structured output", response.text
            ) from exc

    def _generate(self, contents: str):
        return self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": AIInterpretation.model_json_schema(),
            },
        )
