import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


def check_env() -> list[str]:
    required = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "GROQ_API_KEY"]
    missing = [name for name in required if not os.getenv(name)]
    return missing


def _normalized_rocketride_uri() -> str:
    uri = os.getenv("ROCKETRIDE_URI", "http://localhost:5565").strip()
    if not uri:
        return "http://localhost:5565"

    # Users sometimes store ws://.../task/service directly in env; client appends this path itself.
    if uri.endswith("/task/service"):
        uri = uri[: -len("/task/service")]

    parsed = urlparse(uri)
    if not parsed.scheme:
        return f"http://{uri}"
    return uri


async def check_rocketride() -> tuple[bool, str]:
    try:
        from rocketride import RocketRideClient
        from rocketride.schema import Question
    except Exception as exc:
        return False, f"rocketride import failed: {exc}"

    pipe_path = Path(__file__).resolve().parent / "pipelines" / "agentos_simulate.pipe"
    if not pipe_path.exists():
        return False, f"pipeline missing: {pipe_path}"

    with pipe_path.open("r", encoding="utf-8") as f:
        pipeline = json.load(f)

    uri = _normalized_rocketride_uri()
    auth = os.getenv("ROCKETRIDE_APIKEY", "LOCAL_DEV_KEY") or "LOCAL_DEV_KEY"

    try:
        async with RocketRideClient(uri=uri, auth=auth) as client:
            result = await client.use(pipeline=pipeline, source="chat_1", use_existing=True)
            token = result["token"]

            q = Question(expectJson=False)
            q.addInstruction(
                "Format",
                "Return valid JSON object with keys worker, checker, watcher, explanation."
            )
            q.addQuestion("Test run for AgentOS pipeline")
            response = await client.chat(token=token, question=q)
            answers = response.get("answers", [])
            if not answers:
                return False, "rocketride responded without answers"
    except Exception as exc:
        return False, f"{exc} (uri={uri})"

    return True, "ok"


def main() -> int:
    # Load backend env deterministically and allow it to override shell/root values.
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

    missing = check_env()
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
    else:
        print("Core env vars: ok")

    rr_ok, rr_msg = asyncio.run(check_rocketride())
    if rr_ok:
        print("RocketRide check: ok")
    else:
        print(f"RocketRide check: failed ({rr_msg})")

    if missing or not rr_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
