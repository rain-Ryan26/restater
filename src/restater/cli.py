from __future__ import annotations

import argparse
from pathlib import Path

from restater.config import RestaterConfig, load_dotenv
from restater.graph import make_cli_progress, run_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="restater")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Run a Phase 1 local project check.")
    check.add_argument(
        "project_path",
        nargs="?",
        help="Project directory to inspect. Defaults to RESTATER_DEFAULT_PROJECT_PATH when omitted.",
    )
    check.add_argument("--note", default="", help="Initial user note for the check.")
    check.add_argument("--out", default=None, help="Output directory for report and state.")
    check.add_argument("--env-file", default=".env", help="Environment file to load before running.")
    check.add_argument("--quiet", action="store_true", help="Disable per-stage progress output.")

    args = parser.parse_args(argv)
    if args.command == "check":
        load_dotenv(Path(args.env_file))
        config = RestaterConfig.from_env()
        project_path = args.project_path or config.default_project_path
        if not project_path:
            parser.error("project_path is required unless RESTATER_DEFAULT_PROJECT_PATH is set.")
        final_state = run_check(
            project_path=Path(project_path),
            user_note=args.note,
            output_dir=Path(args.out) if args.out else None,
            config=config,
            progress=make_cli_progress(enabled=not args.quiet),
        )
        print(f"Report: {final_state.get('report_path')}")
        print(f"State: {Path(final_state['output_dir']) / 'state.json'}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
