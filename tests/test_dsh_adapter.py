import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("dsh_adapter", ROOT / "scripts" / "dsh_adapter.py")
assert SPEC and SPEC.loader
dsh_adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dsh_adapter)


def test_dsh_manifest_matches_release_plugin_and_skill_contracts():
    manifest = dsh_adapter.load_manifest(ROOT)
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert manifest["version"] == plugin["version"] == version
    assert manifest["skills"] == [Path(path).name for path in plugin["skills"]]
    assert len(manifest["skills"]) == 10
    assert dsh_adapter.validate_sources(ROOT, manifest) == []

    for name in manifest["skills"]:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        assert "user-invocable: true" in frontmatter
        assert "compatibility: native" in frontmatter
        assert "requires-command: wewrite" in frontmatter
        assert "allowed-tools:" in frontmatter  # Claude Code compatibility remains intact.


def test_install_doctor_update_and_uninstall(tmp_path):
    dsh_home = tmp_path / "dsh-home"
    first = dsh_adapter.install(ROOT, dsh_home)
    assert {item["action"] for item in first} == {"installed"}

    manifest = dsh_adapter.load_manifest(ROOT)
    for name in manifest["skills"]:
        target = dsh_home / "skills" / name
        assert (target / "SKILL.md").is_file()
        marker = json.loads((target / dsh_adapter.MARKER_NAME).read_text(encoding="utf-8"))
        assert marker["project"] == "wewrite"
        assert marker["skill"] == name

    report = dsh_adapter.doctor(ROOT, dsh_home, skip_cli=True)
    assert report["ok"] is True
    assert len(report["installed_skills"]) == 10

    second = dsh_adapter.install(ROOT, dsh_home)
    assert {item["action"] for item in second} == {"updated"}

    removed = dsh_adapter.uninstall(ROOT, dsh_home)
    assert {item["action"] for item in removed} == {"removed"}
    assert not any((dsh_home / "skills" / name).exists() for name in manifest["skills"])


def test_unmanaged_collision_is_preserved_or_backed_up(tmp_path):
    dsh_home = tmp_path / "dsh-home"
    collision = dsh_home / "skills" / "wewrite"
    collision.mkdir(parents=True)
    sentinel = collision / "user-file.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    try:
        dsh_adapter.install(ROOT, dsh_home)
    except dsh_adapter.AdapterError as exc:
        assert "--force" in str(exc)
    else:
        raise AssertionError("unmanaged collision must stop a normal install")
    assert sentinel.read_text(encoding="utf-8") == "keep me"

    results = dsh_adapter.install(ROOT, dsh_home, force=True)
    wewrite_result = next(item for item in results if item["skill"] == "wewrite")
    assert wewrite_result["action"] == "backed-up-and-installed"
    backup = Path(wewrite_result["backup"])
    assert (backup / "user-file.txt").read_text(encoding="utf-8") == "keep me"
    assert (collision / "SKILL.md").is_file()


def test_uninstall_skips_unmanaged_directory(tmp_path):
    dsh_home = tmp_path / "dsh-home"
    target = dsh_home / "skills" / "wewrite"
    target.mkdir(parents=True)
    (target / "user-file.txt").write_text("keep me", encoding="utf-8")

    results = dsh_adapter.uninstall(ROOT, dsh_home)
    item = next(result for result in results if result["skill"] == "wewrite")
    assert item["action"] == "skipped-unmanaged"
    assert (target / "user-file.txt").read_text(encoding="utf-8") == "keep me"


def test_dsh_documentation_has_install_runtime_and_safety_contracts():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "deepseek-harness.md").read_text(encoding="utf-8")
    combined = readme + docs

    assert "$DSH_HOME/skills" in combined
    assert "npx @deepseek-ai/dsh web" in combined
    assert "scripts/dsh_adapter.py doctor" in combined
    assert "Developer Preview" in docs
    assert "明确授权" in docs
    assert "backup-" in docs
