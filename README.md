# Recipe Generator — Toy Repo

A small sandbox repo for practicing a real dev workflow: branch off a Jira ticket, make a change,
commit, push, and open a PR.

## What it does

`notebooks/recipe_generator.ipynb`:
1. Dynamically loads every ingredient JSON file in `data/` (no code changes needed to add a category).
2. Samples a few ingredients per category.
3. Builds a prompt embedding those ingredients as JSON.
4. Calls an LLM deployed on **Azure AI Foundry** (Azure OpenAI) to generate a recipe.

## Project structure

```
.
├── data/                     # ingredient JSON files, loaded dynamically
│   ├── proteins.json
│   ├── vegetables.json
│   ├── spices_and_herbs.json
│   └── pantry_staples.json
├── notebooks/
│   └── recipe_generator.ipynb # thin notebook that imports src/recipe_utils.py
├── src/
│   └── recipe_utils.py        # loading, sampling, filtering, prompt-building, LLM call
├── tests/
│   └── test_recipe_utils.py   # pytest unit tests for src/recipe_utils.py
├── conftest.py                 # makes `src` importable when running pytest
├── .env.example               # copy to .env and fill in your Azure values
├── requirements.txt
└── CONTRIBUTING.md            # branch / commit / PR workflow
```

## Setup

```bash
./setup.sh                     # creates .venv, installs deps, copies .env.example -> .env
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

Then open `.env` and fill in your real Azure AI Foundry values, and run:

```bash
jupyter notebook notebooks/recipe_generator.ipynb
```

### Required environment variables (`.env`)

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Your Azure AI Foundry / Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | API key from the Foundry project's "Keys and Endpoint" page |
| `AZURE_OPENAI_DEPLOYMENT` | Your model deployment name (not the base model name) |
| `AZURE_OPENAI_API_VERSION` | API version, e.g. `2024-10-21` |

## Adding a new ingredient category

Drop a new JSON file into `data/` shaped like:

```json
{
  "category": "desserts",
  "items": [
    {"name": "dark chocolate", "tags": ["sweet", "bitter"]}
  ]
}
```

It will be picked up automatically the next time the notebook runs.

## Running tests

Core logic (loading JSON, sampling, dietary filtering, prompt building) lives in
`src/recipe_utils.py` and is covered by unit tests — no Azure credentials needed to run them:

```bash
pytest
```

## Workflow

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the branch-naming, commit, and PR conventions this repo
is meant to exercise (e.g. for an AI coding agent working off Jira tickets).
