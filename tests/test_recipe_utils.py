import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.recipe_utils import (
    build_prompt,
    call_llm,
    exclude_by_dietary,
    filter_by_dietary,
    load_ingredient_data,
    retry_on_rate_limit,
    sample_ingredients,
    save_output,
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

    def test_malformed_json_raises_json_decode_error(self, tmp_path):
        (tmp_path / "broken.json").write_text("{not valid json,")
        with pytest.raises(json.JSONDecodeError):
            load_ingredient_data(tmp_path)

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


class TestExcludeByDietary:
    def test_drops_conflicting_items(self, data_dir):
        bank = load_ingredient_data(data_dir)
        kept = exclude_by_dietary(bank, "vegan")
        names = [item["name"] for item in kept["proteins"]]
        # chicken (poultry) and salmon (fish) conflict with vegan; tofu does not
        assert names == ["tofu"]

    def test_keeps_items_without_conflicting_tags(self, data_dir):
        """Unlike the allow-list filter, compatible items are kept even if they
        don't carry the diet's tag explicitly."""
        bank = load_ingredient_data(data_dir)
        # both vegetables are safe for a dairy-free diet -> nothing dropped
        kept = exclude_by_dietary(bank, "dairy-free")
        assert len(kept["vegetables"]) == 2

    def test_unknown_dietary_keeps_everything(self, data_dir):
        bank = load_ingredient_data(data_dir)
        kept = exclude_by_dietary(bank, "keto")
        assert kept == bank

    def test_category_fully_excluded_returns_empty_list(self):
        bank = {"proteins": [{"name": "salmon", "tags": ["fish"]}]}
        kept = exclude_by_dietary(bank, "vegan")
        assert kept["proteins"] == []


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


class FakeRateLimitError(Exception):
    """Stand-in for openai.RateLimitError so tests don't depend on openai."""


class TestRetryOnRateLimit:
    def test_returns_result_without_retry_on_success(self):
        sleeps = []
        calls = []

        @retry_on_rate_limit(exceptions=(FakeRateLimitError,), sleep=sleeps.append)
        def ok():
            calls.append(1)
            return "done"

        assert ok() == "done"
        assert len(calls) == 1
        assert sleeps == []  # no backoff when the first call succeeds

    def test_retries_then_succeeds(self):
        sleeps = []
        attempts = {"n": 0}

        @retry_on_rate_limit(
            exceptions=(FakeRateLimitError,),
            base_delay=1.0,
            backoff_factor=2.0,
            sleep=sleeps.append,
        )
        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise FakeRateLimitError("429")
            return "recovered"

        assert flaky() == "recovered"
        assert attempts["n"] == 3
        # two failures -> two backoff sleeps with exponential growth
        assert sleeps == [1.0, 2.0]

    def test_gives_up_after_max_retries_and_reraises(self):
        sleeps = []

        @retry_on_rate_limit(
            exceptions=(FakeRateLimitError,),
            max_retries=2,
            base_delay=1.0,
            sleep=sleeps.append,
        )
        def always_limited():
            raise FakeRateLimitError("429")

        with pytest.raises(FakeRateLimitError):
            always_limited()
        # initial attempt + 2 retries = 3 calls -> 2 sleeps between them
        assert sleeps == [1.0, 2.0]

    def test_backoff_is_capped_at_max_delay(self):
        sleeps = []

        @retry_on_rate_limit(
            exceptions=(FakeRateLimitError,),
            max_retries=4,
            base_delay=10.0,
            backoff_factor=2.0,
            max_delay=15.0,
            sleep=sleeps.append,
        )
        def always_limited():
            raise FakeRateLimitError("429")

        with pytest.raises(FakeRateLimitError):
            always_limited()
        assert sleeps == [10.0, 15.0, 15.0, 15.0]

    def test_does_not_retry_unrelated_exceptions(self):
        sleeps = []

        @retry_on_rate_limit(exceptions=(FakeRateLimitError,), sleep=sleeps.append)
        def boom():
            raise ValueError("not a rate limit")

        with pytest.raises(ValueError):
            boom()
        assert sleeps == []


class FakeCompletions:
    """Mimics client.chat.completions.create, raising a rate-limit error the
    first `fail_times` calls before returning a canned response."""

    def __init__(self, fail_times, reply="fake recipe"):
        self.fail_times = fail_times
        self.reply = reply
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise FakeRateLimitError("429 rate limited")
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, fail_times=0, reply="fake recipe"):
        self.chat = SimpleNamespace(completions=FakeCompletions(fail_times, reply))


class TestCallLlm:
    def test_returns_reply_from_injected_client(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
        client = FakeClient(fail_times=0, reply="Tofu stir-fry")
        assert call_llm("make me dinner", client=client) == "Tofu stir-fry"
        assert client.chat.completions.calls == 1

    def test_passes_deployment_and_prompt_to_client(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
            )

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        call_llm("use the tofu", client=client)
        assert captured["model"] == "test-deployment"
        assert captured["messages"][-1]["content"] == "use the tofu"

    def test_retries_rate_limit_errors_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
        # avoid real backoff sleeps and use the fake exception type
        monkeypatch.setattr("src.recipe_utils.time.sleep", lambda _s: None)
        monkeypatch.setattr(
            "src.recipe_utils._default_rate_limit_errors",
            lambda: (FakeRateLimitError,),
        )
        client = FakeClient(fail_times=2, reply="recovered recipe")
        assert call_llm("dinner please", client=client) == "recovered recipe"
        assert client.chat.completions.calls == 3


class TestSaveOutput:
    def test_writes_ingredients_and_recipe_as_json(self, tmp_path):
        chosen = {"proteins": [{"name": "tofu", "tags": ["vegan"]}]}
        out_path = save_output(
            chosen, "Tofu stir-fry\n1. cook", tmp_path, filename="out.json"
        )
        assert out_path == tmp_path / "out.json"
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert payload["ingredients"] == chosen
        assert payload["recipe"] == "Tofu stir-fry\n1. cook"
        assert "prompt" not in payload

    def test_includes_prompt_when_given(self, tmp_path):
        out_path = save_output(
            {}, "recipe", tmp_path, prompt="make dinner", filename="out.json"
        )
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert payload["prompt"] == "make dinner"

    def test_creates_outputs_dir_if_missing(self, tmp_path):
        nested = tmp_path / "outputs" / "runs"
        assert not nested.exists()
        out_path = save_output({}, "recipe", nested, filename="out.json")
        assert out_path.exists()
        assert nested.is_dir()

    def test_timestamped_filename_uses_given_timestamp(self, tmp_path):
        ts = datetime(2026, 7, 6, 14, 30, 15)
        out_path = save_output({}, "recipe", tmp_path, timestamp=ts)
        assert out_path.name == "recipe_20260706T143015.json"
