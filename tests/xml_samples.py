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
