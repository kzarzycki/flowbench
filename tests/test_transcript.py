from flowbench.transcript import render_transcript


def test_render_transcript_labels_roles_and_skips_empty():
    items = [
        {"type": "message", "role": "user", "content": "the kickoff"},
        {"type": "message", "role": "assistant", "content": "what should unknown flags return?"},
        {"type": "message", "role": "assistant", "content": "   "},  # skipped
        {"type": "tool_call", "name": "Write"},  # non-message skipped
        {"type": "message", "role": "user", "content": "a 404"},
    ]
    md = render_transcript(items)
    assert "## user" in md and "## assistant" in md
    assert "the kickoff" in md and "what should unknown flags return?" in md and "a 404" in md
    assert md.count("\n## ") == 3  # 3 kept messages, title uses a single "#"


def test_item_text_content_shapes():
    from flowbench.transcript import item_text

    assert item_text({"content": "plain"}) == "plain"
    assert item_text({"content": [{"type": "text", "text": "a"}, {"type": "image"}, "junk"]}) == "a"
    assert item_text({"content": 42}) == ""
    assert item_text({}) == ""
