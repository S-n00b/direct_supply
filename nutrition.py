"""Nutrition matching and macro estimation for meal-plan recipes."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

COOKING_METHODS = {
    "raw",
    "cooked",
    "boiled",
    "baked",
    "fried",
    "sauteed",
    "roasted",
    "grilled",
    "steamed",
    "braised",
    "microwaved",
    "broiled",
    "poached",
    "blanched",
    "stewed",
    "simmered",
    "toasted",
    "reheated",
}

PREP_FORMS = {
    "diced",
    "chopped",
    "sliced",
    "minced",
    "shredded",
    "florets",
    "ground",
    "mashed",
    "spears",
    "stalks",
    "leaves",
    "pieces",
    "whole",
    "crushed",
    "peeled",
    "boneless",
    "skinless",
    "bone-in",
    "drained",
}

PACKAGING = {
    "frozen",
    "canned",
    "dried",
    "dehydrated",
    "freeze-dried",
    "fresh",
    "refrigerated",
    "ready-to-heat",
    "ready-to-drink",
    "shelf stable",
    "drained",
    "unprepared",
    "pickled",
}

SALT_FLAGS = {"with salt", "without salt", "salted", "unsalted", "no salt added", "low sodium"}

SIZE_DESCRIPTORS = {"large", "small", "medium", "extra", "jumbo"}

COLOR_DESCRIPTORS = {"red", "green", "yellow", "white", "brown", "black", "blue"}

STOP_WORDS = {"and", "or", "the", "a", "an", "to", "taste", "with", "without", "ns"}

INGREDIENT_ALIASES: dict[str, list[str]] = {
    "olive oil": ["oil", "olive"],
    "red bell pepper": ["peppers", "sweet", "red"],
    "bell pepper": ["peppers", "sweet"],
    "almond milk": ["beverages", "almond", "milk"],
    "soy sauce": ["soy", "sauce"],
    "scallion": ["onions", "spring"],
    "scallions": ["onions", "spring"],
    "rolled oats": ["oats"],
    "corn tortillas": ["tortilla", "corn"],
    "small corn tortillas": ["tortilla", "corn"],
    "spinach leaves": ["spinach", "raw"],
    "large eggs": ["eggs", "whole"],
    "ginger": ["ginger", "root"],
    "broccoli florets": ["broccoli"],
    "chicken breast": ["chicken", "breast"],
    "salt and pepper": ["salt"],
    "blueberries": ["blueberries"],
    "chia seeds": ["chia", "seeds"],
    "diced onion": ["onions", "yellow"],
    "diced tomato": ["tomatoes", "red", "ripe", "raw"],
    "honey": ["honey"],
    "garlic": ["garlic"],
}

PREPARED_PRODUCT_MODIFIERS = {
    "sauce",
    "butter",
    "dressing",
    "dip",
    "spread",
    "jam",
    "jelly",
    "concentrate",
}

COMPOSITE_DISH_KEYWORDS = {
    "taco",
    "casserole",
    "salad",
    "rings",
    "roll",
    "sandwich",
    "soup",
    "stew",
    "pizza",
    "burger",
    "cake",
    "pie",
    "cookie",
    "bread",
    "muffin",
    "dip",
    "dressing",
    "slaw",
    "nacho",
    "burrito",
    "wrap",
    "noodle",
    "pasta",
    "curry",
    "stir fried",
    "beef",
    "pork",
    "cheese",
}

TITLE_COOKING_HINTS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"stir[- ]?fry|stir fry", re.I), ["sauteed", "fried"]),
    (re.compile(r"omelette|omelet|scramble", re.I), ["cooked", "fried"]),
    (re.compile(r"roast", re.I), ["roasted"]),
    (re.compile(r"grill", re.I), ["grilled"]),
    (re.compile(r"bake|baked", re.I), ["baked"]),
    (re.compile(r"steam", re.I), ["steamed"]),
    (re.compile(r"boil", re.I), ["boiled"]),
    (re.compile(r"soup|stew", re.I), ["cooked", "boiled", "stewed"]),
    (re.compile(r"overnight|salad|smoothie|raw|no[- ]?bake", re.I), ["raw"]),
]

PARENTHETICAL_PATTERN = re.compile(r"\s*\([^)]*\)")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass
class MacroValues:
    calories: float
    protein: float
    carbs: float
    fat: float


@dataclass
class FoodRow:
    fdc_id: str
    description: str
    macros: MacroValues
    segments: list[str]
    tokens: set[str]
    cooking_method: str | None
    prep_forms: set[str]
    packaging: set[str]
    salt_flag: str | None
    variety_tokens: set[str]


@dataclass
class IngredientAttrs:
    raw_name: str
    normalized_name: str
    food_tokens: list[str]
    cooking_methods: list[str]
    prep_forms: set[str]
    packaging: set[str]
    colors: set[str]
    sizes: set[str]
    search_text: str


@dataclass
class MatchResult:
    fdc_id: str
    matched_description: str
    confidence: float
    score: float
    macros_per_100g: MacroValues


class NutritionDatabase:
    """Loads macro CSV and indexes rows for ingredient matching."""

    def __init__(self, csv_path: Path) -> None:
        self.rows: list[FoodRow] = []
        self._token_index: dict[str, list[int]] = {}
        self._load(csv_path)

    def _load(self, csv_path: Path) -> None:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for record in reader:
                description = record["description"].strip()
                segments = [segment.strip().lower() for segment in description.split(",")]
                tokens = self._tokenize(" ".join(segments))

                cooking_method = None
                prep_forms: set[str] = set()
                packaging: set[str] = set()
                salt_flag = None
                variety_tokens: set[str] = set()

                for segment in segments:
                    segment_tokens = self._tokenize(segment)
                    if segment in COOKING_METHODS or any(
                        token in COOKING_METHODS for token in segment_tokens
                    ):
                        for token in segment_tokens:
                            if token in COOKING_METHODS:
                                cooking_method = token
                                break
                    for token in segment_tokens:
                        if token in PREP_FORMS:
                            prep_forms.add(token)
                        if token in PACKAGING:
                            packaging.add(token)
                        if token in COLOR_DESCRIPTORS | SIZE_DESCRIPTORS:
                            variety_tokens.add(token)
                    for salt in SALT_FLAGS:
                        if salt in segment:
                            salt_flag = salt
                            break

                row = FoodRow(
                    fdc_id=record["fdc_id"],
                    description=description,
                    macros=MacroValues(
                        calories=self._float_or_zero(record.get("calories")),
                        protein=self._float_or_zero(record.get("proteinInGrams")),
                        carbs=self._float_or_zero(record.get("carbohydratesInGrams")),
                        fat=self._float_or_zero(record.get("fatInGrams")),
                    ),
                    segments=segments,
                    tokens=tokens,
                    cooking_method=cooking_method,
                    prep_forms=prep_forms,
                    packaging=packaging,
                    salt_flag=salt_flag,
                    variety_tokens=variety_tokens,
                )
                index = len(self.rows)
                self.rows.append(row)
                for token in tokens:
                    self._token_index.setdefault(token, []).append(index)

    @staticmethod
    def _float_or_zero(value: str | None) -> float:
        if value is None or value == "":
            return 0.0
        return float(value)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in TOKEN_PATTERN.findall(text.lower()) if token not in STOP_WORDS}

    def retrieve_candidates(self, food_tokens: list[str]) -> list[FoodRow]:
        if not food_tokens:
            return []

        index_sets: list[set[int]] = []
        for token in food_tokens:
            matches: set[int] = set()
            singular = _singularize(token)
            for lookup in {token, singular}:
                matches.update(self._token_index.get(lookup, []))
            if not matches:
                return []
            index_sets.append(matches)

        candidate_indices = set.intersection(*index_sets)
        if not candidate_indices and len(index_sets) > 1:
            required = len(index_sets) - 1
            counts: dict[int, int] = {}
            for index_set in index_sets:
                for index in index_set:
                    counts[index] = counts.get(index, 0) + 1
            candidate_indices = {
                index for index, hits in counts.items() if hits >= required
            }

        if not candidate_indices:
            return []

        return [self.rows[index] for index in sorted(candidate_indices)]


def _singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def normalize_ingredient_name(name: str) -> str:
    cleaned = PARENTHETICAL_PATTERN.sub("", name).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def infer_cooking_methods_from_title(title: str) -> list[str]:
    methods: list[str] = []
    for pattern, hints in TITLE_COOKING_HINTS:
        if pattern.search(title):
            methods.extend(hints)
    return methods or ["raw"]


def parse_ingredient_attrs(name: str, title_cooking_methods: list[str]) -> IngredientAttrs:
    normalized = normalize_ingredient_name(name)

    alias_tokens = INGREDIENT_ALIASES.get(normalized)
    if alias_tokens is None:
        for alias, tokens in INGREDIENT_ALIASES.items():
            if alias in normalized or normalized in alias:
                alias_tokens = tokens
                break

    tokens = TOKEN_PATTERN.findall(normalized)
    cooking_methods: list[str] = []
    prep_forms: set[str] = set()
    packaging: set[str] = set()
    colors: set[str] = set()
    sizes: set[str] = set()
    food_tokens: list[str] = []

    for token in tokens:
        if token in COOKING_METHODS:
            cooking_methods.append(token)
        elif token in PREP_FORMS:
            prep_forms.add(token)
        elif token in PACKAGING:
            packaging.add(token)
        elif token in COLOR_DESCRIPTORS:
            colors.add(token)
        elif token in SIZE_DESCRIPTORS:
            sizes.add(token)
        elif token not in STOP_WORDS:
            food_tokens.append(token)

    if alias_tokens:
        food_tokens = list(alias_tokens)
    elif not food_tokens:
        food_tokens = [token for token in tokens if token not in STOP_WORDS]

    if "red" in colors and any("pepper" in token for token in food_tokens + tokens):
        food_tokens = ["peppers", "sweet", "red"]

    resolved_methods = cooking_methods or title_cooking_methods

    return IngredientAttrs(
        raw_name=name,
        normalized_name=normalized,
        food_tokens=food_tokens,
        cooking_methods=resolved_methods,
        prep_forms=prep_forms,
        packaging=packaging,
        colors=colors,
        sizes=sizes,
        search_text=normalized,
    )


def _primary_segment_matches(candidate: FoodRow, food_tokens: list[str]) -> bool:
    if not candidate.segments or not food_tokens:
        return False
    first_segment = candidate.segments[0].strip()
    primary = _singularize(food_tokens[0])
    first_word = first_segment.split()[0] if first_segment else ""
    if _singularize(first_word) == primary:
        return True
    return _singularize(first_segment) == primary


def _is_simple_ingredient(attrs: IngredientAttrs) -> bool:
    return len(attrs.food_tokens) <= 2


def _score_candidate(candidate: FoodRow, attrs: IngredientAttrs) -> float:
    score = 0.0
    food_set = set(attrs.food_tokens)
    singular_food = {_singularize(token) for token in food_set}

    food_overlap = len(candidate.tokens & (food_set | singular_food))
    score += food_overlap * 40.0

    if food_set:
        coverage = food_overlap / len(food_set)
        score += coverage * 25.0
        if coverage < 1.0:
            score -= (1.0 - coverage) * 30.0

    if _primary_segment_matches(candidate, attrs.food_tokens):
        score += 35.0
    elif _is_simple_ingredient(attrs):
        score -= 20.0

    if _is_simple_ingredient(attrs) and len(candidate.segments) <= 3:
        score += 12.0

    description_lower = candidate.description.lower()
    if _is_simple_ingredient(attrs):
        for keyword in COMPOSITE_DISH_KEYWORDS:
            if keyword in description_lower:
                score -= 35.0
                break
        if " and " in candidate.segments[0]:
            score -= 30.0
        for modifier in PREPARED_PRODUCT_MODIFIERS:
            if modifier in candidate.tokens and modifier not in food_set:
                score -= 40.0
                break

    target_methods = set(attrs.cooking_methods)
    if candidate.cooking_method:
        if candidate.cooking_method in target_methods:
            score += 25.0
        elif "raw" in target_methods and candidate.cooking_method != "raw":
            score -= 15.0
        elif target_methods and candidate.cooking_method not in target_methods:
            score -= 10.0
    elif "raw" in target_methods:
        score += 8.0

    if attrs.prep_forms and candidate.prep_forms:
        overlap = len(attrs.prep_forms & candidate.prep_forms)
        score += overlap * 10.0

    if attrs.colors and candidate.variety_tokens:
        overlap = len(attrs.colors & candidate.variety_tokens)
        score += overlap * 8.0

    if not attrs.packaging:
        if "raw" in candidate.tokens or candidate.cooking_method == "raw":
            score += 8.0
        if candidate.packaging & {"frozen", "canned", "dried", "dehydrated", "pickled"}:
            score -= 12.0
    else:
        overlap = len(attrs.packaging & candidate.packaging)
        score += overlap * 10.0

    if "chocolate" in candidate.tokens and "chocolate" not in food_set:
        score -= 25.0
    if "pickled" in candidate.packaging and "pickled" not in attrs.packaging:
        score -= 18.0
    if "vanilla" in candidate.tokens and "vanilla" not in food_set:
        score -= 8.0

    if "raw" in food_set:
        if "raw" in candidate.tokens or candidate.cooking_method == "raw":
            score += 25.0
        if candidate.packaging & {"canned", "frozen", "dried"}:
            score -= 20.0

    if "whole" in food_set and "whole" in candidate.tokens:
        score += 20.0
    if "yolk" in candidate.tokens and "whole" in food_set:
        score -= 30.0
    if "white" in candidate.tokens and "whole" in food_set and "egg" in candidate.tokens:
        score -= 30.0

    similarity = SequenceMatcher(
        None, attrs.search_text, candidate.description.lower()
    ).ratio()
    score += similarity * 10.0

    if attrs.sizes and candidate.variety_tokens:
        overlap = len(attrs.sizes & candidate.variety_tokens)
        score += overlap * 3.0

    return score


def _confidence_from_scores(top_score: float, second_score: float | None) -> float:
    if top_score <= 0:
        return 0.0
    if second_score is None:
        return round(min(1.0, top_score / 120.0), 2)
    gap = top_score - second_score
    base = min(1.0, top_score / 120.0)
    gap_bonus = min(0.25, gap / 80.0)
    return round(min(1.0, base + gap_bonus), 2)


def match_ingredient(
    db: NutritionDatabase,
    name: str,
    title_cooking_methods: list[str],
    *,
    max_alternatives: int = 3,
) -> tuple[MatchResult | None, list[MatchResult]]:
    attrs = parse_ingredient_attrs(name, title_cooking_methods)
    candidates = db.retrieve_candidates(attrs.food_tokens)
    if not candidates:
        return None, []

    scored: list[tuple[FoodRow, float]] = [
        (candidate, _score_candidate(candidate, attrs)) for candidate in candidates
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    results: list[MatchResult] = []
    for candidate, score in scored[: max_alternatives + 1]:
        results.append(
            MatchResult(
                fdc_id=candidate.fdc_id,
                matched_description=candidate.description,
                confidence=0.0,
                score=score,
                macros_per_100g=candidate.macros,
            )
        )

    if not results:
        return None, []

    second_score = results[1].score if len(results) > 1 else None
    best = results[0]
    best.confidence = _confidence_from_scores(best.score, second_score)
    alternatives = results[1 : max_alternatives + 1]
    for alt in alternatives:
        alt.confidence = _confidence_from_scores(alt.score, None)
    return best, alternatives


def scale_macros(macros: MacroValues, grams: float) -> MacroValues:
    factor = grams / 100.0
    return MacroValues(
        calories=round(macros.calories * factor, 2),
        protein=round(macros.protein * factor, 2),
        carbs=round(macros.carbs * factor, 2),
        fat=round(macros.fat * factor, 2),
    )


def sum_macros(values: list[MacroValues]) -> MacroValues:
    return MacroValues(
        calories=round(sum(item.calories for item in values), 2),
        protein=round(sum(item.protein for item in values), 2),
        carbs=round(sum(item.carbs for item in values), 2),
        fat=round(sum(item.fat for item in values), 2),
    )


def divide_macros(macros: MacroValues, servings: int) -> MacroValues:
    if servings <= 0:
        return macros
    return MacroValues(
        calories=round(macros.calories / servings, 2),
        protein=round(macros.protein / servings, 2),
        carbs=round(macros.carbs / servings, 2),
        fat=round(macros.fat / servings, 2),
    )


def macros_to_dict(macros: MacroValues) -> dict[str, float]:
    return {
        "calories": macros.calories,
        "protein": macros.protein,
        "carbs": macros.carbs,
        "fat": macros.fat,
    }


def match_result_to_dict(result: MatchResult) -> dict[str, Any]:
    return {
        "fdc_id": result.fdc_id,
        "matchedDescription": result.matched_description,
        "confidence": result.confidence,
    }


def estimate_recipe_nutrition(
    db: NutritionDatabase,
    title: str,
    ingredients: dict[str, float],
    yield_: int,
) -> dict[str, Any]:
    title_methods = infer_cooking_methods_from_title(title)
    by_ingredient: list[dict[str, Any]] = []
    scaled_macros: list[MacroValues] = []

    for name, grams in ingredients.items():
        best, alternatives = match_ingredient(db, name, title_methods)
        entry: dict[str, Any] = {
            "name": name,
            "grams": grams,
            "fdc_id": None,
            "matchedDescription": None,
            "confidence": 0.0,
            "calories": 0.0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
            "alternatives": [],
        }

        if best:
            scaled = scale_macros(best.macros_per_100g, grams)
            scaled_macros.append(scaled)
            entry.update(
                {
                    "fdc_id": best.fdc_id,
                    "matchedDescription": best.matched_description,
                    "confidence": best.confidence,
                    **macros_to_dict(scaled),
                    "alternatives": [match_result_to_dict(alt) for alt in alternatives],
                }
            )
        by_ingredient.append(entry)

    total = sum_macros(scaled_macros)
    per_serving = divide_macros(total, yield_)

    return {
        "total": macros_to_dict(total),
        "perServing": macros_to_dict(per_serving),
        "byIngredient": by_ingredient,
    }


def enrich_recipes_with_nutrition(
    recipes: list[dict[str, Any]],
    csv_path: Path,
) -> list[dict[str, Any]]:
    db = NutritionDatabase(csv_path)
    enriched: list[dict[str, Any]] = []
    for recipe in recipes:
        payload = dict(recipe)
        payload["nutrition"] = estimate_recipe_nutrition(
            db,
            recipe["title"],
            recipe["ingredients"],
            recipe["yield"],
        )
        enriched.append(payload)
    return enriched
