"""BookMusic backend API.

The "embedded webserver" for local dev: exposes POST /generate and serves the
static frontend so the whole thing runs from one `uvicorn server:app` command.
In production the frontend is static-hosted and /generate becomes a Lambda.

    uv run uvicorn server:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bookmusic import generate

SAMPLE_TEXT = Path(__file__).parent / "samples" / "sample.txt"

app = FastAPI(title="BookMusic")

# Permissive CORS for local dev (frontend may be served from a different origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def dev_headers(request, call_next):
    # Dev convenience: never let the browser cache the frontend, so edits to the
    # static JS/HTML always show up on reload (ES modules cache aggressively).
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    # Cross-origin isolation so the in-browser WebGPU model (transformers.js /
    # ONNX Runtime Web) gets SharedArrayBuffer (crossOriginIsolated === true).
    # "credentialless" (not "require-corp") keeps the app's cross-origin loads
    # working without CORP headers: @strudel/repl (unpkg), pdf.js (jsdelivr) and
    # the model weights (huggingface.co).
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    return response


class GenerateRequest(BaseModel):
    paragraph: str
    previous_code: str = ""


class GenerateResponse(BaseModel):
    code: str


@app.post("/generate", response_model=GenerateResponse)
def generate_endpoint(req: GenerateRequest) -> GenerateResponse:
    return GenerateResponse(code=generate(req.paragraph, req.previous_code))


@app.get("/sample", response_class=PlainTextResponse)
def sample_endpoint() -> str:
    """Return the bundled demo document so the frontend can pre-load it."""
    return SAMPLE_TEXT.read_text()


# Serve the static frontend at the root. Mounted last so /generate wins for its path.
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
