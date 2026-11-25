"""Exercise lookup evidence, decisions and stale-reference recovery in Chromium."""

from pathlib import Path

import pytest
from playwright.sync_api import Page, Response, expect

from test.helpers_business_validation_workflow import write_synthetic_pdf
from test.helpers_lookup_visual import VIEWPORTS, capture_lookup, lookup_browser, lookup_config
from test.integration.test_lookup_review import VALUES, _pause, _publish_review


def _revalidate(page: Page) -> Response:
    with page.expect_response(lambda response: response.url.endswith("/revalidate")) as checked:
        page.get_by_role("button", name="Revalidate", exact=True).click()
    assert checked.value.status == 200, checked.value.json()
    return checked.value


@pytest.mark.parametrize(("viewport", "width", "height"), VIEWPORTS, ids=["desktop", "mobile"])
def test_lookup_review_evidence_resolution_and_completion(tmp_path: Path, viewport: str, width: int, height: int) -> None:
    config = lookup_config(tmp_path)
    long_supplier = "SyntheticSupplier" * 8
    register = (f"Tax,Name,Code\n00123,{long_supplier},00041\n00123,{long_supplier.upper()},00042\n"
                "00999,Acme,00055\n" + "00444,Acme,SYNTHETIC\n" * 51)
    schema = {
        "fields": {"tax": {"type": "string"}, "supplier_id": {"type": "string"},
                   "approval_code": {"type": "string", "label": "Approval code"}},
        "business_validation": {"format_version": 1, "rules": [
            {"id": "supplier_approval", "validator": "required_if:v1", "when": "/supplier_id",
             "equals": "00042", "required": ["/approval_code"], "severity": "blocking"},
        ]},
    }
    version = _publish_review(config, tmp_path, register=register, multiple=True, always_review=True, schema=schema)
    reviews: dict[str, str] = {}
    for name, values in {
        "unique": {**VALUES, "tax": "00999"},
        "ambiguous": {**VALUES, "supplier": long_supplier},
        "truncated": {**VALUES, "tax": "00444"},
        "corrected": {**VALUES, "tax": "wrong"},
    }.items():
        source = tmp_path / "uploads" / name / "synthetic-invoice.pdf"
        write_synthetic_pdf(source, ["SYNTHETIC INVOICE - TEST DATA ONLY", f"Tax ID: {values['tax'] if name != 'corrected' else '00999'}",
                                     "Supplier:", *[values['supplier'][i:i + 55] for i in range(0, len(values['supplier']), 55)]])
        _, reviews[name] = _pause(config, source.parent, version, values, source=source)

    with lookup_browser(tmp_path, width, height, admin=False) as (page, base):
        panel = page.locator("#review-lookup-panel")
        lookup = panel.get_by_role("article").first
        optional = panel.get_by_role("article").nth(1)
        complete = page.get_by_role("button", name="Complete Review", exact=True)
        status = page.locator("#review-lookup-status")

        def open_review(name: str, *, claim: bool = False) -> None:
            page.goto(f"{base}/app/review/{reviews[name]}")
            expect(panel.get_by_role("heading", name="CSV reference lookups")).to_be_visible()
            expect(page.locator("#review-pdf-body canvas")).to_be_visible()
            if claim:
                page.locator("#review-claim-button").click()
                expect(page.get_by_role("button", name="Revalidate", exact=True)).to_be_enabled()

        def submit_action(card_name: str, button: str, reason: str) -> None:
            card = lookup if card_name == "lookup" else optional
            card.get_by_role("textbox", name="Reason").fill(reason)
            with page.expect_response(lambda response: response.url.endswith("/revalidate")) as checked:
                card.get_by_role("button", name=button, exact=True).click()
            assert checked.value.status == 200, checked.value.json()

        def accept() -> None:
            with page.expect_response(lambda response: response.url.endswith("/complete")) as accepted:
                complete.click()
            assert accepted.value.status == 200, accepted.value.json()
            payload = accepted.value.request.post_data_json
            assert payload is not None and payload["lookup_preview_token"]
            page.wait_for_url("**/app/review")

        open_review("unique")
        expect(lookup).to_contain_text("Unique match")
        expect(lookup).to_contain_text("00055")
        expect(lookup.get_by_role("button", name="Use selected record")).to_have_count(0)

        open_review("truncated", claim=True)
        notice = lookup.get_by_text("Showing 50 of 51 matches", exact=False)
        expect(notice).to_be_visible()
        expect(lookup.get_by_role("radio")).to_have_count(0)
        candidates = lookup.get_by_role("region", name="Records for lookup")
        assert candidates.evaluate("element => element.scrollHeight > element.clientHeight")
        candidates.focus()
        candidates.press("PageDown")
        expect(candidates).to_be_focused()
        expect(complete).to_be_disabled()
        notice.scroll_into_view_if_needed()
        capture_lookup(page, f"review-truncated-{viewport}")

        open_review("ambiguous", claim=True)
        expect(lookup).to_contain_text("Multiple matches")
        expect(lookup).to_contain_text("Case-sensitive text")
        expect(lookup).to_contain_text("Case-insensitive text")
        first = lookup.get_by_role("radio", name="Record 1", exact=True)
        second = lookup.get_by_role("radio", name="Record 2", exact=True)
        first.focus()
        first.press("Space")
        first.press("ArrowDown")
        expect(second).to_be_focused()
        expect(second).to_be_checked()
        second.scroll_into_view_if_needed()
        capture_lookup(page, f"review-ambiguous-{viewport}")
        submit_action("lookup", "Use selected record", "Matched the supplier record on the synthetic invoice")
        expect(lookup).to_contain_text("00042")
        expect(complete).to_be_disabled()
        tax = page.locator('input[data-field-path="tax"]')
        tax.fill("bad input")
        expect(lookup).to_contain_text("Match inputs changed")
        expect(lookup).not_to_contain_text("00042")
        tax.fill("00123")
        _revalidate(page)
        expect(second).not_to_be_checked()
        second.check()
        submit_action("lookup", "Use selected record", "Verified synthetic record 2")
        submit_action("optional", "Skip lookup", "Optional billing reference has no match")
        expect(optional).to_contain_text("Skipped")
        expect(complete).to_be_enabled()
        check_summary = page.locator("#review-validation-summary")
        expect(check_summary).to_contain_text("1 failed")
        expect(lookup.locator('[data-validation-path="/supplier_id"]')).to_contain_text("supplier_approval")
        page.locator("#review-validation-details summary").click()
        page.get_by_role("button", name="Go to Approval code").click()
        approval = page.locator('input[data-field-path="approval_code"]')
        expect(approval).to_be_focused()
        approval.fill("APPROVED-SYNTHETIC")
        _revalidate(page)
        expect(check_summary).to_contain_text("1 passed")
        accept()
        open_review("ambiguous")
        expect(status).to_have_text("Accepted lookup evidence")
        expect(lookup).to_contain_text("00042")
        expect(optional).to_contain_text("Optional billing reference has no match")

        open_review("corrected", claim=True)
        expect(lookup).to_contain_text("No match")
        tax.fill("00999")
        _revalidate(page)
        expect(lookup).to_contain_text("00055")
        with page.expect_response(lambda response: response.url.endswith("/draft")):
            page.locator("#review-save-button").click()
        page.reload()
        expect(tax).to_have_value("00999")
        expect(lookup).to_contain_text("00055")
        (tmp_path / "register.csv").write_text("Tax,Name,Code\n00999,Acme,00056\n", encoding="utf-8")
        _revalidate(page)
        expect(lookup).to_contain_text("The CSV changed")
        expect(complete).to_be_disabled()
        adoption = lookup.get_by_role("button", name="Use current reference file")
        adoption.scroll_into_view_if_needed()
        capture_lookup(page, f"review-adoption-{viewport}")
        submit_action("lookup", "Use current reference file", "Approved replacement synthetic register")
        expect(lookup).to_contain_text("00056")
        submit_action("optional", "Skip lookup", "No optional billing match")
        expect(complete).to_be_enabled()
        (tmp_path / "register.csv").write_text("Tax,Name,Code\n00999,Acme,00057\n", encoding="utf-8")
        with page.expect_response(lambda response: response.url.endswith("/complete")) as stale:
            complete.click()
        assert stale.value.status == 409
        expect(status).to_be_focused()
        expect(status).to_contain_text("Lookup evidence changed")
        expect(complete).to_be_disabled()
        _revalidate(page)
        expect(lookup).to_contain_text("00057")
        accept()
        open_review("corrected")
        expect(status).to_have_text("Accepted lookup evidence")
        expect(lookup).to_contain_text("Returned text · Read-only")
        expect(lookup).to_contain_text("00057")
        expect(lookup).to_contain_text("Approved replacement synthetic register")
        expect(page.locator('[data-field-path="supplier_id"]')).to_have_count(0)
        expect(panel.get_by_role("textbox")).to_have_count(0)
        expect(page.get_by_role("button", name="Revalidate", exact=True)).to_be_hidden()
        lookup.get_by_role("heading", name="Returned text · Read-only").scroll_into_view_if_needed()
        capture_lookup(page, f"review-accepted-{viewport}")
