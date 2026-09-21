from app.agent.policy import authorize_tool


def test_protected_catalogue_capabilities():
    assert authorize_tool("catalogue_generation", "read_product_blob", "protected").allowed
    decision = authorize_tool("catalogue_generation", "download_and_execute_script", "protected")
    assert not decision.allowed
    assert "outside the capability set" in decision.reason


def test_vulnerable_demo_allows_requested_tool():
    assert authorize_tool("catalogue_generation", "download_and_execute_script", "vulnerable").allowed
