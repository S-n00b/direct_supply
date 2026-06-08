# Direct Supply KATA — Interview Playbook

> **Purpose:** Predict the top 5 live-coding asks, sketch minimalist Python solutions with ample comments, and document improvement ideas for the app currently running at `http://localhost:8000`.
>
> **How to use this doc:** Talk through the comments out loud during the interview. The code below is intentionally *pseudo-implementation* — it shows problem-solving structure, not production polish.

---

## Current App Snapshot (port 8000 review)

| Layer | What works today |
|---|---|
| **Backend** | `backend.py` — one-shot build step: `clean_json` → pydantic validate → `refactor_json` → writes static JSON |
| **Data** | `meal-plan-refactored.json` — 3 recipes, ingredients as `{name: grams}` dict |
| **Frontend** | `index.html` — hash routing (`#/`, `#/recipe/0`), Tailwind, fetches static JSON |
| **Hosting** | `python -m http.server 8000` locally; GitHub Pages for static deploy |

**DS domain lens:** Direct Supply's food-order platforms care about *recipes → ingredient demand → inventory → purchase orders*. Every ask below maps to that pipeline.

---

## Top 5 Likely Interview Requests

### 1. Scale a Recipe for a Different Yield

**Why they'll ask:** Kitchens rarely cook exactly the recipe's default yield. A 2-serving stir-fry scaled to 50 residents is core food-service math.

**Likely prompt:** *"We need to feed 10 people using the Chicken Stir-Fry recipe. Scale the ingredients."*

**Plan of attack:**

```python
# backend.py — add near existing Recipe model
# KEY INSIGHT: scaling is linear. multiply every gram by (target_yield / original_yield).
# We already store grams as floats in Recipe.ingredients — no re-parsing needed.

def scale_recipe(recipe: Recipe, target_yield: int) -> Recipe:
    """
    Return a new Recipe with ingredient weights adjusted for target_yield.

    Example: Chicken Stir-Fry yields 2, target 10
      scale_factor = 10 / 2 = 5.0
      olive oil: 30g * 5 = 150g
    """
    if target_yield <= 0:
        raise ValueError("target_yield must be positive")

    scale_factor = target_yield / recipe.yield_

    scaled_ingredients = {
        name: round(grams * scale_factor, 1)   # round for readability; keep float internally
        for name, grams in recipe.ingredients.items()
    }

    # Return NEW Recipe — don't mutate the original (immutable pattern, easier to reason about)
    return Recipe(
        title=recipe.title,
        yield_=target_yield,
        ingredients=scaled_ingredients,
    )


# --- INTERVIEW TALKING POINTS ---
# 1. Mention edge case: target_yield == recipe.yield_ → scale_factor 1.0, no-op
# 2. Mention rounding: food service may round to nearest 5g for bulk items — out of scope for KATA
# 3. Frontend hook: add a <input type="number"> on detail page, re-render table client-side
#    OR expose scale_recipe via a tiny stdlib HTTP API (see Request #4)
```

**Where it plugs in:** `Recipe` model already has `yield_` and `ingredients: dict[str, float]`. No schema change needed.

---

### 2. Generate a Consolidated Shopping List (Multi-Recipe)

**Why they'll ask:** This is the bridge from *recipes* to *food orders*. A dietitian picks 3 recipes for the week → procurement needs one purchase list.

**Likely prompt:** *"Given these recipe titles, produce a single shopping list with total grams per ingredient."*

**Plan of attack:**

