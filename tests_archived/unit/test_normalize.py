from app.services.normalize import normalize_symbol


def test_normalize_stock_class_to_hyphen():
    assert normalize_symbol("brk.b") == "BRK-B"
    assert normalize_symbol("RDS.a") == "RDS-A"


def test_exchange_suffix_kept_with_dot():
    assert normalize_symbol("7203.t") == "7203.T"
    assert normalize_symbol("ry.to") == "RY.TO"
    assert normalize_symbol("bhp.ax") == "BHP.AX"
    assert normalize_symbol("azn.l") == "AZN.L"


def test_multidot_respected():
    assert normalize_symbol("ABC.PR.A.TO") == "ABC.PR.A.TO"
