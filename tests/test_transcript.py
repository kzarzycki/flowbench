from dataclasses import dataclass

from flowbench.transcript import render_transcript, to_jsonable


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


def test_to_jsonable_pydantic_style_model():
    class Ev:
        def model_dump(self, mode=None):
            return {"conversation_id": "conv_1", "delta": "hi"}

    assert to_jsonable(Ev()) == {"__type__": "Ev", "conversation_id": "conv_1", "delta": "hi"}


def test_to_jsonable_model_dump_that_raises_falls_back_to_repr():
    class Ev:
        def model_dump(self, mode=None):
            raise ValueError("not serializable")

        def __repr__(self):
            return "<Ev broken>"

    assert to_jsonable(Ev()) == {"__type__": "Ev", "repr": "<Ev broken>"}


def test_to_jsonable_dataclass():
    @dataclass
    class Ev:
        conversation_id: str

    assert to_jsonable(Ev("conv_2")) == {"__type__": "Ev", "conversation_id": "conv_2"}


def test_to_jsonable_plain_object_is_a_truncated_repr():
    class Ev:
        def __repr__(self):
            return "x" * 400

    out = to_jsonable(Ev())
    assert out["__type__"] == "Ev" and len(out["repr"]) == 300