```python
# backend.py — operates on list[Recipe], returns dict[str, float]
# KEY INSIGHT: same ingredient name across recipes → SUM the grams.
# Watch out: "olive oil" appears in Stir-Fry AND Omelette — that's correct to merge.

def build_shopping_list(recipes: list[Recipe]) -> dict[str, float]:
    """
    Aggregate ingredient demand across multiple recipes.

    Input:  [Chicken Stir-Fry, Veggie Omelette]
    Output: {"olive oil": 45.0, "chicken breast": 200.0, ...}
            # 30g + 15g olive oil merged
    """
    shopping_list: dict[str, float] = {}

    for recipe in recipes:
        for name, grams in recipe.ingredients.items():
            # .get() with default 0 — first occurrence sets, subsequent ones add
            shopping_list[name] = shopping_list.get(name, 0.0) + grams

    return shopping_list


# --- BONUS: filter by selected recipe titles (interviewer may specify subset) ---
def shopping_list_for_titles(all_recipes: list[Recipe], titles: list[str]) -> dict[str, float]:
    """Only include recipes whose title is in the requested set."""
    selected = [r for r in all_recipes if r.title in titles]
    # Talk through: what if title not found? return partial list + warn, or raise?
    if len(selected) != len(titles):
        missing = set(titles) - {r.title for r in selected}
        print(f"Warning: recipes not found: {missing}")  # or raise ValueError
    return build_shopping_list(selected)


# --- INTERVIEW TALKING POINTS ---
# 1. This is the "order quantity" step before checking warehouse inventory
# 2. Ingredient normalization is a follow-up problem (see Possible Enhancements)
# 3. Frontend: checkbox on list page → "Generate Shopping List" → new #/shopping route
# 4. Could sort output by grams descending (already done on detail page — reuse pattern)
```

**Where it plugs in:** Load recipes from `meal-plan-refactored.json` or in-memory `list[Recipe]` after `process_meal_plan()`.

---

### 3. Inventory Check — Can We Make This Recipe?

**Why they'll ask:** Direct Supply food-order platforms track on-hand stock. Before scheduling a recipe, staff need to know if inventory covers it.

**Likely prompt:** *"Here's what we have in the pantry. Can we make the Veggie Omelette? What's missing?"*

**Plan of attack:**

```python
# backend.py — pure function, no DB needed (in-memory dict per KATA instructions)

def check_inventory(
    recipe: Recipe,
    on_hand: dict[str, float],   # {"large eggs": 80.0, "olive oil": 50.0, ...}
) -> dict:
    """
    Compare recipe demand vs pantry stock.

    Returns a simple report dict — easy to JSON-serialize for frontend or MCP agent.
    """
    sufficient = []
    insufficient = []   # list of {name, need, have, shortfall}
    missing = []        # ingredient not in pantry at all

    for name, need_grams in recipe.ingredients.items():
        have_grams = on_hand.get(name)  # None if not tracked

        if have_grams is None:
            missing.append({"ingredient": name, "need": need_grams})
        elif have_grams >= need_grams:
            sufficient.append(name)
        else:
            insufficient.append({
                "ingredient": name,
                "need": need_grams,
                "have": have_grams,
                "shortfall": need_grams - have_grams,  # grams to order
            })

    can_make = len(insufficient) == 0 and len(missing) == 0

    return {
        "recipe": recipe.title,
        "can_make": can_make,
        "sufficient": sufficient,
        "insufficient": insufficient,
        "missing": missing,
    }


# --- EXTENSION THEY MIGHT ASK NEXT: "What should we order?" ---
def generate_reorder_list(report: dict) -> dict[str, float]:
    """Extract shortfall grams for anything we can't make."""
    reorder = {}
    for item in report["insufficient"]:
        reorder[item["ingredient"]] = item["shortfall"]
    for item in report["missing"]:
        reorder[item["ingredient"]] = item["need"]
    return reorder


# --- INTERVIEW TALKING POINTS ---
# 1. Start with exact name matching — mention fuzzy matching as future work
# 2. This is the inverse of shopping list: demand vs supply
# 3. Pydantic model for report? Optional — dict is fine for KATA speed
# 4. Real DS platform would persist on_hand in a DB; KATA says in-memory dict is fine
```

**Where it plugs in:** New function alongside `refactor_json`. Demo with a hardcoded `PANTRY` dict at bottom of `backend.py` or in `if __name__` block.

---

### 4. Add a Live API Endpoint (stdlib HTTP server)

**Why they'll ask:** KATA says in-memory dicts, no full DB — but they may want you to *add a recipe at runtime* or expose data for an agent/MCP tool. A 20-line stdlib server proves you can extend without frameworks.

**Likely prompt:** *"Add an endpoint to list recipes and one to add a new recipe."*

**Plan of attack:**

