"""영업 관리 공문(PPTX) 생성 테스트 — 템플릿 칸 채우기 · 판정 규칙 · 다운로드 API."""
import io
import itertools
import zipfile
from datetime import date, datetime, timezone
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation

from backend import storage
from backend.app import app
from backend.letter import generator as g
from backend.models import Company, DiagnosisRatings


def _company(bn="111-11-11111", name="농업회사법인테스트종묘(주)", address="경북의성군안계면가상길1(용기리)", **kw):
    data = dict(
        business_no=bn, company_name=name, representative="홍길동", address=address, postal_code="37315",
        founded_date="1983-05-01", industry_name="종자및묘목생산업", company_type="일반법인", credit_grade="bb+",
        income_summary={"매출액": {"2024": 2390.0, "2025": 2250.0}, "영업이익": {"2024": 273.0, "2025": 55.0}},
        balance_summary={"자본총계": {"2025": 1500.0}},
        diagnosis=DiagnosisRatings(growth="양호", profitability="우수", financial_structure="보통이하", debt_repayment="양호", activity="낮음"),
        diagnosis_details={
            "growth": {"indicators": [{"name": "매출액증가율", "company": -6.2, "industry_avg": 22.6},
                                      {"name": "영업이익증가율", "company": -79.8, "industry_avg": 52.2}]},
            "financial_structure": {"indicators": [{"name": "부채비율", "company": 120.1, "industry_avg": 204.4},
                                                   {"name": "유동비율", "company": 56.9, "industry_avg": 740.0}]},
            "debt_repayment": {"indicators": [{"name": "이자보상배수(배)", "company": 2.4, "industry_avg": 4.8}]},
        },
        settlement_date="2025-12-31", parsed_at=datetime.now(timezone.utc),
    )
    data.update(kw)
    return Company(**data)


def _texts(prs) -> list[str]:
    out = []
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.has_text_frame:
                out.append(sh.text_frame.text)
            if sh.has_table:
                out += [c.text for row in sh.table.rows for c in row.cells]
    return out


@pytest.mark.parametrize("address, short", [
    ("경북의성군안계면가상길1(용기리)", "경상북도 의성군 안계면"),
    ("경북영천시가상로10(도남동)", "경상북도 영천시 도남동"),
    ("전남나주시가상길5(운곡동)", "전라남도 나주시 운곡동"),
    ("경북포항시북구흥해읍가상길7(남송리)", "경상북도 포항시 북구 흥해읍"),
    ("경북구미시옥성면가상로8(옥관리)", "경상북도 구미시 옥성면"),
    ("경상북도 군위군 군위읍 가상길 1", "경상북도 군위군 군위읍"),
    (None, "-"),
])
def test_split_address(address, short):
    assert g.split_address(address).short == short


def test_names():
    assert g.short_name("농업회사법인 테스트종묘(주)") == "테스트종묘(주)"
    assert g.short_name("(주)농업회사법인가나다") == "(주)가나다"
    assert g.spaced_name("농업회사법인테스트종묘(주)") == "농업회사법인 테스트종묘(주)"
    assert g.spaced_name("가상영농조합법인") == "가상영농조합법인"
    assert g.doc_number(date(2026, 10, 7), "A", 2) == "FS-2026-1007-A02"
    assert g.doc_number(date(2026, 1, 5), None, 13) == "FS-2026-0105-N13"


