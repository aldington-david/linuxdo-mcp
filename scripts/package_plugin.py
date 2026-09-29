"""只打包允许的文件；--app-id 将本机连接替换为已注册的 ChatGPT 连接。"""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package(output, app_id=None, python_command=None, plugin_name=None):
    if app_id and not re.fullmatch(r"(?:plugin_)?asdk_app_[A-Za-z0-9_-]+", app_id):
        raise ValueError("请提供 ChatGPT 创建连接后得到的真实 plugin_asdk_app... ID。")
    if app_id:
        app_id = app_id.removeprefix("plugin_")
    if plugin_name and (not app_id or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", plugin_name)
                        or len(plugin_name) > 64):
        raise ValueError("plugin-name 仅用于已绑定的云端插件更新，需使用原插件的有效技术名称。")
    names = ["plugin.json", ".codex-plugin/plugin.json", "README.md",
             "skills/linuxdo-research/SKILL.md", "skills/linuxdo-research/agents/openai.yaml"]
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs").glob("*.md"))]
    files = {name: (ROOT / name).read_bytes() for name in names}
    if plugin_name:
        for name in ("plugin.json", ".codex-plugin/plugin.json"):
            manifest = json.loads(files[name])
            manifest["name"] = plugin_name
            files[name] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    if app_id:
        manifest = json.loads(files[".codex-plugin/plugin.json"])
        manifest.pop("mcpServers", None)
        manifest["apps"] = "./.app.json"
        files[".codex-plugin/plugin.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        files[".app.json"] = json.dumps({"apps": {"linuxdo": {"id": app_id}}}).encode()
    else:
        for name in ("mcp.json", ".mcp.json"):
            config = json.loads((ROOT / name).read_text(encoding="utf-8"))
            if python_command:
                config["mcpServers"]["linuxdo"]["command"] = str(python_command)
            files[name] = json.dumps(config, ensure_ascii=False, indent=2).encode()
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
    parser.add_argument("--python", help="本机包使用的 Python 绝对路径；该环境需已安装 linuxdo-mcp")
    parser.add_argument("--plugin-name", help="更新已有 ChatGPT 插件时保留其技术名称，可从下载的 ZIP 中读取")
    args = parser.parse_args()
    output = args.output or ROOT / "dist" / (
        "linuxdo-mcp-chatgpt.zip" if args.app_id else "linuxdo-mcp-local.zip")
    print(package(output, args.app_id, args.python, args.plugin_name))


if __name__ == "__main__":
    main()
