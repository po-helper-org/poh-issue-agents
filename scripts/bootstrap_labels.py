"""Заводит метки контура в репозитории.

Гоняется один раз при подключении нового репозитория — это шаг runbook'а из
дизайна поддержки GitLab. Идемпотентен: повторный запуск ничего не портит.

    python scripts/bootstrap_labels.py --repo owner/name
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

import github_client  # noqa: E402
from shared.label_catalog import catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                        help="owner/name; по умолчанию GITHUB_REPOSITORY")
    args = parser.parse_args()
    if not args.repo:
        parser.error("нужен --repo или GITHUB_REPOSITORY")

    specs = list(catalog().values())
    created = github_client.ensure_labels_exist(args.repo, specs)
    print(f"{args.repo}: в каталоге {len(specs)}, создано {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