def test_render_fills_sample_fields():
    prs = Presentation(io.BytesIO(g.render_letter(_company(), doc_no="FS-2026-1007-A02", issued=date(2026, 10, 7))))
    texts = _texts(prs)
    for expected in ("FS-2026-1007-A02", "2026. 10. 7.", "농업회사법인 테스트종묘(주) 대표이사 홍길동 귀하", "테스트종묘(주)",
                     "종자 및 묘목생산업", "1983년 (업력 43년)", "경상북도 의성군 안계면", "KODATA · 2025년 결산 · 괄호: 전년 또는 업종평균",
                     "22.5 억원", "(23.9억 · −6.2%)", "0.55 억원", "(2.73억 · −79.8%)", "120.1 %", "(업종 204.4%)",
                     "56.9 %", "(업종 740.0%)", "의성군 소재 농업회사법인", "부채비율 120% (업종 204%) · bb+",
                     "안계 사업장 시설 확충 검토", "유동비율 57% · 이자보상 2.4배",
                     "✓ 충족 2", "? 확인 필요 3", "! 보완 필요 1"):
        assert expected in texts, expected
    verdict = next(t for t in texts if t.startswith("기본 자격과 재무구조는 충족합니다."))
    assert "유동성을 보완하는 자금계획" in verdict
    # 오각형 그래프: 등급 -> 점수(우수 90 · 양호 70 · 보통 이하 40 · 낮음 20), 업종평균 50
    chart = next(sh for sh in prs.slides[1].shapes if sh.name == "radar").chart
    assert list(chart.plots[0].categories) == ["성장성(양호)", "수익성\n(우수)", "재무구조\n(보통 이하)", "부채상환능력\n(양호)", "활동성\n(낮음)"]
    assert [list(s.values) for s in chart.plots[0].series] == [[70, 90, 40, 70, 20], [50] * 5]
    assert [s.name for s in chart.plots[0].series] == ["테스트종묘(주)", "동종업종 평균"]


def test_render_handles_missing_data_and_other_region():
    c = _company(address="전남나주시왕곡면가상길2(덕산리)", diagnosis=DiagnosisRatings(), diagnosis_details={}, income_summary={},
                 balance_summary={}, credit_grade=None, founded_date=None, industry_name=None)
    prs = Presentation(io.BytesIO(g.render_letter(c, doc_no="X")))
    texts = _texts(prs)
    assert "나주시 소재 농업회사법인" in texts and "! 보완 필요" in texts  # 경북 밖
    assert "재무진단 자료 없음" in texts
    assert "부채비율 자료없음" in texts and "유동비율 자료없음" in texts


SAMPLE_VERDICT = ("기본 자격과 재무구조는 충족합니다. 투자계획이 확정되면 일반 시설 5억원 또는 스마트팜 최대 10억원 신청을 "
                  "검토할 수 있으며, 유동성을 보완하는 자금계획이 함께 필요합니다.")


def test_every_verdict_fits_two_lines():
    """종합 의견 칸은 두 줄까지만 들어간다: 샘플 원문(두 줄에 들어감)보다 길지 않아야 한다."""
    limit = g._text_width(SAMPLE_VERDICT, 10.0)
    for basic, finance, liquidity in itertools.product(g.JUDGE_STYLE, repeat=3):
        checks = [g.Check("", "", basic, "")] + [g.Check("", "", finance, "")] + [g.Check("", "", "확인 필요", "")] * 3 + [g.Check("", "", liquidity, "")]
        text = "".join(t for t, _ in g.verdict_segments(checks))
        assert g._text_width(text, 10.0) <= limit, text


# ----- 다운로드 API
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.save_company(_company("111-11-11111", "농업회사법인테스트종묘(주)"))
    storage.save_company(_company("222-22-22222", "가상영농조합법인"))
    return TestClient(app)


def _project(client):
    pid = client.post("/api/projects", json={"name": "A사업"}).json()["id"]
    client.post(f"/api/projects/{pid}/companies", json={"business_nos": ["111-11-11111", "222-22-22222"]})
    return pid


def test_download_single_pptx_named_after_company(client):
    pid = _project(client)
    client.patch(f"/api/sales/{pid}/111-11-11111", json={"tier": "A"})
    res = client.post("/api/sales/letters", json={"items": [{"project_id": pid, "business_no": "111-11-11111"}]})
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.presentationml")
    assert unquote(res.headers["content-disposition"].split("''")[1]) == "공문_농업회사법인테스트종묘(주).pptx"
    texts = _texts(Presentation(io.BytesIO(res.content)))
    assert any(t.startswith("FS-") and t.endswith("-A01") for t in texts)


