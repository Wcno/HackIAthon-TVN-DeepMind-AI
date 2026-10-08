from datetime import UTC, datetime

from whoami.pipeline.context import DEFAULT_RULES, ContextRule, link_context
from whoami.pipeline.evidence import indicator_evidence, inec_evidence, quake_evidence

NO_LINK = "Ningún indicador ni evento oficial del paquete mide este tema; no se fuerza un vínculo."
NO_QUAKE = "Ningún sismo del catálogo USGS coincide en fecha con la noticia."


def wb(country, indicator, year, value, unit="% anual"):
    return indicator_evidence(
        {"pais_iso3": country, "indicador_id": indicator, "anio": year, "valor": value, "unidad": unit, "fuente_url": "https://wb.test"}
    )


def inec(series_id, period, value, frequency="mensual", unit="% interanual"):
    return inec_evidence(
        {
            "serie_id": series_id,
            "serie": f"Serie {series_id}",
            "periodo": period,
            "frecuencia": frequency,
            "valor": value,
            "unidad": unit,
            "base": "2024=100",
            "fuente_url": "https://inec.test",
        }
    )


def quake(usgs_id, time, magnitude, place="Burica, Panama", epicenter=None):
    props = {"id": usgs_id, "magnitude": magnitude, "time": time, "status": "reviewed", "place": place, "url": "https://usgs.test"}
    if epicenter:
        props |= {"latitude": epicenter[0], "longitude": epicenter[1]}
    return quake_evidence(props)


OFFICIAL = {
    e.id_evidencia: e
    for e in [
        inec("ipc_var_interanual", "2026-07", "1.0"),
        inec("ipc_var_interanual", "2026-08", "1.2"),
        inec("ipc_var_interanual", "2026-09", ""),
        inec("pib_constante_var_interanual", "2026-T1", "5.0", "trimestral"),
        inec("pib_constante_var_interanual", "2026-T2", "6.4", "trimestral"),
        wb("PAN", "SL.UEM.TOTL.ZS", "2023", "6.5", "% de la fuerza laboral"),
        wb("PAN", "SL.UEM.TOTL.ZS", "2024", "8.4", "% de la fuerza laboral"),
        wb("PAN", "SL.UEM.TOTL.ZS", "2025", "", "% de la fuerza laboral"),
        wb("CRI", "SL.UEM.TOTL.ZS", "2024", "7.0", "% de la fuerza laboral"),
        wb("PAN", "NE.EXP.GNFS.ZS", "2024", "30.1", "% del PIB"),
        wb("PAN", "NY.GDP.MKTP.KD.ZG", "2024", "2.9"),
        quake("us1", "2026-10-03T08:00:00Z", 4.5),
        quake("us2", "2026-10-03T20:00:00Z", 5.6),
        quake("us3", "2026-09-20T08:00:00Z", 4.5),
    ]
}
DAY = datetime(2026, 10, 3, 9, tzinfo=UTC)


def link(text, topic="economia", date=DAY, official=OFFICIAL, rules=DEFAULT_RULES):
    return link_context(text, date, topic, official, rules)


def ids(links):
    return [x.id_evidencia for x in links]


def test_inflation_links_the_latest_non_null_inec_cpi_point():
    links, reason = link("Sube la inflación en los alimentos")

    assert ids(links) == ["INEC-ipc_var_interanual-2026-08"]
    assert reason is None
    assert links[0].pais == "PAN"
    assert links[0].limitaciones == "Dato mensual del INEC (2026-08, base 2024=100); puede revisarse."


def test_matching_ignores_accents_and_case():
    assert ids(link("EL COSTO DE LA VIDA SIGUE EN ALZA")[0]) == ["INEC-ipc_var_interanual-2026-08"]
    assert ids(link("El IPC de agosto")[0]) == ["INEC-ipc_var_interanual-2026-08"]


def test_keywords_match_whole_words_only():
    links, reason = link("Una típica pelea de recipiente")

    assert links == ()
    assert reason == NO_LINK


def test_unemployment_links_latest_panama_point_with_a_value_never_another_country():
    links, _ = link("Preocupa la tasa de desempleo")

    assert ids(links) == ["WB-PAN-SL.UEM.TOTL.ZS-2024"]
    assert links[0].limitaciones == "Serie anual del Banco Mundial (2024): describe ese año, no la situación de hoy."


def test_gdp_prefers_inec_and_falls_back_to_the_world_bank():
    links, _ = link("La economía creció en el segundo trimestre")
    assert ids(links) == ["INEC-pib_constante_var_interanual-2026-T2"]

    without_inec = {k: v for k, v in OFFICIAL.items() if not k.startswith("INEC-pib")}
    links, _ = link("Crecimiento económico de Panamá", official=without_inec)
    assert ids(links) == ["WB-PAN-NY.GDP.MKTP.KD.ZG-2024"]


def test_exports_link_the_world_bank_exports_series():
    assert ids(link("Caen las exportaciones de banano")[0]) == ["WB-PAN-NE.EXP.GNFS.ZS-2024"]


def test_an_ambiguous_keyword_is_narrowed_by_topic():
    links, reason = link("El PIB de la selección en la tabla", topic="sin_tema")

    assert links == ()
    assert reason == NO_LINK


def test_a_quake_links_the_closest_event_within_one_day():
    links, _ = link("Fuerte sismo sacude el sur del país")

    assert ids(links) == ["USGS-us1"]
    assert links[0].etiqueta == "Sismo M4,5"
    assert links[0].limitaciones == "El catálogo USGS confirma el sismo (hora, magnitud, lugar); no mide daños, pérdidas ni afectados."


