from mcp_service.basket_link import build_basket_link


def test_link_format():
    link = build_basket_link("https://sali.example", [("7290000000011", 2), ("7290000000028", 1)])
    assert link == "https://sali.example/basket?items=7290000000011:2,7290000000028:1"


def test_link_none_when_site_url_empty():
    assert build_basket_link("", [("7290000000011", 2)]) is None
