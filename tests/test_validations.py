import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pytest

from src.main import (
    PRICE_MAX,
    PRICE_MIN,
    STOCK_MAX,
    STOCK_MIN,
    coerce_decimal,
    coerce_int,
    validate_product_payload,
)


def test_coerce_decimal_accepts_valid_value():
    result = coerce_decimal('123.45', 'precio')
    assert float(result) == pytest.approx(123.45)


def test_coerce_decimal_rejects_invalid_number():
    with pytest.raises(ValueError):
        coerce_decimal('abc', 'precio')


def test_coerce_decimal_respects_limits():
    with pytest.raises(ValueError):
        coerce_decimal(PRICE_MIN - 1, 'precio')
    with pytest.raises(ValueError):
        coerce_decimal(PRICE_MAX + 1, 'precio')


def test_coerce_int_accepts_valid_value():
    assert coerce_int('10', 'stock') == 10


def test_coerce_int_rejects_invalid():
    with pytest.raises(ValueError):
        coerce_int('not-int', 'stock')


def test_coerce_int_respects_limits():
    with pytest.raises(ValueError):
        coerce_int(STOCK_MIN - 1, 'stock')
    with pytest.raises(ValueError):
        coerce_int(STOCK_MAX + 1, 'stock')


def test_validate_product_payload_returns_normalized_values():
    payload = {
        'nombre': 'Producto Demo ',
        'categoria': 'Bebidas',
        'precio': '15.50',
        'stock': '5',
        'min_stock': '2',
    }
    normalized = validate_product_payload(payload)
    assert normalized['nombre'] == 'Producto Demo'
    assert normalized['precio'] == pytest.approx(15.50)
    assert normalized['stock'] == 5
    assert normalized['min_stock'] == 2


def test_validate_product_payload_collects_errors():
    with pytest.raises(ValueError) as exc:
        validate_product_payload({
            'nombre': '',
            'categoria': '',
            'precio': '-1',
            'stock': '-5',
            'min_stock': '999999999',
        })
    message = str(exc.value)
    assert 'obligatorio' in message
    assert 'mayor o igual' in message


def test_coerce_decimal_accepts_currency_variants():
    result = coerce_decimal('$ 1.234,50', 'precio')
    assert float(result) == pytest.approx(1234.50)



def test_coerce_decimal_rejects_alpha_characters():
    with pytest.raises(ValueError):
        coerce_decimal('123abc', 'precio')



def test_coerce_int_accepts_thousand_separators():
    assert coerce_int('1.234', 'stock') == 1234



def test_coerce_int_rejects_fractional_values():
    with pytest.raises(ValueError):
        coerce_int('12,5', 'stock')
