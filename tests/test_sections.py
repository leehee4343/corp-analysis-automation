"""표 연도 인식·문자 값·줄바꿈 라벨 규칙 (샘플 PDF 없이 항상 실행)."""
from backend.parser import sections as S


def test_ledger_uses_header_years_not_fixed_2023_2025():
    lines = ["재무상태표", "단위:천원", "계정명", "2022-12-31", "2023-12-31", "2024-12-31", "감사의견",
             "자산(*)", "1,000", "2,000", "3,000", "부채(*)", "10", "-", "30"]
    table, audit = S.parse_ledger(lines, 0, len(lines))
    assert table["자산(*)"] == {"2022": 1000.0, "2023": 2000.0, "2024": 3000.0}
    assert table["부채(*)"] == {"2022": 10.0, "2023": None, "2024": 30.0}
    assert audit == {}


def test_missing_header_year_column_that_is_empty_is_dropped():
    # 하늘팜: 머리글 연도 2개(2020, 2025)인데 값은 3칸이고 첫 칸은 전부 비어 있음
    lines = ["재무상태표", "단위:천원", "계정명", "2020-12-31", "2025-12-31", "감사의견",
             "자산(*)", "-", "2,412,022", "5,089,451", "유동자산(*)", "-", "1,099,151", "494,315"]
    table, _ = S.parse_ledger(lines, 0, len(lines))
    assert table["자산(*)"] == {"2020": 2412022.0, "2025": 5089451.0}


def test_repeated_account_names_are_not_overwritten():
    lines = ["재무상태표", "단위:천원", "계정명", "2023-12-31", "2024-12-31", "감사의견",
             "건물", "100", "110", "(감가상각누계액)", "10", "20",
             "기계장치", "200", "210", "(감가상각누계액)", "30", "40"]
    table, _ = S.parse_ledger(lines, 0, len(lines))
    assert table["(감가상각누계액)"] == {"2023": 10.0, "2024": 20.0}
    assert table["기계장치 · (감가상각누계액)"] == {"2023": 30.0, "2024": 40.0}


def test_audit_opinions_align_to_most_recent_years():
    lines = ["재무상태표", "단위:천원", "계정명", "2023-12-31", "2024-12-31", "2025-12-31", "감사의견",
             "한정의견(감사범위제한)", "적정의견", "자산(*)", "1", "2", "3"]
    _, audit = S.parse_ledger(lines, 0, len(lines))
    assert audit == {"2024": "한정의견(감사범위제한)", "2025": "적정의견"}


def test_summary_years_come_after_values_and_text_values_kept():
    lines = ["요약재무비율", "단위: %", "순이익증가율", "흑자전환", "적자전환", "12.5", "성장성", "2022", "2023", "2024"]
    table = S.parse_summary(lines, 0, len(lines) - 4, fallback_years=[])
    assert table == {"순이익증가율": {"2022": "흑자전환", "2023": "적자전환", "2024": 12.5}}


def test_summary_falls_back_to_given_years_when_no_header():
    lines = ["요약재무상태표", "단위:백만원", "자산총계", "1", "2", "3"]
    assert S.parse_summary(lines, 0, len(lines), ["2022", "2023", "2024"]) == {
        "자산총계": {"2022": 1.0, "2023": 2.0, "2024": 3.0}}


def test_wrapped_label_is_joined_and_cash_flow_grade_kept():
    lines = ["요약현금흐름분석", "경상활동후의현금", "흐름", "101", "-132", "1,811", "현금흐름등급", "CR3", "CR4", "CR3",
             "구분", "2023", "2024", "2025"]
    table = S.parse_summary(lines, 0, 10, [])
    assert table["경상활동후의현금흐름"] == {"2023": 101.0, "2024": -132.0, "2025": 1811.0}
    assert table["현금흐름등급"] == {"2023": "CR3", "2024": "CR4", "2025": "CR3"}


def test_rank_rows_with_wrapped_company_name():
    lines = ["48위", "농업회사법인유한회사나주평야동강", "알피씨", "31,141", "12월", "412-81-37636", "49위", "명천영농조합법인",
             "31,117", "12월", "403-81-23671", "조영"]
    rows = S.parse_rank_rows(lines, 0, len(lines))
    assert rows[0]["company_name"] == "농업회사법인유한회사나주평야동강알피씨"
    assert rows[0]["business_no"] == "412-81-37636" and rows[0]["representative"] is None
    assert rows[1] == {"rank": 49, "company_name": "명천영농조합법인", "revenue": 31117.0, "settlement_month": "12월",
                       "business_no": "403-81-23671", "representative": "조영"}
