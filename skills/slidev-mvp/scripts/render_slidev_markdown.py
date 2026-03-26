import json
import sys


def _load_input() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def _coerce_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _render_slide(item: dict) -> str:
    title = str(item.get("title") or "Untitled").strip()
    brief = str(item.get("content_brief") or "").strip()
    points = item.get("key_points") or []
    role = str(item.get("suggested_slide_role") or "narrative").strip()

    lines = ["---", f"layout: {role if role else 'default'}", "---", f"## {title}", ""]
    if brief:
        lines.extend([brief, ""])
    if isinstance(points, list) and points:
        for point in points:
            text = str(point).strip()
            if text:
                lines.append(f"- {text}")
    else:
        lines.append("- 待补充内容")
    return "\n".join(lines).rstrip()


def main():
    payload = _load_input()
    parameters = payload.get("parameters") or {}
    title = str(parameters.get("title") or parameters.get("topic") or "ZhiYan Slidev MVP").strip()
    topic = str(parameters.get("topic") or title).strip()
    outline = parameters.get("outline") or {}
    items = outline.get("items") or []
    theme = str(parameters.get("theme") or "default").strip()
    paginate = _coerce_bool(parameters.get("paginate"), default=True)

    header = [
        "---",
        f"theme: {theme}",
        f"title: {title}",
        f"info: {topic}",
        f"paginate: {'true' if paginate else 'false'}",
        "---",
        "",
        f"# {title}",
        "",
        f"> {topic}",
    ]
    slides = [_render_slide(item) for item in items if isinstance(item, dict)]
    markdown = "\n".join(header + [""] + slides).strip() + "\n"
    sys.stdout.write(json.dumps({"markdown": markdown}, ensure_ascii=False))


if __name__ == "__main__":
    main()