```python
# api.py (new file) OR append to backend.py — keep separate for clarity in interview
# Uses only stdlib: http.server, json
# Reuse existing pydantic Recipe model for validation

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from backend import Recipe, process_meal_plan
from pathlib import Path

# --- IN-MEMORY STORE (per KATA instructions) ---
RECIPES: list[Recipe] = []   # populated on startup


def load_recipes_into_memory():
    """Boot-time: load from meal-plan-refactored.json into RECIPES list."""
    global RECIPES
    path = Path(__file__).parent / "meal-plan-refactored.json"
    raw = json.loads(path.read_text())
    RECIPES = [Recipe.model_validate(r) for r in raw]


class RecipeHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        # GET /recipes → return all recipes as JSON
        if self.path == "/recipes":
            payload = [r.model_dump(by_alias=True) for r in RECIPES]
            self._json_response(200, payload)
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        # POST /recipes → add a new recipe (body must match Recipe schema)
        if self.path == "/recipes":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            # pydantic validates shape — this is the agent/MCP readiness story
            new_recipe = Recipe.model_validate(body)
            RECIPES.append(new_recipe)

            # OPTIONAL: persist back to JSON file so frontend can re-fetch
            # Path("meal-plan-refactored.json").write_text(...)

            self._json_response(201, new_recipe.model_dump(by_alias=True))
        else:
            self._json_response(404, {"error": "not found"})

    def _json_response(self, status: int, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")  # if frontend on different port
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# if __name__ == "__main__":
#     load_recipes_into_memory()
#     HTTPServer(("localhost", 8080), RecipeHandler).serve_forever()


# --- INTERVIEW TALKING POINTS ---
# 1. Mention CORS header if frontend (port 8000) calls API (port 8080)
# 2. pydantic validation on POST = automatic 422-style errors for bad agent input
# 3. No Flask/FastAPI needed — stdlib is enough for KATA
# 4. MCP agent could call these same endpoints as tools
```

**Where it plugs in:** New `api.py` importing from `backend.py`. Frontend change: `fetch("http://localhost:8080/recipes")` instead of static JSON.

---

### 5. Search / Filter Recipes by Ingredient

**Why they'll ask:** Food service staff think in ingredients ("what can I make with the chicken we need to use up?"). Also tests your comfort iterating the existing data structures.

**Likely prompt:** *"Show me all recipes that use chicken breast"* or *"Which recipes can I make with only these 3 ingredients?"*

**Plan of attack:**

```python
# backend.py — simple list comprehensions over list[Recipe]

def find_recipes_by_ingredient(
    recipes: list[Recipe],
    ingredient_query: str,
) -> list[Recipe]:
    """
    Case-insensitive substring match on ingredient keys.

    "chicken" → matches "chicken breast"
    "oil"     → matches "olive oil" in multiple recipes
    """
    query = ingredient_query.lower()
    return [
        recipe for recipe in recipes
        if any(query in name.lower() for name in recipe.ingredients)
    ]


def find_recipes_using_all(
    recipes: list[Recipe],
    required_ingredients: list[str],
) -> list[Recipe]:
    """
    Return recipes that contain ALL of the listed ingredients.

    Useful for: "We have eggs, spinach, and olive oil — what can we cook?"
    """
    required = {name.lower() for name in required_ingredients}
    results = []
    for recipe in recipes:
        recipe_names = {name.lower() for name in recipe.ingredients}
        if required.issubset(recipe_names):
            results.append(recipe)
    return results


# --- FRONTEND SKETCH (talk through, don't necessarily code) ---
# Add <input> on list page → filter cards client-side:
#
#   const filtered = recipes.filter(r =>
#     Object.keys(r.ingredients).some(name =>
#       name.toLowerCase().includes(query.toLowerCase())
#     )
#   );
#
# Same logic, just in JS instead of Python — show you can translate between layers.


# --- INTERVIEW TALKING POINTS ---
# 1. Start with substring match — mention exact match or fuzzy later
# 2. Inverse query (recipes using ALL ingredients) is slightly harder — good to offer both
# 3. Could combine with inventory check: filter to only recipes where can_make == True
```

**Where it plugs in:** Pure functions over `list[Recipe]`. Frontend can mirror the same logic in JS for instant filter without an API round-trip.

---

## Quick Reference — Which File to Touch

| Request | Primary file | Frontend change? |
|---|---|---|
| Scale yield | `backend.py` | Optional input on detail page |
| Shopping list | `backend.py` | New `#/shopping` route |
| Inventory check | `backend.py` | New report section or route |
| Live API | `api.py` (new) | Point `fetch` to `:8080` |
| Search/filter | `backend.py` + `index.html` | Search box on list page |

