import json

import pytest

from src.recipe_utils import (
    build_prompt,
    filter_by_dietary,
    load_ingredient_data,
    sample_ingredients,
)


@pytest.fixture
def data_dir(tmp_path):
    """A temp data/ dir with two small ingredient JSON files."""
    proteins = {
        "category": "proteins",
        "items": [
            {"name": "chicken breast", "tags": ["poultry"]},
            {"name": "tofu", "tags": ["vegan", "vegetarian"]},
            {"name": "salmon", "tags": ["fish"]},
        ],
    }
    veg = {
        "category": "vegetables",
        "items": [
            {"name": "broccoli", "tags": ["vegan", "vegetarian"]},
            {"name": "carrot", "tags": ["vegan", "vegetarian"]},
        ],
    }
    (tmp_path / "proteins.json").write_text(json.dumps(proteins))
    (tmp_path / "vegetables.json").write_text(json.dumps(veg))
    return tmp_path


class TestLoadIngredientData:
    def test_loads_all_json_files(self, data_dir):
        bank = load_ingredient_data(data_dir)
        assert set(bank.keys()) == {"proteins", "vegetables"}
        assert len(bank["proteins"]) == 3
        assert len(bank["vegetables"]) == 2

    def test_uses_filename_stem_when_category_missing(self, tmp_path):
        (tmp_path / "spices.json").write_text(json.dumps({"items": [{"name": "cumin", "tags": []}]}))
        bank = load_ingredient_data(tmp_path)
        assert "spices" in bank
        assert bank["spices"][0]["name"] == "cumin"

    def test_empty_dir_returns_empty_dict(self, tmp_path):
        assert load_ingredient_data(tmp_path) == {}

    def test_missing_items_key_treated_as_empty_list(self, tmp_path):
        (tmp_path / "empty.json").write_text(json.dumps({"category": "empty"}))
        bank = load_ingredient_data(tmp_path)
        assert bank["empty"] == []


class TestSampleIngredients:
    def test_respects_per_category_limit(self, data_dir):
        bank = load_ingredient_data(data_dir)
        sampled = sample_ingredients(bank, per_category=1, seed=1)
        assert len(sampled["proteins"]) == 1
        assert len(sampled["vegetables"]) == 1

    def test_never_samples_more_than_available(self, data_dir):
        bank = load_ingredient_data(data_dir)
        sampled = sample_ingredients(bank, per_category=10, seed=1)
        # only 3 proteins and 2 vegetables exist
        assert len(sampled["proteins"]) == 3
        assert len(sampled["vegetables"]) == 2

    def test_seed_gives_deterministic_output(self, data_dir):
        bank = load_ingredient_data(data_dir)
        first = sample_ingredients(bank, per_category=2, seed=42)
        second = sample_ingredients(bank, per_category=2, seed=42)
        assert first == second

    def test_sampled_items_come_from_original_bank(self, data_dir):
        bank = load_ingredient_data(data_dir)
        sampled = sample_ingredients(bank, per_category=2, seed=7)
        for name, items in sampled.items():
            for item in items:
                assert item in bank[name]


class TestFilterByDietary:
    def test_filters_out_non_matching_items(self, data_dir):
        bank = load_ingredient_data(data_dir)
        filtered = filter_by_dietary(bank, "vegan")
        assert all("vegan" in item["tags"] for item in filtered["proteins"])
        assert len(filtered["proteins"]) == 1  # only tofu
        assert len(filtered["vegetables"]) == 2  # both are vegan

    def test_category_with_no_matches_returns_empty_list(self, data_dir):
        bank = load_ingredient_data(data_dir)
        filtered = filter_by_dietary(bank, "gluten-free")
        assert filtered["proteins"] == []
        assert filtered["vegetables"] == []


class TestBuildPrompt:
    def test_includes_ingredients_as_json(self):
        chosen = {"proteins": [{"name": "tofu", "tags": ["vegan"]}]}
        prompt = build_prompt(chosen)
        assert "tofu" in prompt
        assert json.dumps(chosen, indent=2) in prompt

    def test_includes_cuisine_constraint_when_given(self):
        prompt = build_prompt({}, cuisine="Thai")
        assert "Cuisine style: Thai." in prompt

    def test_includes_dietary_constraint_when_given(self):
        prompt = build_prompt({}, dietary="vegan")
        assert "Dietary requirement: vegan." in prompt

    def test_omits_constraints_when_not_given(self):
        prompt = build_prompt({})
        assert "Cuisine style:" not in prompt
        assert "Dietary requirement:" not in prompt