def test_a_magnitude_in_the_text_must_match_within_three_tenths():
    links, _ = link("Sismo de magnitud 5,6 en Chiriquí")
    assert ids(links) == ["USGS-us2"]

    links, reason = link("Sismo de magnitud 7,1 en Chiriquí")
    assert links == ()
    assert reason == NO_QUAKE


def test_a_quake_without_an_event_that_day_is_not_forced():
    links, reason = link("Temblor sorprende a los vecinos", date=datetime(2026, 10, 10, tzinfo=UTC))

    assert links == ()
    assert reason == NO_QUAKE


def test_a_group_can_link_several_official_sources():
    links, _ = link("Sismo y alza de la inflación")

    assert sorted(ids(links)) == ["INEC-ipc_var_interanual-2026-08", "USGS-us1"]


def test_a_quake_that_finds_nothing_does_not_hide_other_links():
    links, reason = link("Sismo y alza de la inflación", date=datetime(2026, 10, 10, tzinfo=UTC))

    assert ids(links) == ["INEC-ipc_var_interanual-2026-08"]
    assert reason is None


def test_no_rule_fires_means_no_link_and_the_reason_says_so():
    links, reason = link("Estrenan una película en los cines", topic="sin_tema")

    assert links == ()
    assert reason == NO_LINK


def test_rules_are_pluggable():
    always = ContextRule(
        name="siempre",
        keywords=("cines",),
        topics=frozenset(),
        evidence=lambda official, text, date: OFFICIAL["WB-PAN-NE.EXP.GNFS.ZS-2024"],
        razon="Regla de prueba.",
    )

    links, _ = link("Estrenan una película en los cines", rules=[always])

    assert ids(links) == ["WB-PAN-NE.EXP.GNFS.ZS-2024"]
    assert "Regla de prueba." in links[0].razon


# ----------------------------------------------------------------------------------------------- quake location

CHOCO_QUAKE = quake("us-choco", "2026-10-03T07:00:00Z", 5.5, "15 km N of Acandi, Colombia", epicenter=(8.6, -77.3))
CHOCO_OFFICIAL = {CHOCO_QUAKE.id_evidencia: CHOCO_QUAKE}


def test_a_quake_in_colombia_is_not_linked_to_news_about_a_quake_in_colombia():
    links, reason = link("Fuerte terremoto sacude el Chocó, en Colombia", official=CHOCO_OFFICIAL)

    from whoami.pipeline.context import OTHER_COUNTRY_REASON

    assert links == ()
    assert reason == OTHER_COUNTRY_REASON


def test_news_naming_another_country_still_links_when_it_also_names_a_panamanian_province():
    links, _ = link("Sismo en Colombia se sintió en Darién", official=CHOCO_OFFICIAL)

    assert ids(links) == ["USGS-us-choco"]


def test_a_quake_whose_place_is_not_panama_links_when_the_epicenter_is_inside_the_panama_box():
    links, _ = link("Fuerte sismo sacude la frontera", official=CHOCO_OFFICIAL)

    assert ids(links) == ["USGS-us-choco"]


def test_a_quake_outside_panama_by_place_and_epicenter_is_never_linked():
    far = quake("us-far", "2026-10-03T07:00:00Z", 5.5, "10 km S of Quepos, Costa Rica", epicenter=(9.9, -84.2))

    links, reason = link("Fuerte sismo sacude el país", official={far.id_evidencia: far})

    assert links == ()
    assert reason == NO_QUAKE


def test_a_quake_without_epicenter_and_without_panama_in_its_place_is_not_linked():
    unknown = quake("us-unknown", "2026-10-03T07:00:00Z", 5.5, "Costa Rica region")

    links, _ = link("Fuerte sismo sacude el país", official={unknown.id_evidencia: unknown})

    assert links == ()


def test_the_country_check_ignores_accents_and_case():
    links, _ = link("TERREMOTO EN MÉXICO deja daños", official=OFFICIAL)

    assert links == ()


def test_naming_the_us_geological_survey_does_not_make_a_panamanian_quake_foreign():
    links, _ = link("Sismo sacude el país, informó el Servicio Geológico de Estados Unidos")

    assert ids(links) == ["USGS-us1"]


def test_gdp_phrasings_found_by_the_embedding_comparison_link_to_gdp():
    from whoami.pipeline.context import DEFAULT_RULES
    from whoami.pipeline.text import fold

    pib = next(rule for rule in DEFAULT_RULES if rule.name == "pib")
    for headline in (
        "Producto Interno Bruto de Panamá crece 6.4% en el segundo trimestre de 2026",
        "Economía panameña crece 8.49% en julio de 2026, según el INEC",
        "La economía panameña acelera: de 4.8% en el primer trimestre a 6.4% en el segundo",
    ):
        assert pib.matched_keyword(fold(headline), "economia") is not None, headline


def test_news_about_another_country_gets_no_panamanian_indicator():
    from datetime import UTC, datetime

    from whoami.pipeline.context import OTHER_COUNTRY_REASON, link_context

    links, reason = link_context(
        "EEUU reactiva segundo punto fronterizo para la exportación de ganado de México",
        datetime(2026, 9, 20, tzinfo=UTC),
        "economia",
        {},
    )
    assert links == () and reason == OTHER_COUNTRY_REASON
