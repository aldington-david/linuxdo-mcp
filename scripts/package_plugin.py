"""只打包允许的文件；--app-id 将本机连接替换为已注册的 ChatGPT 连接。"""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package(output, app_id=None):
    if app_id and not re.fullmatch(r"(?:plugin_)?asdk_app_[A-Za-z0-9_-]+", app_id):
        raise ValueError("请提供 ChatGPT 创建连接后得到的真实 plugin_asdk_app... ID。")
    names = ["plugin.json", ".codex-plugin/plugin.json", "README.md",
             "skills/linuxdo-research/SKILL.md", "skills/linuxdo-research/agents/openai.yaml"]
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs").glob("*.md"))]
    files = {name: (ROOT / name).read_bytes() for name in names}
    if app_id:
        manifest = json.loads(files[".codex-plugin/plugin.json"])
        manifest.pop("mcpServers", None)
        manifest["apps"] = "./.app.json"
        files[".codex-plugin/plugin.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        files[".app.json"] = json.dumps({"apps": {"linuxdo": {"id": app_id}}}).encode()
    else:
        for name in ("mcp.json", ".mcp.json"):
            files[name] = (ROOT / name).read_bytes()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", help="自己在 ChatGPT 注册的连接 ID；不填则生成本机插件包")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "dist" / (
        "linuxdo-mcp-chatgpt.zip" if args.app_id else "linuxdo-mcp-local.zip")
    print(package(output, args.app_id))


if __name__ == "__main__":
    main()
