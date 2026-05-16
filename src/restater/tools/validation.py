from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from restater.models import ShellResult, ValidationAttempt


VALIDATION_KEYWORDS = {
    "test",
    "tests",
    "verify",
    "check",
    "compile",
    "build",
    "package",
}

BLOCKED_COMMAND_TOKENS = [
    "&&",
    "||",
    "|",
    ">",
    ">>",
    "rm ",
    "del ",
    "rmdir ",
    "remove-item",
    "git reset",
    "git clean",
    "format ",
]


def run_validation_command(command: str, cwd: Path, *, timeout_seconds: int = 180) -> tuple[ShellResult, ValidationAttempt]:
    attempt = normalize_validation_command(command, cwd)
    if not attempt.runnable:
        result = ShellResult(
            command=command,
            cwd=str(cwd),
            exit_code=1,
            stdout="",
            stderr=attempt.blocked_reason,
            duration_ms=0,
        )
        return result, attempt

    executable, args = command_parts(attempt.normalized_command)
    start = time.perf_counter()
    completed = subprocess.run(
        [executable, *args],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    result = ShellResult(
        command=display_command(attempt.normalized_command),
        cwd=str(cwd),
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
    )
    attempt.exit_code = completed.returncode
    attempt.success = completed.returncode == 0
    attempt.stdout_excerpt = completed.stdout.strip()[:1000]
    attempt.stderr_excerpt = completed.stderr.strip()[:1000]
    attempt.summary = summarize_validation_result(result)
    attempt.report_paths = discover_report_paths(cwd)
    return result, attempt


def normalize_validation_command(command: str, cwd: Path) -> ValidationAttempt:
    raw = command.strip()
    lowered = raw.lower()
    blocked = blocked_reason(raw)
    if blocked:
        return ValidationAttempt(
            command=command,
            cwd=str(cwd),
            runnable=False,
            blocked_reason=blocked,
            summary=blocked,
        )

    if "powershell" in lowered and "-command" in lowered:
        return ValidationAttempt(
            command=command,
            cwd=str(cwd),
            runnable=False,
            blocked_reason="Nested PowerShell commands are not accepted by the validation tool.",
            summary="Validation command was rejected because it nests powershell -Command.",
        )

    if is_maven_command(lowered, cwd):
        return normalize_maven_command(raw, cwd)
    if is_npm_command(lowered, cwd):
        return normalize_npm_command(raw, cwd)
    if is_pytest_command(lowered, cwd):
        return normalize_pytest_command(raw, cwd)
    if is_gradle_command(lowered, cwd):
        return normalize_gradle_command(raw, cwd)

    return ValidationAttempt(
        command=command,
        cwd=str(cwd),
        runnable=False,
        blocked_reason="Command does not look like a supported read-only validation command.",
        summary="No supported validation command was identified.",
    )


def blocked_reason(command: str) -> str:
    lowered = command.lower()
    for token in BLOCKED_COMMAND_TOKENS:
        if token in lowered:
            return f"Validation command rejected because it contains unsupported shell syntax or destructive token: {token.strip()}"
    return ""


def is_maven_command(lowered: str, cwd: Path) -> bool:
    return ("mvn" in lowered or (cwd / "pom.xml").exists()) and any(word in lowered for word in VALIDATION_KEYWORDS)


def normalize_maven_command(command: str, cwd: Path) -> ValidationAttempt:
    executable = discover_maven_executable(command)
    goals = maven_goals(command) or ["test"]
    options = maven_options(command)
    args = [*options, *goals]
    normalized = format_command(executable, args)
    return ValidationAttempt(
        command=command,
        normalized_command=normalized,
        cwd=str(cwd),
        purpose="maven validation",
        summary=f"Prepared Maven validation command: {display_command(normalized)}",
    )


def discover_maven_executable(command: str) -> str:
    match = re.search(r"&\s*['\"]([^'\"]*mvn(?:\.cmd)?)['\"]", command, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"(['\"])([^'\"]*mvn(?:\.cmd)?)\1", command, flags=re.IGNORECASE)
    if match:
        return match.group(2)
    return "mvn"


def maven_goals(command: str) -> list[str]:
    goals: list[str] = []
    for goal in ["test", "verify", "compile", "package"]:
        if re.search(rf"(^|\s){goal}($|\s)", command, flags=re.IGNORECASE):
            goals.append(goal)
    return goals


def maven_options(command: str) -> list[str]:
    options: list[str] = []
    if re.search(r"(^|\s)-q($|\s)", command):
        options.append("-q")
    if "-DskipTests" in command:
        options.append("-DskipTests")
    test_match = re.search(r"-Dtest=(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))", command)
    if test_match:
        test_value = next(group for group in test_match.groups() if group)
        options.append(f"-Dtest={test_value}")
    if "-DfailIfNoTests=false" in command:
        options.append("-DfailIfNoTests=false")
    return options


def is_npm_command(lowered: str, cwd: Path) -> bool:
    return (lowered.startswith("npm ") or (cwd / "package.json").exists()) and any(
        word in lowered for word in ["test", "build", "run"]
    )


def normalize_npm_command(command: str, cwd: Path) -> ValidationAttempt:
    lowered = command.lower()
    if "build" in lowered:
        args = ["run", "build"]
    elif "npm test" in lowered:
        args = ["test"]
    else:
        args = ["test"]
    normalized = format_command("npm", args)
    return ValidationAttempt(command=command, normalized_command=normalized, cwd=str(cwd), purpose="npm validation")


def is_pytest_command(lowered: str, cwd: Path) -> bool:
    return "pytest" in lowered or (cwd / "pytest.ini").exists()


def normalize_pytest_command(command: str, cwd: Path) -> ValidationAttempt:
    normalized = format_command("python", ["-m", "pytest"])
    return ValidationAttempt(command=command, normalized_command=normalized, cwd=str(cwd), purpose="pytest validation")


def is_gradle_command(lowered: str, cwd: Path) -> bool:
    return "gradle" in lowered or (cwd / "build.gradle").exists() or (cwd / "build.gradle.kts").exists()


def normalize_gradle_command(command: str, cwd: Path) -> ValidationAttempt:
    executable = "gradlew.bat" if (cwd / "gradlew.bat").exists() else "gradle"
    args = ["test" if "test" in command.lower() else "build"]
    normalized = format_command(executable, args)
    return ValidationAttempt(command=command, normalized_command=normalized, cwd=str(cwd), purpose="gradle validation")


def command_parts(normalized_command: str) -> tuple[str, list[str]]:
    parts = normalized_command.split("\0")
    return parts[0], parts[1:]


def format_command(executable: str, args: list[str]) -> str:
    return "\0".join([executable, *args])


def display_command(normalized_command: str) -> str:
    executable, args = command_parts(normalized_command)
    return " ".join([quote_if_needed(executable), *[quote_if_needed(arg) for arg in args]])


def quote_if_needed(value: str) -> str:
    if re.search(r"\s", value):
        return f'"{value}"'
    return value


def summarize_validation_result(result: ShellResult) -> str:
    display = result.command
    out = result.stdout.strip()
    err = result.stderr.strip()
    if result.exit_code == 0:
        summary = f"Validation command succeeded: {display}."
    else:
        summary = f"Validation command failed with exit code {result.exit_code}: {display}."
    if out:
        summary += f" stdout: {out[:500]}"
    if err:
        summary += f" stderr: {err[:500]}"
    return summary


def discover_report_paths(cwd: Path) -> list[str]:
    report_dir = cwd / "target" / "surefire-reports"
    if not report_dir.exists():
        return []
    return [str(path.relative_to(cwd)) for path in sorted(report_dir.glob("*.xml"))[:20]]
