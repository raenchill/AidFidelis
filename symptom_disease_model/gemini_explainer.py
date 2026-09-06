import os
import random
import time
from typing import List

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field


load_dotenv()

client: Groq | None = None


def get_client() -> Groq:
    global client

    if client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY was not found. Check your .env file."
            )
        client = Groq(api_key=api_key)

    return client


class PossibleCondition(BaseModel):
    name: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class AidFidelisExplanation(BaseModel):
    summary: str
    possible_conditions: List[PossibleCondition]
    self_care: List[str]
    red_flags: List[str]
    follow_up_questions: List[str]
    recommended_action: str
    disclaimer: str


def generate_with_retry(
    prompt: str,
    max_attempts_per_model: int | None = None,
):
    """
    Call Groq with retries and configurable fallback models.

    Retries temporary errors such as:
    - 408: Request timeout
    - 429: Rate limit
    - 500, 502, 503, 504: Temporary server problems
    """

    model_names = [
        model.strip()
        for model in os.getenv(
            "GROQ_MODELS",
            "llama-3.3-70b-versatile",
        ).split(",")
        if model.strip()
    ]

    if max_attempts_per_model is None:
        max_attempts_per_model = max(
            1,
            int(os.getenv("GROQ_MAX_ATTEMPTS", "1")),
        )

    last_error: Exception | None = None

    for model_name in model_names:
        for attempt in range(max_attempts_per_model):
            try:
                response = get_client().chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": "Return only valid JSON matching the requested explanation schema.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )

                content = response.choices[0].message.content
                if not content:
                    raise RuntimeError("Groq returned an empty explanation.")
                return content

            except Exception as error:
                last_error = error
                status_code = getattr(error, "status_code", None)
                print(
                    f"Groq model {model_name} failed with status "
                    f"{status_code}: {error}"
                )

                if attempt < max_attempts_per_model - 1:
                    delay_seconds = (
                        2 ** attempt
                        + random.uniform(0.2, 1.0)
                    )

                    print(
                        f"Groq model {model_name} is temporarily "
                        f"unavailable. Retrying in "
                        f"{delay_seconds:.1f} seconds..."
                    )

                    time.sleep(delay_seconds)

        print(
            f"Switching from {model_name} to another Groq model."
        )

    raise RuntimeError(
        "The Groq explanation service is temporarily unavailable "
        "after several retries. Please try again shortly."
    ) from last_error


def explain(
    symptoms: str,
    predictions: list[dict],
) -> dict:
    if not symptoms.strip():
        raise ValueError("Symptoms cannot be empty.")

    if not predictions:
        raise ValueError("Predictions cannot be empty.")

    formatted_predictions = "\n".join(
        [
            (
                f"- Disease: {item['disease']}\n"
                f"  Confidence: "
                f"{float(item['confidence']):.8f}"
            )
            for item in predictions[:5]
        ]
    )

    prompt = f"""
You are AidFidelis AI, a health-information explanation assistant.

A separate machine-learning classifier generated the predictions below.
Your role is only to explain those supplied predictions.

USER SYMPTOMS

{symptoms}

MODEL PREDICTIONS

{formatted_predictions}

STRICT RULES

1. Do not diagnose the user.
2. Do not add conditions absent from the supplied predictions.
3. Keep every confidence score exactly as supplied.
4. Confidence values must remain decimals between 0 and 1.
5. Do not include confidence percentages inside condition names.
6. Do not prescribe medicines or give medication dosages.
7. Do not advise stopping prescribed medication.
8. Do not describe model scores as medically confirmed probabilities.
9. Explain that multiple conditions can share similar symptoms.
10. Provide only low-risk general self-care information.
11. Clearly identify symptoms requiring urgent professional care.
12. Do not claim that the model performed medical tests.
13. Use clear, compassionate language.
14. Avoid phrases such as "characteristic of",
    "strongly indicates", "classic symptoms of",
    or "highly suggestive of".
15. Prefer phrases such as "can occur with",
    "may be associated with", or
    "could be consistent with".
16. Do not recommend a specific medication or treatment.
17. Recommend professional evaluation where appropriate.
18. The summary must make clear that this is pattern matching,
    not a confirmed medical diagnosis.
""".strip()

    try:
        response_json = generate_with_retry(prompt)
        explanation = AidFidelisExplanation.model_validate_json(response_json)

        validated = validate_conditions(
            explanation=explanation,
            predictions=predictions,
        )

        return validated.model_dump()

    except RuntimeError:
        raise

    except Exception as error:
        raise RuntimeError(
            f"Groq explanation failed: {error}"
        ) from error


def validate_conditions(
    explanation: AidFidelisExplanation,
    predictions: list[dict],
) -> AidFidelisExplanation:
    """
    Ensure Gemini only returns conditions supplied by the classifier
    and restore the classifier's original confidence scores.
    """

    prediction_map = {
        str(item["disease"]).strip().lower(): {
            "name": str(item["disease"]).strip(),
            "confidence": float(item["confidence"]),
        }
        for item in predictions
    }

    valid_conditions: list[PossibleCondition] = []

    for condition in explanation.possible_conditions:
        key = condition.name.strip().lower()

        if key not in prediction_map:
            continue

        original = prediction_map[key]

        valid_conditions.append(
            PossibleCondition(
                name=original["name"],
                confidence=original["confidence"],
                reason=condition.reason,
            )
        )

    explanation.possible_conditions = valid_conditions

    explanation.disclaimer = (
        "AidFidelis provides general health information and "
        "explains machine-learning predictions. It does not "
        "provide a medical diagnosis or replace a qualified "
        "healthcare professional."
    )

    return explanation