def test_download_many_as_zip_in_request_order(client):
    pid = _project(client)
    items = [{"project_id": pid, "business_no": bn} for bn in ("222-22-22222", "111-11-11111")]
    res = client.post("/api/sales/letters", json={"items": items})
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    assert zf.namelist() == ["공문_가상영농조합법인.pptx", "공문_농업회사법인테스트종묘(주).pptx"]
    first = _texts(Presentation(io.BytesIO(zf.read(zf.namelist()[0]))))
    assert any(t.endswith("-N01") for t in first)  # 등급 분류 미지정 N, 목록 순서대로 일련번호


def test_download_rejects_non_member(client):
    pid = _project(client)
    res = client.post("/api/sales/letters", json={"items": [{"project_id": pid, "business_no": "999-99-99999"}]})
    assert res.status_code == 404
    assert client.post("/api/sales/letters", json={"items": []}).status_code == 422


# ----- 이미지 다운로드 (세로로 긴 PNG 한 장)
from PIL import Image

from backend.letter import image as letter_image


def _fake_pdf(pages=2) -> bytes:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=595.5, height=842).insert_text((72, 72), f"page {i + 1}")
    return doc.tobytes()


def test_pdf_pages_stacked_vertically():
    png = letter_image.pdf_to_long_png(_fake_pdf(2))
    w, h = Image.open(io.BytesIO(png)).size
    page_h = round(842 * letter_image.IMAGE_WIDTH / 595.5)
    assert w == letter_image.IMAGE_WIDTH and abs(h - (page_h * 2 + letter_image.PAGE_GAP)) <= 2


def test_download_images_single_and_zip(client, monkeypatch):
    monkeypatch.setattr(letter_image, "pptx_to_pdfs", lambda files: [_fake_pdf() for _ in files])
    pid = _project(client)
    one = [{"project_id": pid, "business_no": "111-11-11111"}]
    res = client.post("/api/sales/letter-images", json={"items": one})
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert unquote(res.headers["content-disposition"].split("''")[1]) == "공문_농업회사법인테스트종묘(주).png"
    both = one + [{"project_id": pid, "business_no": "222-22-22222"}]
    res = client.post("/api/sales/letter-images", json={"items": both})
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == ["공문_농업회사법인테스트종묘(주).png", "공문_가상영농조합법인.png"]
    assert unquote(res.headers["content-disposition"].split("''")[1]).startswith("공문이미지_2개기업_")


def test_download_images_without_converter(client, monkeypatch):
    monkeypatch.setattr(letter_image, "find_converter", lambda: None)
    pid = _project(client)
    res = client.post("/api/sales/letter-images", json={"items": [{"project_id": pid, "business_no": "111-11-11111"}]})
    assert res.status_code == 503 and "PowerPoint 또는 LibreOffice" in res.json()["detail"]


@pytest.mark.skipif(letter_image.find_converter() is None, reason="PowerPoint·LibreOffice가 없는 환경")
def test_real_conversion_to_long_png():
    png = letter_image.pptx_to_long_pngs([g.render_letter(_company(), doc_no="X")])[0]
    w, h = Image.open(io.BytesIO(png)).size
    assert w == letter_image.IMAGE_WIDTH and h > 4000  # A4 두 쪽


# ----- 이미지(모바일용): 스마트폰 폭에 맞춰 다시 배치한 PNG
from backend.letter import mobile


def test_mobile_png_is_phone_width():
    png = mobile.render_mobile_png(_company(), doc_no="FS-2026-1007-A01", issued=date(2026, 10, 7))
    w, h = Image.open(io.BytesIO(png)).size
    assert w == 1080 and h > 8000  # 360dp x 3배, 위아래로 긴 한 장


def test_mobile_png_without_financial_data():
    c = _company(diagnosis=DiagnosisRatings(), diagnosis_details={}, income_summary={}, balance_summary={},
                 credit_grade=None, founded_date=None, industry_name=None, address=None)
    assert Image.open(io.BytesIO(mobile.render_mobile_png(c, doc_no="X"))).width == 1080


