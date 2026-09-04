"""app.agent.guard is the deterministic backstop that redacts anything
implementation-shaped from the agent's final answer text, regardless of
whether the system prompt was actually followed -- these tests exercise the
scrubber directly rather than a live LLM, which is what makes "the agent
response never contains a UUID" an actually-enforceable, testable claim."""
from app.agent.guard import find_leaks, scrub


def test_uuid_is_redacted():
    text = "The batch id is 145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d and it closed fine."
    assert "145d4d3c" not in scrub(text)
    assert "[internal reference removed]" in scrub(text)


def test_windows_path_is_redacted():
    text = r"Files were read from C:\Users\ops\data\inbound\mrdn\hdfc\statement.csv today."
    result = scrub(text)
    assert "C:\\Users" not in result
    assert "statement.csv" not in result


def test_posix_path_is_redacted():
    text = "Scanning /data/inbound/shyd/disbursal for new files."
    result = scrub(text)
    assert "/data/inbound" not in result


def test_function_call_syntax_is_redacted():
    text = "Evidence: get_batch_report(batch_id=145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d)."
    result = scrub(text)
    assert "get_batch_report(" not in result
    assert "145d4d3c" not in result


def test_raw_json_blob_is_redacted():
    text = 'Result: {"batch_id": "145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d", "status": "CLOSED"} was returned.'
    result = scrub(text)
    assert '"batch_id"' not in result
    assert "145d4d3c" not in result


def test_sha256_hash_is_redacted():
    text = "checksum 2f320a21f3a0e5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f9001122334 was recorded."
    result = scrub(text)
    assert "2f320a21f3a0" not in result


def test_id_field_reference_is_redacted_even_without_full_uuid_shape():
    text = "See exception_id=exc-4471 for the detail."
    result = scrub(text)
    assert "exc-4471" not in result


def test_legitimate_business_content_survives_untouched():
    text = (
        "SHYD — Latest Reconciliation\n\n"
        "Batch: Payments and Aggregator Settlement, Status: Closed, Records: 32\n\n"
        "32 transactions processed, 100% associated with reconciliation groups, "
        "11 exact reference matches, 1 open exception worth Rs 150.00.\n"
        "Completed: 04 Sep 2026, 08:25:43 PM IST"
    )
    assert scrub(text) == text


def test_find_leaks_reports_category_and_matched_text():
    leaks = find_leaks("id: 145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d")
    assert any(leak.category == "uuid" for leak in leaks)


def test_scrub_collapses_adjacent_redactions_instead_of_repeating_the_marker():
    text = "batch_id=145d4d3c-2a41-4e9a-9c11-8b1f9a7e2b0d client_id=99999999-9999-9999-9999-999999999999"
    result = scrub(text)
    assert result.count("[internal reference removed]") <= 2
