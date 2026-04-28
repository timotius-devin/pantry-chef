"""
pantry-chef/backend/main.py
FastAPI backend for Pantry Chef.

Responsibilities:
- Holds the ANTHROPIC_API_KEY server-side
- Accepts ingredients, calls Claude to generate recipes
- Returns JSON with recipe objects
- Exhaustive error handling per the project spec
"""

import os
import json

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_TIMEOUT = 25.0  # seconds

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is not set.")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=CLAUDE_TIMEOUT)

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(
    title="Pantry Chef API",
    description="Turn your ingredients into recipes — powered by Claude.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic models ───────────────────────────────────────────────

class GenerateRequest(BaseModel):
    ingredients: list[str] = Field(..., min_length=1, max_length=30)


class Recipe(BaseModel):
    title: str
    description: str
    cook_time: str
    difficulty: str
    ingredients: list[str]
    steps: list[str]


class GenerateResponse(BaseModel):
    recipes: list[Recipe]

# ── Schema validation ─────────────────────────────────────────────

def validate_recipe_schema(data: dict) -> list[dict]:
    """Validate the parsed JSON matches our recipe schema. Raises ValueError on failure."""
    if not isinstance(data, dict):
        raise ValueError("Response was not a JSON object")

    recipes = data.get("recipes")
    if not isinstance(recipes, list):
        raise ValueError("Missing 'recipes' array")
    if len(recipes) == 0:
        raise ValueError("'recipes' array is empty")

    required = {"title", "description", "cook_time", "difficulty", "ingredients", "steps"}
    for i, r in enumerate(recipes):
        if not isinstance(r, dict):
            raise ValueError(f"Recipe at index {i} is not an object")
        missing = required - set(r.keys())
        if missing:
            raise ValueError(f"Recipe at index {i} missing fields: {', '.join(missing)}")
        if not isinstance(r.get("ingredients"), list) or not all(isinstance(x, str) for x in r["ingredients"]):
            raise ValueError(f"Recipe at index {i} ingredients must be a list of strings")
        if not isinstance(r.get("steps"), list) or not all(isinstance(x, str) for x in r["steps"]):
            raise ValueError(f"Recipe at index {i} steps must be a list of strings")

    return recipes

# ── JSON extraction ───────────────────────────────────────────────

def extract_json(raw: str) -> dict:
    """Extract JSON from Claude's response. Handles markdown fences and preamble."""
    s = raw.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    fence = s
    # Try ```json ... ``` or ``` ... ```
    if "```" in s:
        start = s.find("```")
        end = s.find("```", start + 3)
        if end != -1:
            line_end = s.find("\n", start)
            if line_end != -1 and line_end < end:
                fence = s[line_end:end].strip()
            else:
                fence = s[start + 3:end].strip()

    try:
        return json.loads(fence)
    except json.JSONDecodeError:
        pass

    # Last resort: find first { and last }
    brace_start = s.find("{")
    brace_end = s.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(s[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse JSON from Claude's response")

# ── Claude prompt ─────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a creative home chef assistant. Given a list of ingredients, generate recipe ideas.

RULES:
1. Only generate recipes that can realistically be made with the ingredients provided (pantry basics like salt, pepper, oil, water are assumed available).
2. Return exactly this JSON format — nothing else:
{
  "recipes": [
    {
      "title": "Recipe Name",
      "description": "One-sentence description of the dish",
      "cook_time": "25 mins",
      "difficulty": "Easy",
      "ingredients": ["1 cup flour", "2 eggs", "..."],
      "steps": ["Step 1: ...", "Step 2: ..."]
    }
  ]
}
3. Generate 1–4 recipes depending on the ingredients provided.
4. Include measurements in the ingredients list where helpful.
5. Each step should be a clear, actionable instruction.
6. If the input is clearly not food ingredients (e.g. "keyboard", "laptop", "homework"), return:
{"error": "Those don't look like food ingredients. Try listing things from your pantry or fridge!"}
7. Return ONLY valid JSON. No markdown, no conversation, no preamble."""

# ── Routes ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/generate-recipe")
async def generate_recipe(req: GenerateRequest):
    # ── Input validation ────────────────────────────────────────────
    ingredients = req.ingredients

    if len(ingredients) == 0:
        raise HTTPException(status_code=400, detail="Please provide at least one ingredient")

    if len(ingredients) > 30:
        raise HTTPException(status_code=400, detail="Too many ingredients — keep it under 30")

    if not all(isinstance(i, str) for i in ingredients):
        raise HTTPException(status_code=400, detail="All ingredients must be text")

    # ── Call Claude ─────────────────────────────────────────────────
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Ingredients: {', '.join(ingredients)}"
            }],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=500, detail="Service misconfigured — contact admin")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Too many requests — slow down a bit")
    except anthropic.APIError as e:
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg or "timedout" in msg:
            raise HTTPException(status_code=503, detail="Our chef is taking too long — try again")
        raise HTTPException(status_code=500, detail="Something went wrong")
    except Exception:
        raise HTTPException(status_code=500, detail="Something went wrong")

    # ── Parse response ──────────────────────────────────────────────
    block = response.content[0] if response.content else None
    if block is None or block.type != "text":
        raise HTTPException(status_code=422, detail="Couldn't understand the recipe response — try again")

    raw_text = block.text

    try:
        data = extract_json(raw_text)
    except ValueError:
        raise HTTPException(status_code=422, detail="Couldn't understand the recipe response — try again")

    # Check for off-topic rejection from Claude
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])

    # Schema validation
    try:
        validated = validate_recipe_schema(data)
    except ValueError:
        raise HTTPException(status_code=422, detail="Recipe response was incomplete — try again")

    return GenerateResponse(recipes=[Recipe(**r) for r in validated])


# ── Catch-all error handlers ──────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong"},
    )


@app.exception_handler(422)
async def validation_exception_handler(request: Request, exc):
    """Handle FastAPI's built-in 422 (Pydantic validation failure)."""
    errors = exc.errors() if hasattr(exc, 'errors') else []
    # Check if the body itself is missing/malformed
    for err in errors:
        if err.get("type") in ("missing", "json_invalid"):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid request format"},
            )
    return JSONResponse(
        status_code=400,
        content={"detail": "Invalid request format"},
    )


# ── Serve built frontend in production ────────────────────────────
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    @app.get("/")
    def serve_root():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")
