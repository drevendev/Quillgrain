"""Synthetic explicit example-pool selection; never an author corpus."""
import copy
import pytest
from quillgrain.compose import compile_context
from quillgrain.io import QGError


def test_explicit_pool_replaces_defaults_without_losing_rules(pack, save):
    base={"language":"ru","register":"essay","channel":"narration","permissions":pack["permissions"],
          "visibility":"public","role":"positive","priority":50,"authorship":"synthetic_ai_prepared","status":"REVIEWED"}
    pack["examples"]=[
        dict(base,id="default.example",source_id="default",work_id="default",text="A synthetic neutral example.",tags=[]),
        dict(base,id="chosen.example",source_id="chosen",work_id="chosen",text="A distinct synthetic style example.",tags=["examples.chosen"])]
    path=save(pack)
    before,_=compile_context(path,tags=["examples.chosen"])
    after,_=compile_context(path,tags=["examples.chosen"],example_pool="examples.chosen")
    assert len(before["examples_selected"])==2
    assert [e["id"] for e in after["examples_selected"]]==["chosen.example"]
    assert {"id":"default.example","reason":"example_pool"} in after["examples_omitted"]
    assert before["rules_applied"]==after["rules_applied"]


def test_missing_pool_does_not_silently_fall_back(pack,save):
    path=save(pack)
    with pytest.raises(QGError,match="EXAMPLE_POOL_TAG_REQUIRED"):
        compile_context(path,example_pool="examples.chosen")
    context,_=compile_context(path,tags=["examples.chosen"],example_pool="examples.chosen")
    assert not context["examples_selected"]
