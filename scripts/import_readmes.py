#!/usr/bin/env python3
"""Import public repository READMEs into a temporary MkDocs build."""

from __future__ import annotations

import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_FILE = ROOT / "readme-projects.yml"
BASE_CONFIG = ROOT / "mkdocs.yml"
GENERATED_CONFIG = ROOT / "mkdocs.generated.yml"
OUTPUT_DIR = ROOT / "docs-source" / "repositories"


def fetch_readme(repository: str) -> str | None:
    url = f"https://api.github.com/repos/{repository}/readme"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.raw+json",
            "User-Agent": "mcquerol-github-pages-readme-importer",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            print(f"Skipping {repository}: no README found.")
            return None
        raise


def make_relative_links_absolute(markdown: str, repository: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix, target, suffix = match.groups()
        clean_target = target.strip()
        if (
            not clean_target
            or clean_target.startswith(("#", "/", "mailto:"))
            or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean_target)
        ):
            return match.group(0)

        path, *fragment = clean_target.split("#", 1)
        anchor = f"#{fragment[0]}" if fragment else ""
        if prefix.startswith("!"):
            absolute = f"https://raw.githubusercontent.com/{repository}/HEAD/{path}{anchor}"
        else:
            absolute = f"https://github.com/{repository}/blob/HEAD/{path}{anchor}"
        return f"{prefix}{absolute}{suffix}"

    return re.sub(r"(!?\[[^\]]*\]\()([^\s)]+)(\))", replace, markdown)


def main() -> int:
    project_data = yaml.safe_load(PROJECTS_FILE.read_text(encoding="utf-8"))
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    imported: list[dict[str, str]] = []

    for project in project_data.get("projects", []):
        name = project["name"]
        repository = project["repository"]
        readme = fetch_readme(repository)
        if readme is None:
            continue

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = repository.split("/", 1)[1]
        page_path = OUTPUT_DIR / f"{slug}.md"
        source_url = f"https://github.com/{repository}"
        content = (
            f"[View the source repository on GitHub]({source_url}){{ .md-button }}\n\n"
            + make_relative_links_absolute(readme, repository)
        )
        page_path.write_text(content, encoding="utf-8")
        imported.append(
            {
                "name": name,
                "path": f"repositories/{slug}.md",
                "repository": repository,
            }
        )
        print(f"Imported README from {repository}.")

    if imported:
        overview = [
            "# Repository documentation",
            "",
            "These pages are generated from the latest README in each project repository.",
            "",
        ]
        for project in imported:
            overview.append(
                f"- [{project['name']}]({Path(project['path']).name}) "
                f"— [{project['repository']}](https://github.com/{project['repository']})"
            )
        (OUTPUT_DIR / "index.md").write_text(
            "\n".join(overview) + "\n", encoding="utf-8"
        )

        category = project_data.get("category", "Repository READMEs")
        project_nav = {
            category: [
                {"Overview": "repositories/index.md"},
                *[{item["name"]: item["path"]} for item in imported],
            ]
        }
        nav = config.setdefault("nav", [])
        about_index = next(
            (index for index, item in enumerate(nav) if "About" in item),
            len(nav),
        )
        nav.insert(about_index, project_nav)

    GENERATED_CONFIG.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Generated MkDocs configuration with {len(imported)} README page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
