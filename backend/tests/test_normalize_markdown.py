"""normalize_markdown() 单元测试"""

from app.services.document.parser import normalize_markdown


def test_remove_empty_image_placeholders():
    text = "前文\n![]()\n后文\n![ alt ]()\n尾"
    result = normalize_markdown(text)
    assert "![]()" not in result
    assert "![ alt ]()" not in result
    assert "前文" in result
    assert "后文" in result


def test_remove_image_tag():
    text = "line1\n[image]\nline2"
    result = normalize_markdown(text)
    assert "[image]" not in result
    assert "line1" in result
    assert "line2" in result


def test_remove_page_numbers():
    text = "content\n- 12 -\nmore\n— 3 —\nend\n- Page 5 -"
    result = normalize_markdown(text)
    assert "- 12 -" not in result
    assert "— 3 —" not in result
    assert "- Page 5 -" not in result


def test_merge_duplicate_separators():
    text = "above\n---\n---\n---\nbelow"
    result = normalize_markdown(text)
    # 只保留一个 ---
    assert result.count("---") == 1


def test_merge_inline_breaks():
    # 中文续行
    text = "这是一个很长的句\n子需要合并"
    result = normalize_markdown(text)
    assert "句子" in result

    # 英文小写续行
    text2 = "this is a long sen\ntence to merge"
    result2 = normalize_markdown(text2)
    assert "sentence" in result2


def test_no_merge_after_sentence_end():
    text = "第一句话。\n第二句话"
    result = normalize_markdown(text)
    assert "。\n第二句话" in result


def test_collapse_blank_lines():
    text = "a\n\n\n\n\n\nb"
    result = normalize_markdown(text)
    # 最多两个空行 (三个 \n)
    assert "\n\n\n\n" not in result
    assert "a\n\n\nb" == result


def test_strip_trailing_whitespace():
    text = "hello   \nworld\t\nend"
    result = normalize_markdown(text)
    for line in result.split("\n"):
        assert line == line.rstrip()


def test_preserves_normal_content():
    text = "# Title\n\nSome **bold** text.\n\n- item 1\n- item 2"
    result = normalize_markdown(text)
    assert "# Title" in result
    assert "**bold**" in result
    assert "- item 1" in result
