# Source Coverage Draft

**Date:** 2026-10-07  
**Purpose:** first nationwide map of where public environmental information cards for the 16 RDOŚ can be collected.

This is a draft. It is not a complete catalogue of Polish public authorities.

Status values:

- **VERIFIED** — observed on a live public page in this project’s research
- **NOT FOUND** — looked for in the expected public place and not found
- **UNKNOWN** — not established; do not guess

SIOS facts come from [SIOS_RESEARCH.md](SIOS_RESEARCH.md) and later live SIOS verification.  
EkoKarty facts come from [EKOKARTY_RESEARCH.md](EKOKARTY_RESEARCH.md).

Important distinction, already verified for SIOS:

- `iid` = institution/tenant scope
- `id_provinces` = card geography, not publisher

Province SIOS searches can include RDOŚ, starostwa, Wody Polskie, municipalities, and other publishers. That is intended for province monitoring and is **not** the same as “this RDOŚ uses SIOS as its own register”.

---

## 16 RDOŚ

| Authority | Region | SIOS | EkoKarty | Own system | Full documents online | Notes |
|---|---|---|---|---|---|---|
| RDOŚ Białystok | podlaskie | VERIFIED as SIOS tenant `iid=1324`; also appears in nationwide/`id_provinces=10` searches | NOT FOUND | UNKNOWN | UNKNOWN | Institution heading matched. Public attachments only when a SIOS card already links them. |
| RDOŚ Bydgoszcz | kujawsko-pomorskie | VERIFIED as a publisher in `id_provinces=2` samples; institution-specific `iid` UNKNOWN | NOT FOUND | UNKNOWN | UNKNOWN | Official RDOŚ page linked generic SIOS `/search/common`, not an `iid`. |
| RDOŚ Gdańsk | pomorskie | VERIFIED as SIOS tenant `iid=1747` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Gorzów Wielkopolski | lubuskie | VERIFIED as SIOS tenant `iid=1682` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Katowice | śląskie | VERIFIED as SIOS tenant `iid=1226` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Kielce | świętokrzyskie | VERIFIED as SIOS tenant `iid=1398` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Kraków | małopolskie | VERIFIED as SIOS tenant `iid=1336` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Lublin | lubelskie | VERIFIED as SIOS tenant `iid=1428` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Łódź | łódzkie | VERIFIED as a publisher in `id_provinces=5` samples; institution-specific `iid` UNKNOWN | NOT FOUND | UNKNOWN | UNKNOWN | Official RDOŚ page linked generic SIOS. |
| RDOŚ Olsztyn | warmińsko-mazurskie | VERIFIED as SIOS tenant `iid=1278` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Opole | opolskie | VERIFIED as SIOS tenant `iid=1381` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Poznań | wielkopolskie | VERIFIED as SIOS tenant `iid=1761` | NOT FOUND | UNKNOWN | UNKNOWN | |
| RDOŚ Rzeszów | podkarpackie | VERIFIED as SIOS tenant `iid=1429` | NOT FOUND | UNKNOWN | UNKNOWN | Detail authority may include a department suffix. |
| RDOŚ Szczecin | zachodniopomorskie | VERIFIED as a publisher in `id_provinces=16` samples; institution-specific `iid` UNKNOWN | NOT FOUND | UNKNOWN | UNKNOWN | No public institution `iid` found. |
| RDOŚ Warszawa | mazowieckie | NOT FOUND in the 2026-10-07 overlap sample | VERIFIED `/wykaz/rdos-warszawa/` | UNKNOWN beyond EkoKarty | UNKNOWN | Four sampled Warszawa cards were absent from SIOS `nocard` and case-mark search. Mazowieckie SIOS + `Castor fiber` returned GDOŚ cards, not RDOŚ Warszawa. Some EkoKarty cards cite an external PDF URL; retrieval was not verified. |
| RDOŚ Wrocław | dolnośląskie | VERIFIED as a publisher in `id_provinces=1` samples (mixed with Starostwo Powiatowe w Kłodzku); institution-specific `iid` UNKNOWN | NOT FOUND | UNKNOWN | UNKNOWN | Province filter is not institution scope. |

---

## Current monitoring implication

Primary SIOS monitoring unit remains the **voivodeship** (`iid=0` + `id_provinces=1..16`), including multiple publishers.

EkoKarty is currently a **supplementary institution source for RDOŚ Warszawa only**. It must not replace `mazowieckie` SIOS province monitoring.

---

## Other EkoKarty authorities (non-exhaustive)

These public slugs were verified as live institution datasets. This is a discoverable sample, not a directory.

| Authority | Region | Slug | Notes |
|---|---|---|---|
| Urząd Gminy Przykładowo | n/a | `urzad-gminy-przykladowo` | Demo dataset linked from the homepage |
| Urząd Gminy w Chojnicach | pomorskie | `gmchojnice` | Current template labels match Warszawa; card numbers are not `N/YEAR` |
| Urząd Gminy Drużbice | łódzkie | `ug-druzbice` | |
| Urząd Gminy Gorzyce | podkarpackie | `uggorzyce` | |
| Urząd Gminy w Brzeszczach | małopolskie | `brzeszcze` | |
| Urząd Gminy Głowno | łódzkie | `ug-glowno` | |
| Urząd Miasta Zielona Góra | lubuskie | `zielonagora` | |
| Urząd Miasta Tychy | śląskie | `umtychy` | |
| Urząd Miasta Łaziska Górne | śląskie | `laziska` | |
| Urząd Miasta Limanowa | małopolskie | `miastoLimanowa` | |
| Urząd Miasta Kolno | podlaskie | `umkolno` | |
| Urząd Miejski w Szczebrzeszynie | lubelskie | `umszczebrzeszyn` | |
| Urząd Miejski w Pińczowie | świętokrzyskie | `ochrona_srodowiska` | Slug is not a city name |
| Starostwo Powiatowe w Białymstoku | podlaskie | `sp-bialystok` | |
| Starostwo Powiatowe w Oleśnie | opolskie | `sp-olesno` | |
| Starostwo Powiatowe w Międzychodzie | wielkopolskie | `spmiedzychod` | |
| Starostwo Powiatowe w Gorlicach | małopolskie | `sp-gorlice` | |
| Starostwo Powiatowe w Ropczycach | podkarpackie | `spropczyce` | |
| Starostwo Powiatowe w Lubinie | dolnośląskie | `sp-lubin` | |
| Urząd Marszałkowski Województwa Łódzkiego | łódzkie | `lodzkie` | Archive route verified |
| WIOŚ Kielce | świętokrzyskie | `wios-kielce` | Archive route verified |

Card counts, institution numeric IDs, and year bounds are **UNKNOWN** unless a dataset is inspected individually.

---

## Open coverage questions

1. Do any remaining RDOŚ use EkoKarty under an unexpected slug?
2. Does RDOŚ Warszawa publish anything into SIOS under a name that the overlap sample missed?
3. Which municipalities/counties in beaver-relevant areas use EkoKarty vs SIOS vs a local BIP page?
4. Is `wykaz.ekoportal.pl` still an active alternative, as claimed on the EkoKarty homepage?
5. Where are full source documents actually published, if they are published at all?
