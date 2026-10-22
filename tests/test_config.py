from src.sios.config import load_sources


EXPECTED_PROVINCES = {
    "dolnoslaskie": ("dolnośląskie", 1),
    "kujawsko_pomorskie": ("kujawsko-pomorskie", 2),
    "lubelskie": ("lubelskie", 3),
    "lubuskie": ("lubuskie", 4),
    "lodzkie": ("łódzkie", 5),
    "malopolskie": ("małopolskie", 6),
    "mazowieckie": ("mazowieckie", 7),
    "opolskie": ("opolskie", 8),
    "podkarpackie": ("podkarpackie", 9),
    "podlaskie": ("podlaskie", 10),
    "pomorskie": ("pomorskie", 11),
    "slaskie": ("śląskie", 12),
    "swietokrzyskie": ("świętokrzyskie", 13),
    "warminsko_mazurskie": ("warmińsko-mazurskie", 14),
    "wielkopolskie": ("wielkopolskie", 15),
    "zachodniopomorskie": ("zachodniopomorskie", 16),
}


def test_registry_loads_all_sixteen_province_sources() -> None:
    sources = load_sources()

    assert set(sources) == set(EXPECTED_PROVINCES)
    assert len(sources) == 16
    for key, (name, province_id) in EXPECTED_PROVINCES.items():
        source = sources[key]
        assert source.name == name
        assert source.adapter == "sios"
        assert source.scope == "province"
        assert source.enabled is True
        assert source.params == {"iid": 0, "id_provinces": province_id}


def test_province_registry_does_not_require_institution_iids() -> None:
    sources = load_sources()

    assert all(source.params["iid"] == 0 for source in sources.values())
    assert {source.params["id_provinces"] for source in sources.values()} == set(
        range(1, 17)
    )
