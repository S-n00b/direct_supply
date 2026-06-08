"""Meal-plan JSON cleaner, refactorer, and validator for the Direct Supply KATA."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

INGREDIENT_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*g\s+(.*)$", re.IGNORECASE)
TRAILING_COMMA_PATTERN = re.compile(r",(\s*[}\]])")


class RawRecipe(BaseModel):
    """Recipe with ingredients stored as raw strings (pre-refactor)."""

    model_config = ConfigDict(populate_by_name=True)

    title: str
    yield_: int = Field(alias="yield")
    ingredients: list[str]


class Recipe(BaseModel):
    """Validated recipe with ingredients as {name: grams} dict."""

    model_config = ConfigDict(populate_by_name=True)

    title: str
    yield_: int = Field(alias="yield")
    ingredients: dict[str, float]


def clean_json(raw_text: str) -> list[dict[str, Any]]:
    """Repair common JSON syntax issues and return normalized data."""
    # Normalize exotic whitespace (tabs, en/em spaces, etc.) to regular spaces.
    normalized = "".join(" " if ord(ch) > 127 and ch.isspace() else ch for ch in raw_text)
    normalized = normalized.replace("\t", "  ")
    repaired = TRAILING_COMMA_PATTERN.sub(r"\1", normalized)
    data = json.loads(repaired)
    return json.loads(json.dumps(data, indent=2))


def parse_ingredient(ingredient: str) -> tuple[str, float]:
    """Split an ingredient string like '30g olive oil' into ('olive oil', 30.0)."""
    match = INGREDIENT_PATTERN.match(ingredient)
    if not match:
        raise ValueError(f"Could not parse ingredient: {ingredient!r}")
    grams = float(match.group(1))
    name = match.group(2).strip()
    return name, grams


def refactor_json(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert each recipe's ingredients array into a {name: grams} dictionary."""
    refactored: list[dict[str, Any]] = []
    for recipe in data:
        ingredients: dict[str, float] = {}
        for item in recipe["ingredients"]:
            name, grams = parse_ingredient(item)
            ingredients[name] = grams
        refactored.append(
            {
                "title": recipe["title"],
                "yield": recipe["yield"],
                "ingredients": ingredients,
            }
        )
    return refactored


def process_meal_plan(input_path: Path) -> tuple[list[dict[str, Any]], list[Recipe]]:
    """Clean, validate, and refactor a single meal-plan JSON file."""
    raw_text = input_path.read_text(encoding="utf-8")
    cleaned = clean_json(raw_text)

    cleaned_path = input_path.with_name(f"{input_path.stem}-cleaned.json")
    cleaned_path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    print(f"Wrote cleaned JSON: {cleaned_path.name}")

    raw_recipes = [RawRecipe.model_validate(recipe) for recipe in cleaned]
    refactored = refactor_json(cleaned)
    recipes = [Recipe.model_validate(recipe) for recipe in refactored]
    return cleaned, recipes


def main() -> None:
    root = Path(__file__).parent
    demo_inputs = [root / "meal-plan.json", root / "meal-plan-2.json"]
    primary = root / "meal-plan.json"

    recipes: list[Recipe] = []
    for input_path in demo_inputs:
        if not input_path.exists():
            print(f"Skipping missing file: {input_path.name}")
            continue
        _, recipe_list = process_meal_plan(input_path)
        if input_path == primary:
            recipes = recipe_list

    if recipes:
        output_path = root / "meal-plan-refactored.json"
        payload = [recipe.model_dump(by_alias=True) for recipe in recipes]
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote refactored JSON: {output_path.name} ({len(recipes)} recipes)")


if __name__ == "__main__":
    main()
