#!/usr/bin/env python3
"""Import READMEs from all public repositories into a temporary MkDocs build."""

from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_FILE = ROOT / "readme-projects.yml"
BASE_CONFIG = ROOT / "mkdocs.yml"
GENERATED_CONFIG = ROOT / "mkdocs.generated.yml"
OUTPUT_DIR = ROOT / "docs-source" / "repositories"
USER_AGENT = "mcquerol-github-pages-readme-importer"


def request_bytes(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def list_repositories(owner: str) -> list[dict]:
    repositories: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"per_page": 100, "page": page, "sort": "full_name"}
        )
        payload = request_bytes(
            f"https://api.github.com/users/{owner}/repos?{query}"
        )
        if payload is None:
            raise RuntimeError(f"GitHub user not found: {owner}")
        batch = json.loads(payload.decode("utf-8"))
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repositories


def fetch_readme(repository: str, default_branch: str) -> str | None:
    for filename in ("README.md", "README.MD", "readme.md", "Readme.md"):
        url = (
            f"https://raw.githubusercontent.com/{repository}/"
            f"{urllib.parse.quote(default_branch, safe='')}/{filename}"
        )
        payload = request_bytes(url)
        if payload is not None:
            return payload.decode("utf-8")
    return None


def make_relative_links_absolute(
    markdown: str, repository: str, default_branch: str
) -> str:
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
            absolute = (
                f"https://raw.githubusercontent.com/{repository}/"
                f"{default_branch}/{path}{anchor}"
            )
        else:
            absolute = (
                f"https://github.com/{repository}/blob/"
                f"{default_branch}/{path}{anchor}"
            )
        return f"{prefix}{absolute}{suffix}"

    return re.sub(r"(!?\[[^\]]*\]\()([^\s)]+)(\))", replace, markdown)


def main() -> int:
    settings = yaml.safe_load(PROJECTS_FILE.read_text(encoding="utf-8"))
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    owner = settings.get("owner", "mcquerol")
    category = settings.get("category", "Repositories")
    include_forks = settings.get("include_forks", False)
    excluded = set(settings.get("exclude", []))

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    imported: list[dict[str, str]] = []

    repositories = list_repositories(owner)
    for repository_data in repositories:
        name = repository_data["name"]
        if name in excluded:
            continue
        if repository_data.get("fork") and not include_forks:
            continue

        full_name = repository_data["full_name"]
        default_branch = repository_data.get("default_branch", "main")
        readme = fetch_readme(full_name, default_branch)
        if readme is None:
            print(f"Skipping {full_name}: no README found.")
            continue

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        page_path = OUTPUT_DIR / f"{name}.md"
        source_url = repository_data["html_url"]
        content = (
            f"[View the source repository on GitHub]({source_url})"
            "{ .md-button }\n\n"
            + make_relative_links_absolute(readme, full_name, default_branch)
        )
        page_path.write_text(content, encoding="utf-8")
        imported.append(
            {"name": name, "path": f"repositories/{name}.md", "url": source_url}
        )
        print(f"Imported README from {full_name}.")

    imported.sort(key=lambda item: item["name"].lower())

    if imported:
        overview = [
            "# Repositories",
            "",
            "These pages are generated from the latest README in each public repository.",
            "",
        ]
        for item in imported:
            overview.append(
                f"- [{item['name']}]({Path(item['path']).name}) "
                f"— [GitHub]({item['url']})"
            )
        (OUTPUT_DIR / "index.md").write_text(
            "\n".join(overview) + "\n", encoding="utf-8"
        )

        repository_nav = {
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
        nav.insert(about_index, repository_nav)

    GENERATED_CONFIG.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Generated MkDocs configuration with {len(imported)} README page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
