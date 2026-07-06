"""Core logic for the recipe generator toy project.

Kept separate from the notebook so it can be unit tested and reused.
"""
import functools
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path


def load_ingredient_data(data_dir: Path) -> dict:
    """Load every *.json file in data_dir into {category: [items...]}.

    Each JSON file is expected to look like:
        {"category": "proteins", "items": [{"name": "chicken breast", "tags": [...]}]}
    Files missing a "category" key fall back to using the filename stem.
    Files missing an "items" key are treated as having no items.
    """
    categories = {}
    for json_path in sorted(Path(data_dir).glob("*.json")):
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        category = payload.get("category", json_path.stem)
        categories[category] = payload.get("items", [])
    return categories


def sample_ingredients(ingredient_bank: dict, per_category: int = 2, seed: int | None = None) -> dict:
    """Randomly sample up to `per_category` items from each category."""
    rng = random.Random(seed)
    sampled = {}
    for category, items in ingredient_bank.items():
        k = min(per_category, len(items))
        sampled[category] = rng.sample(items, k)
    return sampled


def filter_by_dietary(ingredient_bank: dict, dietary: str) -> dict:
    """Keep only items whose tags include the given dietary label.

    Categories with no matching items are kept but return an empty list,
    so downstream code can still see which categories exist.
    """
    filtered = {}
    for category, items in ingredient_bank.items():
        filtered[category] = [item for item in items if dietary in item.get("tags", [])]
    return filtered


# Tags that conflict with a given dietary requirement. An item is excluded when
# any of its tags appears in the conflict set for the requested diet. Diets not
# listed here impose no exclusions (every item is kept).
DIETARY_CONFLICTS = {
    "vegan": {"poultry", "fish", "red meat", "shellfish", "meat", "dairy", "creamy"},
    "vegetarian": {"poultry", "fish", "red meat", "shellfish", "meat"},
    "pescatarian": {"poultry", "red meat", "meat"},
    "dairy-free": {"dairy", "creamy"},
}


def exclude_by_dietary(ingredient_bank: dict, dietary: str) -> dict:
    """Drop items whose tags conflict with the given dietary requirement.

    Unlike `filter_by_dietary` (an allow-list), this keeps every item that is
    *compatible* with the diet (e.g. vegetables and grains are kept for
    "vegan") and only removes items carrying a conflicting tag (e.g. "poultry"
    or "fish"). An unknown dietary label imposes no exclusions, so the bank is
    returned unchanged.

    Categories with no remaining items are kept but return an empty list,
    so downstream code can still see which categories exist.
    """
    conflicts = DIETARY_CONFLICTS.get(dietary, set())
    filtered = {}
    for category, items in ingredient_bank.items():
        filtered[category] = [
            item for item in items if not (conflicts & set(item.get("tags", [])))
        ]
    return filtered


def build_prompt(chosen_ingredients: dict, cuisine: str | None = None, dietary: str | None = None) -> str:
    """Build the LLM prompt string from a dict of {category: [items]}."""
    ingredients_json = json.dumps(chosen_ingredients, indent=2)
    constraints = []
    if cuisine:
        constraints.append(f"Cuisine style: {cuisine}.")
    if dietary:
        constraints.append(f"Dietary requirement: {dietary}.")
    constraints_text = " ".join(constraints)

    return f"""You are a helpful home-cooking assistant.
Using ONLY the ingredients below (plus basic staples like salt, water, oil), suggest one recipe.
{constraints_text}

Available ingredients (JSON):
{ingredients_json}

Respond with:
1. Recipe name
2. Ingredient list with rough quantities
3. Numbered preparation steps
4. Approximate total cook time
"""


def get_client():
    """Build an AzureOpenAI client from environment variables.

    Imported lazily so `openai` is only required when actually calling the LLM,
    not when just running the unit tests for prompt/sampling logic.
    """
    from openai import AzureOpenAI

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


def _default_rate_limit_errors():
    """Resolve the openai rate-limit exception type lazily.

    Imported lazily (like `get_client`) so `openai` is only required when
    actually calling the LLM, not when unit-testing prompt/sampling logic.
    """
    from openai import RateLimitError

    return (RateLimitError,)


def retry_on_rate_limit(
    fn=None,
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions=None,
    sleep=time.sleep,
):
    """Wrap `fn` so it is retried with exponential backoff on rate-limit errors.

    On a matching exception the call sleeps for `base_delay`, then
    `base_delay * backoff_factor`, and so on (capped at `max_delay`) before
    retrying, up to `max_retries` times. After the final attempt the original
    exception is re-raised.

    `exceptions` overrides which exception types trigger a retry (defaults to
    `openai.RateLimitError`, resolved lazily). `sleep` is injectable so tests
    can run without real delays.

    Usable directly or as a decorator:
        create = retry_on_rate_limit(client.chat.completions.create)
        @retry_on_rate_limit(max_retries=3)
        def f(): ...
    """
    if fn is None:
        return functools.partial(
            retry_on_rate_limit,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
            exceptions=exceptions,
            sleep=sleep,
        )

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        retryable = exceptions if exceptions is not None else _default_rate_limit_errors()
        delay = base_delay
        for attempt in range(max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except retryable:
                if attempt == max_retries:
                    raise
                sleep(min(delay, max_delay))
                delay *= backoff_factor

    return wrapper


def call_llm(prompt: str, client=None) -> str:
    """Send the prompt to the configured Azure AI Foundry deployment and return the reply text.

    Rate-limit errors are retried with exponential backoff. `client` can be
    injected (e.g. a fake) instead of building one from environment variables.
    """
    client = client or get_client()
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    create = retry_on_rate_limit(client.chat.completions.create)
    response = create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You are a concise, practical home-cooking assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_completion_tokens=500,
    )
    return response.choices[0].message.content


def save_output(
    chosen_ingredients: dict,
    recipe: str,
    outputs_dir: Path,
    *,
    prompt: str | None = None,
    filename: str | None = None,
    timestamp: datetime | None = None,
) -> Path:
    """Write the chosen ingredients + generated recipe to a JSON file.

    Creates `outputs_dir` if it doesn't exist and returns the path written.
    By default the filename is timestamped (`recipe_YYYYMMDDTHHMMSS.json`);
    pass `filename` to override, or `timestamp` to pin the generated name
    (useful for deterministic tests). The prompt is included when given.
    """
    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = (timestamp or datetime.now()).strftime("%Y%m%dT%H%M%S")
        filename = f"recipe_{ts}.json"

    payload = {"ingredients": chosen_ingredients, "recipe": recipe}
    if prompt is not None:
        payload["prompt"] = prompt

    out_path = outputs_dir / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path
