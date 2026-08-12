from unittest.mock import Mock, patch

from rdagent.scenarios.qlib.factor_experiment_loader import pdf_loader


def _mock_factor_session(responses):
    session = Mock()
    session.build_chat_completion.side_effect = responses
    backend = Mock()
    backend.return_value.build_chat_session.return_value = session
    return backend, session


def test_factor_extraction_keeps_factors_when_follow_up_returns_empty_object():
    backend, session = _mock_factor_session(
        [
            '{"factors": {"Alpha1": "first factor"}}',
            "{}",
        ]
    )

    with patch.object(pdf_loader, "APIBackend", backend):
        result = pdf_loader.__extract_factors_name_and_desc_from_content("report content")

    assert result == {"Alpha1": "first factor"}
    assert session.build_chat_completion.call_count == 2


def test_factor_extraction_keeps_factors_when_follow_up_omits_factors_field():
    backend, session = _mock_factor_session(
        [
            '{"factors": {"Alpha1": "first factor"}}',
            '{"summary": "no additional factors"}',
        ]
    )

    with patch.object(pdf_loader, "APIBackend", backend):
        result = pdf_loader.__extract_factors_name_and_desc_from_content("report content")

    assert result == {"Alpha1": "first factor"}
    assert session.build_chat_completion.call_count == 2


def test_factor_extraction_keeps_factors_when_follow_up_returns_invalid_json():
    backend, session = _mock_factor_session(
        [
            '{"factors": {"Alpha1": "first factor"}}',
            "not-json",
        ]
    )

    with patch.object(pdf_loader, "APIBackend", backend):
        result = pdf_loader.__extract_factors_name_and_desc_from_content("report content")

    assert result == {"Alpha1": "first factor"}
    assert session.build_chat_completion.call_count == 2
