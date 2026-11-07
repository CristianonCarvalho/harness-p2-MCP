"""Testes da escolha de versão pela data (spec, seção 6), com versões sintéticas."""

from datetime import date

import pytest

from taxlaw.versions import choose_version, status_at


def version(versao: str, desde: str | None, ate: str | None = None) -> dict:
    return {"versao": versao, "efeitos_desde": desde, "efeitos_ate": ate}


# Três redações em sequência, como CF.art156-A.par1.incIX no corpus real.
CHAIN = [
    version("EC132.art1", "2023-12-21", "2026-12-31"),
    version("EC132.art3", "2027-01-01", "2032-12-31"),
    version("EC132.art4", "2033-01-01"),
]


def versao_of(versions, when):
    choice = choose_version(versions, date.fromisoformat(when))
    return choice.chosen["versao"], choice.in_effect, [v["versao"] for v in choice.others]


def test_status_at_interval_edges_are_inclusive():
    v = version("EC132.art3", "2027-01-01", "2032-12-31")
    assert status_at(v, date(2027, 1, 1)) is True
    assert status_at(v, date(2032, 12, 31)) is True
    assert status_at(v, date(2026, 12, 31)) is False
    assert status_at(v, date(2033, 1, 1)) is False


def test_status_at_open_end_and_unknown_start():
    assert status_at(version("EC132.art4", "2033-01-01"), date(2099, 1, 1)) is True
    assert status_at(version("EC132.art9", None), date(2030, 1, 1)) is None


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("2025-06-01", "EC132.art1"),
        ("2026-12-31", "EC132.art1"),
        ("2027-01-01", "EC132.art3"),
        ("2032-12-31", "EC132.art3"),
        ("2033-01-01", "EC132.art4"),
        ("2099-01-01", "EC132.art4"),
    ],
)
def test_date_inside_one_interval_picks_that_version(when, expected):
    chosen, in_effect, others = versao_of(CHAIN, when)
    assert (chosen, in_effect) == (expected, True)
    assert expected not in others and len(others) == 2


def test_before_all_versions_returns_the_first_not_in_effect():
    assert versao_of(CHAIN, "2023-12-20") == ("EC132.art1", False, ["EC132.art3", "EC132.art4"])


def test_after_the_last_version_returns_the_last_not_in_effect():
    revoked = [version("EC132.art1", "2023-12-21", "2032-12-31")]
    assert versao_of(revoked, "2033-01-01") == ("EC132.art1", False, [])


def test_after_several_ended_versions_returns_the_last_one():
    ended = [version("EC132.art1", "2023-12-21", "2026-12-31"), version("EC132.art3", "2027-01-01", "2032-12-31")]
    assert versao_of(ended, "2040-01-01") == ("EC132.art3", False, ["EC132.art1"])


def test_gap_between_versions_returns_the_one_that_already_ended():
    gap = [version("EC132.art1", "2023-12-21", "2025-12-31"), version("EC132.art3", "2027-01-01")]
    assert versao_of(gap, "2026-06-01") == ("EC132.art1", False, ["EC132.art3"])


def test_unknown_start_is_null_never_false():
    assert versao_of([version("EC132.art9", None)], "2030-01-01") == ("EC132.art9", None, [])


def test_more_than_one_possible_returns_the_oldest_with_null():
    # Início conhecido + versão indeterminada: as duas são possíveis em 2030.
    versions = [version("EC132.art3", "2027-01-01"), version("EC132.art9", None)]
    assert versao_of(versions, "2030-01-01") == ("EC132.art3", None, ["EC132.art9"])


def test_overlapping_known_intervals_are_null_too():
    versions = [version("EC132.art1", "2023-12-21"), version("EC132.art3", "2027-01-01")]
    assert versao_of(versions, "2030-01-01") == ("EC132.art1", None, ["EC132.art3"])
    # Antes da segunda começar, só a primeira é possível: True.
    assert versao_of(versions, "2025-01-01") == ("EC132.art1", True, ["EC132.art3"])


def test_others_keep_corpus_order():
    assert versao_of(CHAIN, "2030-01-01")[2] == ["EC132.art1", "EC132.art4"]


def test_empty_versions_is_an_error():
    with pytest.raises(ValueError):
        choose_version([], date(2030, 1, 1))
