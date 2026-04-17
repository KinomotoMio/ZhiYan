from app.services.skill_runtime.contracts import (
    build_skill_activation_record,
    build_skill_catalog_context,
    build_skill_prompt_bundle,
    resolve_default_skill_name,
    resolve_skill_name,
)


def test_default_skill_resolution_prefers_slidev_and_html_defaults():
    assert resolve_default_skill_name("slidev") == "slidev-default"
    assert resolve_default_skill_name("html") == "html-default"
    assert resolve_default_skill_name("structured") is None


def test_resolve_skill_name_uses_default_when_missing():
    assert resolve_skill_name(requested_skill=None, output_mode="slidev") == "slidev-default"
    assert resolve_skill_name(requested_skill=None, output_mode="html") == "html-default"


def test_build_skill_prompt_bundle_includes_skill_and_reference_text():
    bundle = build_skill_prompt_bundle("slidev-default")
    assert "slidev-default" in bundle
    assert "Slidev Default" in bundle
    assert "references/generation-contract.md" in bundle


def test_build_skill_catalog_context_mentions_mode_and_base_skill():
    context = build_skill_catalog_context(output_mode="slidev", requested_skill="slidev-default")
    assert "当前 output_mode: slidev" in context
    assert "当前基础 skill: slidev-default" in context


def test_build_skill_activation_record_includes_scope_and_resources():
    activation = build_skill_activation_record("slidev-default", source="harness", reason="output_mode_default")
    assert activation is not None
    assert activation["skill_id"] == "slidev-default"
    assert activation["source"] == "harness"
    assert activation["scope"] == "builtin"
    assert "references/generation-contract.md" in activation["resources"]
