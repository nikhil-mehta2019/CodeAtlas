"""CodeAtlas CLI — V1 surface (ARCHITECTURE.md §2, §9).

    codeatlas analyze <repo-path> [--data-dir DIR] [--out REPORT.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codeatlas.orchestrator.pipeline import Orchestrator


def _cmd_analyze(args: argparse.Namespace) -> int:
    data_dir = args.data_dir or (Path(args.repo_path).resolve().parent / ".codeatlas")
    orchestrator = Orchestrator(data_dir=data_dir)
    run = orchestrator.run(args.repo_path)

    out_path = Path(args.out) if args.out else Path(data_dir) / run.knowledge.project_id / "report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(run.markdown_report, encoding="utf-8")

    print(f"Project ID: {run.knowledge.project_id}")
    print(f"Knowledge DB: {Path(data_dir) / 'knowledge.db'}")
    print(f"Evidence dir: {Path(data_dir) / run.knowledge.project_id / 'evidence'}")
    print(f"Report written to: {out_path}")
    print(f"Unknowns flagged: {len(run.knowledge.unknowns)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codeatlas", description="AI Software Quality Agent — discovery & understanding.")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Discover, analyze, and document a repository.")
    analyze.add_argument("repo_path", help="Path to the repository to analyze.")
    analyze.add_argument("--data-dir", help="Where to store the knowledge base and evidence (default: <repo-parent>/.codeatlas).")
    analyze.add_argument("--out", help="Where to write the Markdown report (default: <data-dir>/<project-id>/report.md).")
    analyze.set_defaults(func=_cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
