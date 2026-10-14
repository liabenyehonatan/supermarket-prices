# Builders for tiny Shufersal-format dump files used by the parse tests.

from pathlib import Path

CHAIN = "7290027600007"


def price_xml(store_id: str, items: list[tuple[str, str, str]]) -> str:
    """items: (barcode, price, 'YYYY-MM-DD HH:MM')"""
    body = "".join(
        f"""<Item><PriceUpdateDate>{when}</PriceUpdateDate><ItemCode>{code}</ItemCode>
<ItemType>1</ItemType><ItemName>מוצר {code}</ItemName><ManufacturerName>יצרן</ManufacturerName>
<UnitQty>גרמים</UnitQty><Quantity>100.00</Quantity><bIsWeighted>0</bIsWeighted>
<UnitOfMeasure>100 גרם</UnitOfMeasure><QtyInPackage>0</QtyInPackage>
<ItemPrice>{price}</ItemPrice><UnitOfMeasurePrice>1.00</UnitOfMeasurePrice>
<AllowDiscount>1</AllowDiscount><ItemStatus>1</ItemStatus></Item>"""
        for code, price, when in items
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?><root>'
        f"<ChainId>{CHAIN}</ChainId><SubChainId>005</SubChainId><StoreId>{store_id}</StoreId>"
        f'<BikoretNo>0</BikoretNo><Items Count="{len(items)}">{body}</Items></root>'
    )


def stores_xml(stores: list[tuple[str, str, str]]) -> str:
    """stores: (store_id, name, city)"""
    body = "".join(
        f"<STORE><SUBCHAINID>1</SUBCHAINID><STOREID>{sid}</STOREID><BIKORETNO>7</BIKORETNO>"
        f"<STORETYPE>1</STORETYPE><CHAINNAME>שופרסל</CHAINNAME><SUBCHAINNAME>שלי</SUBCHAINNAME>"
        f"<STORENAME>{name}</STORENAME><ADDRESS>רחוב 1</ADDRESS><CITY>{city}</CITY>"
        f"<ZIPCODE>1</ZIPCODE></STORE>"
        for sid, name, city in stores
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><asx:abap xmlns:asx="http://www.sap.com/abapxml" '
        f'version="1.0"><asx:values><CHAINID>{CHAIN}</CHAINID><STORES>{body}</STORES></asx:values></asx:abap>'
    )


def write(folder: Path, name: str, content: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(content, encoding="utf-8")
    return path


def price_name(store: str, stamp: str, full: bool = True) -> str:
    """stamp like '20260512-030442'"""
    return f"{'PriceFull' if full else 'Price'}{CHAIN}-001-{store}-{stamp}.xml"


STORES_NAME = f"Stores{CHAIN}-000-202605120201.xml"


def items_xml(codes: list[str]) -> str:
    # One element per line, like the chains' files: the library's parser loses nested items from a one-line file.
    return "".join(
        f"<Item>\n<ItemCode>{c}</ItemCode>\n<ItemType>1</ItemType>\n<IsGiftItem>0</IsGiftItem>\n</Item>\n"
        for c in codes
    )


def promo_xml(store_id: str, promos: list[dict]) -> str:
    """promos: dicts with id, desc, items (barcodes), optional start/end 'YYYY-MM-DD', reward, min_qty, price."""
    body = "".join(
        f"""<Promotion><PromotionId>{p['id']}</PromotionId><AllowMultipleDiscounts>1</AllowMultipleDiscounts>
<PromotionDescription>{p['desc']}</PromotionDescription><PromotionUpdateDate>2026-05-01 12:00</PromotionUpdateDate>
<PromotionStartDate>{p.get('start', '2026-05-01')}</PromotionStartDate><PromotionStartHour>00:00</PromotionStartHour>
<PromotionEndDate>{p.get('end', '2026-12-31')}</PromotionEndDate><PromotionEndHour>23:59</PromotionEndHour>
<IsWeightedPromo>0</IsWeightedPromo><MinQty>{p.get('min_qty', '2.000')}</MinQty><DiscountType>0</DiscountType>
<RewardType>{p.get('reward', '1')}</RewardType><DiscountRate>0</DiscountRate>
<DiscountedPrice>{p.get('price', '18.00')}</DiscountedPrice><MinNoOfItemOfered>10</MinNoOfItemOfered><Remark />
<PromotionItems Count="{len(p['items'])}">
{items_xml(p['items'])}</PromotionItems>
</Promotion>"""
        for p in promos
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?><root>'
        f"<ChainId>{CHAIN}</ChainId><SubChainId>001</SubChainId><StoreId>{store_id}</StoreId>"
        f'<BikoretNo>0</BikoretNo><Promotions>{body}</Promotions></root>'
    )


def promo_name(store: str, stamp: str) -> str:
    """stamp like '20260512-030442' (same shape as price_name)"""
    return f"PromoFull{CHAIN}-001-{store}-{stamp}.xml"