def test_mobile_layout_wraps_within_width():
    width = 300
    runs = [("아주긴어절이한줄보다길어서글자단위로잘라야하는경우" * 2, False, "#000"), (" 일반 문장 이어서 씁니다", True, "#000")]
    for line in mobile.layout(runs, width, 14):
        t, b, _, x = line[-1]
        assert x + mobile.font(14, b).getlength(t.rstrip()) <= width + 1
    # 줄바꿈 없는 공백(U+00A0)으로 묶은 '낮음 20'은 나뉘지 않는다
    lines = mobile.layout([("가" * 30 + " 낮음\u00a020", False, "#000")], mobile.font(12, False).getlength("가" * 31), 12)
    assert any("낮음\u00a020" in t for t, *_ in lines[-1])


def test_download_mobile_images(client):
    pid = _project(client)
    one = [{"project_id": pid, "business_no": "111-11-11111"}]
    res = client.post("/api/sales/letter-mobile-images", json={"items": one})
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert unquote(res.headers["content-disposition"].split("''")[1]) == "공문_농업회사법인테스트종묘(주)_모바일.png"
    both = one + [{"project_id": pid, "business_no": "222-22-22222"}]
    res = client.post("/api/sales/letter-mobile-images", json={"items": both})
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == [
        "공문_농업회사법인테스트종묘(주)_모바일.png", "공문_가상영농조합법인_모바일.png"]


# ----- 공문(HTML) 공유 링크 /l/{code}: 로그인 없이 열림, 90일 유효, 문서번호·시행일자는 만든 날로 고정
def test_letter_link_created_once_and_reused(client):
    pid = _project(client)
    client.patch(f"/api/sales/{pid}/111-11-11111", json={"tier": "B"})
    first = client.post(f"/api/sales/{pid}/111-11-11111/letter-link").json()
    assert len(first["code"]) == 8 and first["url"].endswith(f"/l/{first['code']}")
    assert first["doc_no"].endswith("-B01")
    issued = date.fromisoformat(first["issued_at"])
    assert date.fromisoformat(first["expires_at"]).toordinal() - issued.toordinal() == 90
    again = client.post(f"/api/sales/{pid}/111-11-11111/letter-link").json()
    assert again["code"] == first["code"] and again["doc_no"] == first["doc_no"]  # 유효한 동안 같은 링크
    other = client.post(f"/api/sales/{pid}/222-22-22222/letter-link").json()
    assert other["code"] != first["code"] and other["doc_no"].endswith("-N02")  # 그날 두 번째 링크
    assert client.post(f"/api/sales/{pid}/999-99-99999/letter-link").status_code == 404


def test_letter_page_is_public_and_shows_letter(client, monkeypatch):
    pid = _project(client)
    link = client.post(f"/api/sales/{pid}/111-11-11111/letter-link").json()
    monkeypatch.setenv("APP_LOGIN_PASSWORD", "1234")  # 로그인을 켜도 공문 화면은 열린다
    res = client.get(f"/l/{link['code']}")
    assert res.status_code == 200 and "text/html" in res.headers["content-type"]
    body = res.text
    for expected in (link["doc_no"], "농업회사법인 테스트종묘(주)", "URL 복사", "인쇄", "noindex", "✓ 충족 2"):
        assert expected in body, expected
    assert res.headers["cache-control"] == "no-store"
    # 다른 화면·API는 여전히 로그인 필요
    assert client.post(f"/api/sales/{pid}/111-11-11111/letter-link").status_code == 401
    assert client.get("/l/NoSuchCode1").status_code == 404


def test_expired_letter_link(client):
    pid = _project(client)
    link = client.post(f"/api/sales/{pid}/111-11-11111/letter-link").json()
    storage._run("UPDATE letter_links SET expires_at = %s WHERE code = %s", ("2000-01-01", link["code"]))
    res = client.get(f"/l/{link['code']}")
    assert res.status_code == 410 and "열람 기간이 지났습니다" in res.text
    renewed = client.post(f"/api/sales/{pid}/111-11-11111/letter-link").json()
    assert renewed["code"] != link["code"]  # 만료되면 새 링크(새 문서번호·시행일자)


def test_letter_links_removed_with_project_membership(client):
    pid = _project(client)
    link = client.post(f"/api/sales/{pid}/111-11-11111/letter-link").json()
    storage.remove_company_from_project(pid, "111-11-11111")
    assert storage.get_letter_link(link["code"]) is None
