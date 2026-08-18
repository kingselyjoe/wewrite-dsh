#!/usr/bin/env python3
"""Install and validate WeWrite skills for DeepSeek Harness.

DSH discovers folder-per-skill packages below ``$DSH_HOME/skills``.  This
adapter deliberately copies the skills instead of relying on symlinks so the
same installation flow works on Windows, macOS, Linux, containers and CI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "dsh" / "manifest.json"
MARKER_NAME = ".wewrite-dsh.json"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AdapterError(RuntimeError):
    """A user-actionable adapter failure."""


def load_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest_path = repo_root / "dsh" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"无法读取 DSH manifest：{manifest_path}: {exc}") from exc

    skills = manifest.get("skills")
    if manifest.get("schema") != "wewrite-dsh-adapter/v1" or not isinstance(skills, list):
        raise AdapterError(f"无效的 DSH manifest：{manifest_path}")
    if not skills or len(skills) != len(set(skills)):
        raise AdapterError("DSH manifest 的 skills 必须非空且不能重复")
    invalid = [name for name in skills if not isinstance(name, str) or not NAME_RE.fullmatch(name)]
    if invalid:
        raise AdapterError(f"DSH manifest 包含非法 skill 名称：{invalid}")
    return manifest


def resolve_dsh_home(value: str | None) -> Path:
    raw = value or os.environ.get("DSH_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".dsh"


def _frontmatter_value(skill_file: Path, key: str) -> str | None:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    match = re.search(rf"(?m)^{re.escape(key)}:\s*([^\n]*)$", text[4:end])
    if not match:
        return None
    return match.group(1).strip().strip('"\'')


def validate_sources(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    version_file = repo_root / "VERSION"
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        issues.append(f"无法读取 VERSION：{exc}")
        version = ""
    if manifest.get("version") != version:
        issues.append(f"manifest version {manifest.get('version')!r} 与 VERSION {version!r} 不一致")

    for name in manifest["skills"]:
        skill_file = repo_root / "skills" / name / "SKILL.md"
        if not skill_file.is_file():
            issues.append(f"缺少 {skill_file}")
            continue
        if _frontmatter_value(skill_file, "name") != name:
            issues.append(f"{name}/SKILL.md 的 frontmatter name 不匹配")
        if _frontmatter_value(skill_file, "description") is None:
            issues.append(f"{name}/SKILL.md 缺少 description")
        if _frontmatter_value(skill_file, "user-invocable") != "true":
            issues.append(f"{name}/SKILL.md 缺少 user-invocable: true")
    return issues


def _read_marker(target: Path) -> dict[str, Any] | None:
    marker = target / MARKER_NAME
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if value.get("schema") == "wewrite-dsh-install/v1" else None


def _is_managed(target: Path, skill_name: str) -> bool:
    marker = _read_marker(target)
    return bool(marker and marker.get("project") == "wewrite" and marker.get("skill") == skill_name)


def _unique_backup(target: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = target.with_name(f"{target.name}.backup-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = target.with_name(f"{target.name}.backup-{stamp}-{counter}")
        counter += 1
    return candidate


def _assert_direct_child(target: Path, skills_root: Path) -> None:
    if target.parent.resolve() != skills_root.resolve():
        raise AdapterError(f"拒绝操作 skills 根目录以外的路径：{target}")


def install(repo_root: Path, dsh_home: Path, force: bool = False) -> list[dict[str, str]]:
    manifest = load_manifest(repo_root)
    source_issues = validate_sources(repo_root, manifest)
    if source_issues:
        raise AdapterError("源包校验失败：\n- " + "\n- ".join(source_issues))

    skills_root = dsh_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    collisions = []
    for name in manifest["skills"]:
        target = skills_root / name
        _assert_direct_child(target, skills_root)
        if target.exists() and not _is_managed(target, name):
            collisions.append(target)
    if collisions and not force:
        paths = "\n- ".join(str(path) for path in collisions)
        raise AdapterError(
            "发现非本工具管理的同名目录，未做修改。使用 --force 时会先备份：\n- " + paths
        )

    results: list[dict[str, str]] = []
    for name in manifest["skills"]:
        source = repo_root / "skills" / name
        target = skills_root / name
        temp_parent = Path(tempfile.mkdtemp(prefix=f".{name}.install-", dir=skills_root))
        staged = temp_parent / name
        shutil.copytree(source, staged)
        marker = {
            "schema": "wewrite-dsh-install/v1",
            "project": "wewrite",
            "skill": name,
            "version": manifest["version"],
            "source": str(repo_root.resolve()),
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        (staged / MARKER_NAME).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        action = "installed"
        backup: Path | None = None
        old_managed: Path | None = None
        if target.exists():
            if _is_managed(target, name):
                old_managed = target.with_name(f".{name}.previous")
                suffix = 1
                while old_managed.exists():
                    old_managed = target.with_name(f".{name}.previous-{suffix}")
                    suffix += 1
                target.rename(old_managed)
                action = "updated"
            else:
                backup = _unique_backup(target)
                target.rename(backup)
                action = "backed-up-and-installed"

        try:
            staged.rename(target)
        except Exception:
            if old_managed and old_managed.exists() and not target.exists():
                old_managed.rename(target)
            elif backup and backup.exists() and not target.exists():
                backup.rename(target)
            raise
        finally:
            if temp_parent.exists():
                shutil.rmtree(temp_parent)
        if old_managed and old_managed.exists():
            shutil.rmtree(old_managed)

        item = {"skill": name, "action": action, "target": str(target)}
        if backup:
            item["backup"] = str(backup)
        results.append(item)
    return results


def doctor(repo_root: Path, dsh_home: Path, skip_cli: bool = False) -> dict[str, Any]:
    manifest = load_manifest(repo_root)
    source_issues = validate_sources(repo_root, manifest)
    skills_root = dsh_home / "skills"
    install_issues: list[str] = []
    installed: list[str] = []
    for name in manifest["skills"]:
        target = skills_root / name
        skill_file = target / "SKILL.md"
        if not skill_file.is_file():
            install_issues.append(f"未安装：{target}")
            continue
        installed.append(name)
        if _frontmatter_value(skill_file, "name") != name:
            install_issues.append(f"安装副本 frontmatter 不匹配：{skill_file}")
        if not _is_managed(target, name):
            install_issues.append(f"安装目录不是由 WeWrite DSH adapter 管理：{target}")

    cli_path = shutil.which("wewrite")
    runtime_path = shutil.which("dsh") or shutil.which("npx")
    cli_issues = [] if skip_cli or cli_path else ["PATH 中未找到 wewrite CLI"]
    errors = [*source_issues, *install_issues, *cli_issues]
    warnings = [] if runtime_path else ["未找到 dsh 或 npx；可用 npx @deepseek-ai/dsh 启动 DSH"]
    return {
        "ok": not errors,
        "repo": str(repo_root.resolve()),
        "dsh_home": str(dsh_home.resolve()),
        "skills_root": str(skills_root.resolve()),
        "expected_skills": len(manifest["skills"]),
        "installed_skills": installed,
        "wewrite_cli": cli_path,
        "dsh_runtime": runtime_path,
        "errors": errors,
        "warnings": warnings,
    }


def uninstall(repo_root: Path, dsh_home: Path) -> list[dict[str, str]]:
    manifest = load_manifest(repo_root)
    skills_root = dsh_home / "skills"
    results: list[dict[str, str]] = []
    for name in manifest["skills"]:
        target = skills_root / name
        _assert_direct_child(target, skills_root)
        if not target.exists():
            results.append({"skill": name, "action": "absent", "target": str(target)})
        elif _is_managed(target, name):
            shutil.rmtree(target)
            results.append({"skill": name, "action": "removed", "target": str(target)})
        else:
            results.append({"skill": name, "action": "skipped-unmanaged", "target": str(target)})
    return results


def _print_results(results: list[dict[str, str]]) -> None:
    for item in results:
        suffix = f"（备份：{item['backup']}）" if item.get("backup") else ""
        print(f"{item['action']:>24}  {item['skill']} -> {item['target']}{suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeWrite 的 DeepSeek Harness 安装与诊断工具")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--dsh-home", help="DSH_HOME 路径；默认读取环境变量或 ~/.dsh")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install", help="安装或更新 10 个 WeWrite skills")
    install_parser.add_argument("--force", action="store_true", help="备份并替换非本工具管理的同名目录")
    doctor_parser = subparsers.add_parser("doctor", help="检查源包、skill 安装和 CLI")
    doctor_parser.add_argument("--skip-cli", action="store_true", help="只验证 skill，忽略 CLI 是否在 PATH")
    subparsers.add_parser("uninstall", help="仅卸载由本工具管理的 WeWrite skills")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    dsh_home = resolve_dsh_home(args.dsh_home)
    try:
        if args.command == "install":
            result: Any = install(repo_root, dsh_home, force=args.force)
            exit_code = 0
        elif args.command == "uninstall":
            result = uninstall(repo_root, dsh_home)
            exit_code = 0
        else:
            result = doctor(repo_root, dsh_home, skip_cli=args.skip_cli)
            exit_code = 0 if result["ok"] else 1
    except AdapterError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"错误：{exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "doctor":
        print("✓ DSH 检查通过" if result["ok"] else "✗ DSH 检查失败")
        print(f"  Skills: {len(result['installed_skills'])}/{result['expected_skills']} @ {result['skills_root']}")
        print(f"  wewrite CLI: {result['wewrite_cli'] or '未找到'}")
        print(f"  DSH runtime: {result['dsh_runtime'] or '未找到'}")
        for message in result["errors"]:
            print(f"  ERROR: {message}")
        for message in result["warnings"]:
            print(f"  WARN: {message}")
    else:
        _print_results(result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
