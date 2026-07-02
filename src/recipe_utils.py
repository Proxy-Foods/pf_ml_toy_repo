"""Core logic for the recipe generator toy project.

Kept separate from the notebook so it can be unit tested and reused.
"""
import json
import os
import random
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


def call_llm(prompt: str) -> str:
    """Send the prompt to the configured Azure AI Foundry deployment and return the reply text."""
    client = get_client()
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You are a concise, practical home-cooking assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=500,
    )
    return response.choices[0].message.content
