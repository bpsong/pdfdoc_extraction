"""Validate and update cache versions for frontend feature-module graphs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURES = {
    "admin-audit": "admin_audit.html",
    "admin-dashboard": "admin_dashboard.html",
    "config-validation": "config_validation.html",
    "extraction-results": "extraction_results.html",
    "failures": "failures.html",
    "human-review": "human_review.html",
    "pipeline-config": "pipeline_config.html",
    "processing-overview": "processing_overview.html",
    "reports": "reports.html",
    "review-queue": "review_queue.html",
    "schema-editor": "schema_editor.html",
    "settings": "settings.html",
    "split-results": "split_results.html",
    "task-catalog": "task_catalog.html",
    "upload-process": "upload_process.html",
    "watch-folders": "watch_folders.html",
}
VERSION_PATTERN = re.compile(r"\?v=([A-Za-z0-9._-]+)")
IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s*)[\"'](\./[^\"']+\.js)\?v=([A-Za-z0-9._-]+)[\"']"
)


def _entry_version(root: Path, feature: str, template_name: str) -> str:
    template = (root / "web/templates" / template_name).read_text(encoding="utf-8")
    pattern = re.compile(
        rf"/static/js/{re.escape(feature)}/index\.js\?v=([A-Za-z0-9._-]+)"
    )
    match = pattern.search(template)
    if not match:
        raise ValueError(f"{template_name}: missing versioned {feature} entry")
    return match.group(1)


def check_features(root: Path = ROOT) -> list[str]:
    """Return release-version inconsistencies across feature-local imports."""

    errors: list[str] = []
    for feature, template_name in FEATURES.items():
        try:
            expected = _entry_version(root, feature, template_name)
        except ValueError as error:
            errors.append(str(error))
            continue
        feature_dir = root / "web/static/js" / feature
        for module_path in feature_dir.glob("*.js"):
            source = module_path.read_text(encoding="utf-8")
            for relative_path, version in IMPORT_PATTERN.findall(source):
                if version != expected:
                    errors.append(
                        f"{module_path.relative_to(root)} imports {relative_path} "
                        f"at {version}; expected {expected}"
                    )
    return errors


def bump_feature(feature: str, version: str, root: Path = ROOT) -> None:
    """Atomically align a feature entry and its local imports to one version."""

    if feature not in FEATURES:
        raise ValueError(f"Unknown feature: {feature}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        raise ValueError("Version may contain only letters, digits, dot, dash, underscore")

    template_path = root / "web/templates" / FEATURES[feature]
    template = template_path.read_text(encoding="utf-8")
    entry_pattern = re.compile(
        rf"(/static/js/{re.escape(feature)}/index\.js\?v=)[A-Za-z0-9._-]+"
    )
    updated_template, count = entry_pattern.subn(rf"\g<1>{version}", template)
    if count != 1:
        raise ValueError(f"Expected one {feature} entry in {template_path.name}")
    template_path.write_text(updated_template, encoding="utf-8")

    for module_path in (root / "web/static/js" / feature).glob("*.js"):
        source = module_path.read_text(encoding="utf-8")
        updated = IMPORT_PATTERN.sub(
            lambda match: match.group(0).replace(
                f"?v={match.group(2)}", f"?v={version}"
            ),
            source,
        )
        module_path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    bump = subparsers.add_parser("bump")
    bump.add_argument("feature", choices=sorted(FEATURES))
    bump.add_argument("version")
    args = parser.parse_args()

    if args.command == "bump":
        bump_feature(args.feature, args.version)
    errors = check_features()
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"Validated {len(FEATURES)} frontend feature release graphs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
