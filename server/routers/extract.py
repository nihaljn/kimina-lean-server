import asyncio
import json
import os
import tempfile
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from ..auth import require_key
from ..settings import settings

router = APIRouter()

# `lake env lean --run ExtractDataFast.lean ...` is parser-only — it loads
# Mathlib oleans (mmap, ~10s) and parses commands without elaboration. No
# tactic tracing. Only `commandASTs` is populated; `tactics` and `messages`
# are empty (callers needing messages should use `/api/check` separately).
# Cap parallelism — concurrent runs each load Mathlib parser tables fresh.
_extract_semaphore = asyncio.Semaphore(2)

EXTRACT_SCRIPT = "ExtractDataFast.lean"


class ExtractRequest(BaseModel):
    id: str = "extract"
    code: str
    timeout: int = 300


class ExtractResponse(BaseModel):
    id: str
    ast: dict | None = None
    error: str | None = None
    time: float


async def _run_extract(code: str, timeout: int) -> tuple[dict | None, str | None]:
    project_dir = settings.project_dir
    script_path = project_dir / EXTRACT_SCRIPT
    if not script_path.exists():
        return None, f"{EXTRACT_SCRIPT} not found at {script_path}"

    in_fd, in_path = tempfile.mkstemp(suffix=".lean", dir=str(project_dir))
    out_fd, out_path = tempfile.mkstemp(suffix=".json", dir=str(project_dir))
    os.close(in_fd)
    os.close(out_fd)
    try:
        with open(in_path, "w") as f:
            f.write(code)

        proc = await asyncio.create_subprocess_exec(
            "lake", "env", "lean", "--run", EXTRACT_SCRIPT, in_path, out_path,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return None, f"ExtractData timed out after {timeout}s"

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace") or stdout.decode("utf-8", errors="replace")
            return None, f"ExtractData exit {proc.returncode}: {err[:2000]}"

        try:
            with open(out_path) as f:
                ast = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return None, f"Failed to read AST output: {e}"

        return ast, None
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


@router.post(
    "/extract",
    response_model=ExtractResponse,
    response_model_exclude_none=True,
)
async def extract(
    request: ExtractRequest,
    raw_request: Request,
    _: str | None = Depends(require_key),
) -> ExtractResponse:
    start = time.monotonic()
    async with _extract_semaphore:
        if await raw_request.is_disconnected():
            raise HTTPException(499, "Client disconnected")
        logger.info("[extract] id={} chars={}", request.id, len(request.code))
        ast, err = await _run_extract(request.code, request.timeout)
    elapsed = time.monotonic() - start
    if err:
        logger.warning("[extract] id={} failed in {:.2f}s: {}", request.id, elapsed, err[:200])
    else:
        logger.info("[extract] id={} ok in {:.2f}s", request.id, elapsed)
    return ExtractResponse(id=request.id, ast=ast, error=err, time=elapsed)
