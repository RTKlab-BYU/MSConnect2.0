import shlex
import subprocess


def run_upgrade_hook(command: str, parameters: dict) -> dict:
    """Run an operator-configured host upgrade hook without invoking a shell."""
    tokens = shlex.split(command or "")
    if not tokens:
        return {"status": "unconfigured"}
    args = [str(parameters.get(key) or "") for key in ("release_version", "image", "digest")]
    try:
        completed = subprocess.run([*tokens, *args], capture_output=True, text=True, timeout=900, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "error": str(exc)}
    result = {"status": "succeeded" if completed.returncode == 0 else "failed", "returncode": completed.returncode}
    if completed.stdout.strip():
        result["stdout"] = completed.stdout[-2000:]
    if completed.stderr.strip():
        result["stderr"] = completed.stderr[-2000:]
    return result