---

## Possible Enhancements

*Based on review of the app at `http://localhost:8000` (static server + `index.html` + `meal-plan-refactored.json`).*

### Data & Backend

| Area | Current state | Suggested improvement |
|---|---|---|
| **Ingredient parsing** | Regex only handles `"Ng name"` format | Extend `parse_ingredient` for `kg`, `ml`, `oz`, and unitless items (`"2 eggs"`) |
| **Ingredient normalization** | `"olive oil"` merged by exact string key only | Add a `canonical_name()` mapping so `"diced onion"` / `"onion"` roll up for ordering |
| **Duplicate demo input** | `meal-plan-2.json` is identical to `meal-plan.json` | Use it for a *different* messy file in the demo, or document why both exist |
| **Persistence** | Backend is a one-shot build step | Add optional `api.py` (Request #4) so changes survive page refresh |
| **requirements.txt** | Only `pydantic` documented in README | Pin `pydantic>=2.0` for reproducible interview setup |

### Frontend (port 8000)

| Area | Current state | Suggested improvement |
|---|---|---|
| **Routing** | `#/recipe/0` uses array index | Use slug (`#/recipe/chicken-stir-fry`) — indices break if recipe order changes |
| **XSS safety** | `innerHTML` with `${r.title}` unescaped | Use `textContent` or escape helper — interviewer may probe security awareness |
| **Per-serving display** | Detail shows total grams only | Add a "per serving" column (`grams / yield`) — natural follow-up to scaling |
| **Total weight** | Not shown on detail page | Footer row summing all ingredient grams |
| **Search / filter** | List shows all 3 cards, no filter | Search input (Request #5) — high-value, low-effort during live coding |
| **Loading state** | "Loading recipes…" text only | Skeleton cards or spinner — minor polish |
| **Empty / error states** | Good error if JSON missing | Add friendly 404 for `#/recipe/999` (currently redirects to list silently) |
| **Tailwind CDN** | Full CDN build (~300KB) | Acceptable for KATA; mention that production would use a built CSS file |

### Domain-Specific (DS Food Order Platform)

| Area | Why it matters |
|---|---|
| **Shopping list page** | Natural capstone: select recipes → aggregate → show order quantities |
| **Inventory dashboard** | Show on-hand vs required with red/green indicators |
| **Reorder suggestions** | `generate_reorder_list()` output as a "Suggested Order" view |
| **Agent/MCP tools** | Expose `scale_recipe`, `build_shopping_list`, `check_inventory` as named Python functions an MCP server can wrap — pydantic models already in place |
| **Cost estimation** | Multiply grams by unit cost from a `PRICES` dict — common procurement ask |
| **Dietary tags** | Add optional `tags: list[str]` to `Recipe` (`vegetarian`, `gluten-free`) for filtering |

### Interview Presentation Tips

1. **Start by restating the problem** in DS terms: "This is a demand calculation before placing a food order."
2. **Reach for existing code first:** "We already have `Recipe` with `ingredients: dict[str, float]` — I can build on that."
3. **Call out trade-offs aloud:** exact vs fuzzy ingredient matching, mutate vs return-new, static JSON vs live API.
4. **Draw the data flow** if whiteboard available: `Recipe → scale/shopping-list → inventory check → reorder`.
5. **Don't over-build.** A commented 15-line function beats a 100-line refactor during a KATA.

---

## Cheat-Sheet: Existing Code to Reference Live

```python
# Already in backend.py — point interviewer here immediately:

class Recipe(BaseModel):
    title: str
    yield_: int = Field(alias="yield")
    ingredients: dict[str, float]          # ← most new features iterate this dict

def parse_ingredient(ingredient: str) -> tuple[str, float]: ...
def refactor_json(data) -> list[dict]: ...
def process_meal_plan(input_path: Path) -> tuple[list, list[Recipe]]: ...
```

```javascript
// Already in index.html — frontend patterns to extend:

fetch("meal-plan-refactored.json")         // swap for API when needed
Object.entries(recipe.ingredients)         // iterate for tables, totals, filters
location.hash                              // add #/shopping, #/inventory routes
```
