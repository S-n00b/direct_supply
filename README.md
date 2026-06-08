# Direct Supply KATA — Recipe Cleaner + Viewer

A lightweight meal-plan app for the Direct Supply KATA assessment. A vanilla Python backend cleans and refactors messy JSON; a static Tailwind frontend displays recipes on GitHub Pages.

## Project Structure

```
meal-plan.json            # Original messy input (from KATA email)
meal-plan-2.json          # Duplicate messy input for demo
backend.py                # clean_json, refactor_json, pydantic validation
meal-plan-cleaned.json    # Generated: syntax-fixed JSON
meal-plan-2-cleaned.json  # Generated: syntax-fixed JSON (demo)
meal-plan-refactored.json # Generated: ingredients as {name: grams} dict
index.html                # Tailwind frontend (recipe list + detail)
```

## Quick Start

### 1. Install dependency

```bash
pip install pydantic
```

### 2. Run the backend build step

```bash
python backend.py
```

This will:

- Clean `meal-plan.json` and `meal-plan-2.json` (fix trailing commas, bad whitespace, indentation)
- Validate recipes with pydantic `RawRecipe` and `Recipe` models
- Write `meal-plan-refactored.json` for the frontend

### 3. Preview locally

Open `index.html` in a browser, or serve with any static file server:

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000`.

## GitHub Pages Deployment

```bash
git init
git add .
git commit -m "Direct Supply KATA meal plan app"
git remote add origin <your-repo-url>
git push -u origin main
```

In your GitHub repo: **Settings → Pages → Source: Deploy from branch `main`, folder `/ (root)`**.

The site will be live at `https://<username>.github.io/<repo>/`.

> **Note:** Run `python backend.py` before committing so `meal-plan-refactored.json` is up to date. GitHub Pages serves static files only; the Python backend runs locally as a build step.

## Backend Functions

| Function | Purpose |
|---|---|
| `clean_json(raw_text)` | Heuristic repair of broken JSON syntax |
| `parse_ingredient(s)` | Split `"30g olive oil"` → `("olive oil", 30.0)` |
| `refactor_json(data)` | Convert ingredient arrays to `{name: grams}` dicts |
| `RawRecipe` / `Recipe` | Pydantic models for validation and agent/MCP readiness |

## Frontend

- **List view** (`#/`): card grid of all recipes
- **Detail view** (`#/recipe/<index>`): ingredients table with gram weights
- Styled with Tailwind CSS to match [Direct Supply](https://www.directsupply.com/) branding (green primary, navy headers, light gray surfaces)
