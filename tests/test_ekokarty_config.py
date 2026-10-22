from src.ekokarty.config import load_ekokarty_keywords, load_institutions, load_settings


def test_only_rdos_warszawa_is_enabled() -> None:
    institutions = load_institutions()
    assert set(institutions) == {"rdos-warszawa"}
    source = institutions["rdos-warszawa"]
    assert source.enabled is True
    assert source.slug == "rdos-warszawa"
    assert source.name == "Regionalna Dyrekcja Ochrony Środowiska w Warszawie"


def test_ekokarty_keywords_are_source_specific() -> None:
    groups = load_ekokarty_keywords()
    assert groups["species"] == [
        "bóbr",
        "bobry",
        "Castor fiber",
        "bobra europejskiego",
    ]
    assert "tama" in groups["interventions"]
    assert "tamy" in groups["interventions"]
    assert "żeremie" in groups["interventions"]
    assert "odstrzał" in groups["interventions"]
    assert "tama bobrowa" not in groups["interventions"]


def test_result_cap_defaults_to_verified_limit() -> None:
    settings = load_settings()
    assert settings.result_cap == 2000
    assert settings.base_url == "https://ekokarty.pl"
