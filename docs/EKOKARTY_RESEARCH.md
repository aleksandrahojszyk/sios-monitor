# EkoKarty Technical Research

**Source:** public pages at [https://ekokarty.pl/](https://ekokarty.pl/)  
**Investigation date:** 2026-10-07  
**Primary dataset used for search/detail tests:** [https://ekokarty.pl/wykaz/rdos-warszawa/](https://ekokarty.pl/wykaz/rdos-warszawa/)  
**Scope:** public HTML only. No login, no CAPTCHA solving, no bulk crawl, no document downloads.

Evidence is from:

- Direct `httpx` GET/POST requests without a session cookie
- Browser inspection of the public RDOŚ Warszawa listing
- Small public web-index lookups used only to discover institution slugs
- Comparison searches against public SIOS (`https://system.sios.pl/search/common`)

Status labels used below:

- **VERIFIED FACT** — observed on a live public response
- **ASSUMPTION** — reasonable interpretation, not proven
- **OPEN QUESTION** — not established by this sample

---

## Executive Summary

EkoKarty is **not a nationwide search index**. It is a vendor-hosted publication platform (Arisco / EDOŚ) that serves **separate institution datasets** at:

```
https://ekokarty.pl/wykaz/{institution-slug}/
```

The homepage is a marketing page. It does not expose a cross-institution search. There is no public institution directory, sitemap, or `robots.txt`.

For RDOŚ Warszawa, public search is a **server-rendered HTML POST**. The response embeds matching rows in one HTML table. DataTables then paginates those rows in the browser. Direct HTTP is sufficient; Playwright is not required for public listing or detail pages.

A hard **2,000-row HTML cap** was observed on both filtered and unfiltered Warszawa POSTs. Uncapped totals are therefore not available from a single request.

Among the 16 RDOŚ, **only Warszawa was verified on EkoKarty**. Other RDOŚ routes were **NOT FOUND**. Municipalities, counties, one marshal office, and one WIOŚ do appear under other slugs, so the platform is broader than RDOŚ Warszawa, but it is not a complete national RDOŚ register.

A small SIOS overlap sample found **no equivalent RDOŚ Warszawa cards** in SIOS. Current evidence supports treating EkoKarty as a **complementary source for RDOŚ Warszawa**, not as a duplicate of SIOS and not as a replacement for mazowieckie SIOS province monitoring.

**Adapter recommendation:** **GO**, but only for a bounded first adapter scoped to known institution slugs, starting with `rdos-warszawa`. **NO-GO** for a nationwide EkoKarty crawl or for replacing SIOS.

---

## Site Architecture

**VERIFIED FACT.** Users do not go from a national result list to a card. The observed path is:

1. Institution URL, usually linked from that authority’s own BIP/website, not from the EkoKarty homepage.
2. Institution listing/search at `/wykaz/{slug}/`.
3. Row click uses `tr[data-href]` to open a detail page.
4. Optional archive at `/wykaz/{slug}/archiwum/` for pre-16 November 2010 card types.

Homepage links:

- Vendor/product pages for EDOŚ on `arisco.pl`
- Demo dataset: [https://ekokarty.pl/wykaz/urzad-gminy-przykladowo/](https://ekokarty.pl/wykaz/urzad-gminy-przykladowo/)

These URLs returned the vendor 404 HTML page titled “Nie ma takiej strony”:

- `https://ekokarty.pl/robots.txt`
- `https://ekokarty.pl/sitemap.xml`
- `https://ekokarty.pl/wykaz/`

**VERIFIED FACT.** Architecture is **a platform hosting separate institution datasets**, not one nationwide database and not an index over all authorities.

**OPEN QUESTION.** Complete public inventory of slugs. No machine-readable registry was found.

---

## Search Architecture

**VERIFIED FACT** for RDOŚ Warszawa:

- Listing/search form: `<form method="post" action="https://ekokarty.pl/wykaz/rdos-warszawa/">`
- Encoding: `application/x-www-form-urlencoded`
- Hidden field `szukajRodzaj=NEW` on the current register
- Archive uses `szukajRodzaj=OLD`
- Result table `#tableKarty` is initialised with DataTables `pageLength: 10`
- Row navigation: `$('#tableKarty').on('click', 'tbody tr', ... window.location.href = data-href)`

A GET of the same URL with `?karty_all=bobry` returned the empty search form and **0 result rows**. Search is POST, not GET.

No JSON, GraphQL, or result-list XHR was observed. Browser performance entries after a live search were static assets plus a full navigation.

---

## Network Requests

### 1. Institution listing / search

- **URL:** `https://ekokarty.pl/wykaz/rdos-warszawa/`
- **Method:** `POST`
- **Body:** form fields below
- **Required headers:** none beyond a normal POST. A clear User-Agent was sent.
- **Cookies / session:** none observed; requests succeeded with an empty cookie jar
- **Response:** `200`, `text/html; charset=UTF-8`
- **Server:** `Apache/2.4.66 (Debian)`, `X-Powered-By: PHP/8.1.34`
- **CAPTCHA / CSRF:** none observed

Example:

```http
POST /wykaz/rdos-warszawa/ HTTP/1.1
Host: ekokarty.pl
Content-Type: application/x-www-form-urlencoded

szukajRodzaj=NEW&karty_all=b%C3%B3br&karty_numer=&sprawy_znak=&rok_dokumentu=&rodzaj_dokumentu=&karty_nazwa=&temat_dokumentu=&karty_miejsce_wyd=&karty_wyt_name=&karty_zat_name=&data_od=&data_do=
```

### 2. Card detail

- **URL pattern:** `/wykaz/{slug}/{cardId}/{secondaryId}/{type}`
- **Example:** `GET /wykaz/rdos-warszawa/77888/11843/X`
- **Method:** `GET`
- **Status:** `200`
- **Response:** HTML page, not a fragment-only Fancybox payload
- **Session:** not required

A legacy indexed URL still resolves to the Warszawa listing, not a card:

`https://ekokarty.pl/wykaz/rdos-warszawa/index.php?id=56170&id_inst=154&rob=szczegoly&rodzaj=X`

**OPEN QUESTION.** Whether those old `id` / `id_inst` query parameters still identify cards if posted rather than fetched as GET.

### 3. Archive

- **URL:** `https://ekokarty.pl/wykaz/rdos-warszawa/archiwum/`
- **Method:** `GET` for the form; search is `POST` with `szukajRodzaj=OLD`

---

## Search Parameters

Observed on the RDOŚ Warszawa current form.

| UI label | HTML `name` | Type | Notes |
|---|---|---|---|
| *(hidden)* | `szukajRodzaj` | hidden | `NEW` current register; `OLD` archive |
| Szukaj w całym dokumencie | `karty_all` | text | Primary keyword box |
| Numer karty | `karty_numer` | text | Not separately counted in this sample |
| Znak sprawy | `sprawy_znak` | text | Not separately counted in this sample |
| Rok wydania dokumentu | `rok_dokumentu` | select | `-1` = all; years `2010`–`2026` |
| Rodzaj dokumentu | `rodzaj_dokumentu` | select | `-1` = all; values `32`–`54` |
| Nazwa dokumentu | `karty_nazwa` | text | |
| Temat dokumentu | `temat_dokumentu` | select | `-1` = all; `7` = ochrona zwierząt oraz roślin |
| Obszar, którego dokument dotyczy | `karty_miejsce_wyd` | text | Free-text geography, not SIOS `id_provinces` |
| Dokument wytworzył | `karty_wyt_name` | text | |
| Dokument zatwierdził | `karty_zat_name` | text | |
| Zakres czasowy Od/do | `data_od`, `data_do` | text | **VERIFIED** to filter listing `Data karty` |

`rodzaj_dokumentu` values are **not** the SIOS `id_doctype` integers. Warszawa current values start at `32` = wnioski o wydanie decyzji, `35` = decyzje.

`temat_dokumentu` values are sequential `1`–`8`, **not** SIOS topic bit flags.

---

## Search Behaviour

All counts below are **RDOŚ Warszawa only**, `szukajRodzaj=NEW`, `karty_all=<term>`, no other filters, 2026-10-07.

| Query | Rows returned | Unique first-segment IDs | First card | Listing date range | Notes |
|---|---:|---:|---|---|---|
| `bóbr` | **2000** | 2000 | `4365/2026` | 2026-10-06 … 2018-12-04 | Cap hit |
| `bobry` | **23** | 23 | `3831/2025` | 2025-10-16 … 2015-05-14 | Complete for this term |
| `Castor fiber` | **2000** | 2000 | `4365/2026` | 2026-10-06 … 2014-03-18 | Cap hit |
| `bobra europejskiego` | **2000** | 2000 | `4365/2026` | 2026-10-06 … 2017-01-24 | Cap hit |
| `zwierząt chronionych` | **15** | 15 | `952/2026` | 2026-03-03 … 2018-05-30 | Complete for this term |
| `gatunków chronionych` | **169** | 169 | `662/2026` | 2026-02-13 … 2012-09-27 | Complete for this term |
| `odstrzał` | **148** | 148 | `3092/2025` | 2025-08-13 … 2012-02-01 | Complete for this term |
| `tama` | **21** | 21 | `1793/2026` | 2026-04-27 … 2011-10-07 | Complete for this term |

An unfiltered POST (`szukajRodzaj=NEW` only) also returned **exactly 2000 rows**. The 2000 figure is a **response cap**, not a verified dataset size.

### Matching semantics

**VERIFIED FACT.**

- Case-insensitive: `bóbr` ≡ `BÓBR`; `bobry` ≡ `BOBRY`; `Castor fiber` ≡ `castor fiber` (same ordered URLs).
- Diacritic-insensitive for this pair: `bóbr` ≡ `bobr` (same ordered URLs, both capped at 2000).
- Not stemming / not a synonym thesaurus: `bobry` returned 23 rows while `bóbr` overflowed 2000.
- Multi-word queries return large sets; this sample does **not** prove AND vs OR because the large queries were truncated.

Visible-row substring check:

- `bobry`: 23/23 listing rows contained the term
- `gatunków chronionych`: 169/169 listing rows contained the term
- `tama`: 19/21 listing rows contained the visible term; 2 matches lived in non-visible metadata or a morphological variant

**ASSUMPTION.** `karty_all` is a broad full-text / substring search over card fields, not an exact title match.

### Volunteer report: `Castor fiber` vs Polish variants

The volunteer report that `Castor fiber` is more reliable than generic Polish variants is **not verified as a completeness rule**.

What this sample shows:

- `Castor fiber` is useful and currently hits the 2000 cap.
- `bóbr` also hits the 2000 cap.
- In the two capped 2000-row windows, overlap was only **1355** URLs (`bóbr` only 645, `Castor fiber` only 645).
- `bobry` is much smaller (23) and is **not** a substitute for either query.

**ASSUMPTION.** A union of several queries, plus date windows to defeat the 2000 cap, is required. One keyword is not exhaustive.

---

## Institution Coverage

**VERIFIED FACT.** EkoKarty is relevant beyond RDOŚ Warszawa, but it is **not** a complete 16-RDOŚ source.

| Authority type | Status in this research |
|---|---|
| RDOŚ Warszawa | **VERIFIED** at `/wykaz/rdos-warszawa/` |
| Other 15 RDOŚ | **NOT FOUND** at conventional slugs and exact-name web lookup |
| Municipalities | **VERIFIED** sample exists |
| Counties / starostwa | **VERIFIED** sample exists |
| Marshal offices | **VERIFIED** at least Łódzkie |
| WIOŚ | **VERIFIED** at least Kielce |
| Demo gmina | **VERIFIED** `urzad-gminy-przykladowo` |

RDOŚ Warszawa exposed year-filter options **2010–2026**. That is a filter range, not proof that every year contains beaver-related cards. No public card-count field was found.

The second URL segment and old `id_inst` query values **vary by card** and must not be treated as the institution ID. The stable institution key on the public web is the **slug**.

See [SOURCE_COVERAGE_DRAFT.md](SOURCE_COVERAGE_DRAFT.md) for the 16-RDOŚ table.

---

## Pagination

This is **not** the SIOS `page=` model.

**VERIFIED FACT.**

| Behaviour | Observation |
|---|---|
| Default visible page size | DataTables `10` |
| Client page-size options | `10`, `25`, `50`, `100` |
| Server page parameter | **None** |
| Rows in one POST response | all matches, until cap |
| Cap | **2000 rows** |
| Overflow after last client page | not applicable; all rows are already in the DOM |
| SIOS-style repeated last page | **not observed**, because there is no server page walk |
| Listing sort | mostly newest `Data karty` first; **not strictly monotonic** (1 date inversion in a 2000-row `Castor fiber` window; 6 first-segment ID increases) |

`data_od` / `data_do` is a usable server-side window. Example: `Castor fiber` + `2026-10-01`–`2026-10-07` returned **10** rows, all inside that range.

### Safe termination conditions

For one POST:

1. Parse every `#tableKarty` body row in the HTML.
2. If `0` rows → empty result.
3. If `1..1999` rows → treat the response as complete for that filter.
4. If **exactly 2000** rows → **truncated**. Do not assume the dataset ended. Split the query, preferably by `data_od` / `data_do`.

Do not paginate with invented `page=` parameters.

---

## Search Result Schema

Source: RDOŚ Warszawa `#tableKarty` rows.

| Column | Example | Notes |
|---|---|---|
| Lp. | `1` | Position in this response |
| Numer karty | `4365/2026` | Institution-year number, not a global key |
| Rok wydania | `2026` | |
| Rodzaj dokumentu | `decyzje` | Label text |
| Nazwa dokumentu | `Decyzja zezwalająca…` | |
| Temat dokumentu | `ochrona zwierząt oraz roślin` | |
| Zakres przedmiotowy | truncated/full description | Keyword often matches here |
| Data karty | `2026-10-06` | Listing date; matched `Data zamieszczenie w wykazie` on sampled details |
| `data-href` | `/wykaz/rdos-warszawa/77888/11843/X` | Detail route |

Authority is **not** a listing column. It is implied by the institution dataset and restated on the detail page.

---

## Card Detail Schema

Sampled RDOŚ Warszawa cards from 2015, 2024, 2025 and 2026 used the same numbered labels. A Chojnice municipality card used the **same 18 labels**.

Original labels:

| # | Original label | Example / notes |
|---|---|---|
| 1 | Numer karty/rok | `4365/2026`. Chojnice sample used `RŚiGN.6220/X/29/14` |
| 2 | Rodzaj dokumentu | `decyzje` / `wnioski o wydanie decyzji` |
| 3 | Temat dokumentu | `ochrona zwierząt oraz roślin` or `inne` |
| 4 | Nazwa dokumentu | |
| 5 | Zakres przedmiotowy dokumentu - opis dokumentu | Full description |
| 6 | Obszar, którego dokument dotyczy, zgodnie z podziałem administracyjnym kraju | Free text: locality, gmina, or `woj. mazowieckie`. **Not** a reliable woj/powiat/gmina triple |
| 7 | Znak sprawy | `WPN-I.6401.389.2026.AJC` |
| 8 | Dokument wytworzył | Decision: RDOŚ; application: applicant, including `Osoba prywatna` |
| 9 | Data dokumentu | Document date |
| 10 | Dokument zatwierdził | |
| 11 | Data zatwierdzenia dokumentu | |
| 12 | Miejsce przechowywania dokumentu | Holding office / address |
| 13 | Adres elektroniczny zawierający odnośnik do dokumentu | `nie dotyczy` or an external URL |
| 14 | Czy dokument jest ostateczny tak/nie | `TAK` / `NIE` |
| 15 | Numery kart innych dokumentów w sprawie | Related card numbers, hyperlinked |
| 16 | Data zamieszczenie w wykazie danych o dokumencie | Listing/publication date. Label is missing a final *a* |
| 17 | Zastrzeżenia dotyczące nieudostępniania informacji | often empty |
| 18 | Uwagi | often `nie dotyczy` |

Additional version table, original headers:

| Numer | Nazwa dokumentu | Osoba publikująca | Data utworzenia | Data modyfikacji | Data publikacji | Status | Wersja | Akcja |
|---|---|---|---|---|---|---|---|---|

`PODGLĄD` in that table pointed back to the same public card URL, not to a source PDF.

SIOS-style fields **not seen** on these EkoKarty details:

- `Data wpływu dokumentu`
- `Data wprowadzenia`
- `Nazwa organu` as a separate label
- structured Województwo / Powiat / Gmina rows
- SIOS `/documents/download/id/{fileId}` attachments

**OPEN QUESTION.** Whether every institution uses this 18-field current template. Only Warszawa plus one municipality detail were opened.

---

## Stable Identifiers

Observed current URL:

```
/wykaz/{slug}/{cardId}/{secondaryId}/{type}
```

Example: `/wykaz/rdos-warszawa/77888/11843/X`

**VERIFIED FACT** in a 2000-row Warszawa `Castor fiber` window:

- `cardId` (first numeric segment) was unique (2000/2000)
- `secondaryId` was **not** unique (658 distinct values; one value appeared 69 times)
- related application/decision pairs often share `secondaryId`
- the same `cardId` loaded with different `secondaryId` values (`/75047/10983/X` and `/75047/2843/X` both returned card `1793/2026`)
- `/77888/0/X` still returned card `4365/2026`
- `/75047/X` did **not** resolve as a card; it returned the listing page
- `type` was `X` on all sampled current-register cards
- card numbers were unique in that 2000-row window, but municipality numbering is a different scheme

**Recommended primary key:**

```
source_system = "ekokarty"
native_record_id = "{slug}:{cardId}"
```

Example: `("ekokarty", "rdos-warszawa:77888")`.

Do **not** use:

- card number alone
- `secondaryId` alone
- SIOS numeric IDs
- `id_inst` from legacy URLs

Store the full observed URL as `source_url`. Treat `secondaryId` as useful related-group evidence, not identity.

**OPEN QUESTION.** Whether `cardId` is unique across all EkoKarty institutions, or only within a slug. Namespace with the slug anyway.

---

## Related Cards and Case References

EkoKarty exposes a useful **card → case signal**, but not a complete case object.

**VERIFIED FACT** from 10 related groups (9 pairs + 1 unpaired application):

| Signal | Observation |
|---|---|
| `Znak sprawy` | Shared by application and decision in all 9 linked pairs |
| `Numery kart innych dokumentów w sprawie` | Present and bidirectional in the 9 pairs |
| Hyperlink | Related card number links to the other card |
| Topic | Shared in the 9 pairs |
| Area | Same or more/less specific wording |
| `Dokument wytworzył` | **Not** shared: decision = RDOŚ, application = applicant |
| Unpaired card | `5065/2024` had related numbers `nie dotyczy` |

Typical pair:

- `4364/2026` wniosek, applicant = Gmina Mszczonów company, case `WPN-I.6401.389.2026.AJC`
- `4365/2026` decyzja, author = Regionalny Dyrektor Ochrony Środowiska w Warszawie, same case

This is high-confidence evidence that two cards belong to one administrative case **when both the case reference and the related-card field agree**. It is not enough to implement clustering yet:

- related field can be empty
- more than two cards per case were not sampled
- `secondaryId` is correlated but unstable
- location strings are not canonical

---

## Attachments and Public Documents

**VERIFIED FACT.** Most sampled Warszawa cards store field 13 as `nie dotyczy`. The public card is metadata. `PODGLĄD` is the card HTML, not an attachment.

One 2015 card listed a public URL:

`http://mmm.rdos.gov.pl/doc/waw/dec2015/6401.102.2015.ml.pdf`

That URL is on an RDOŚ host, not on `ekokarty.pl`. A HEAD request **timed out**. The file is publicly *cited*, but retrieval was **not verified**. No authentication challenge was received because the connection did not complete.

**ASSUMPTION.** When a file exists, it belongs to the cited document/card, not to an EkoKarty file store.

Do not bulk-download these URLs in the collector. Record the URL in `raw_fields` only.

---

## SIOS ↔ EkoKarty Overlap

Small sample, RDOŚ Warszawa cards vs public SIOS nationwide/`nocard`/mazowieckie search.

| EkoKarty card | SIOS equivalent | Confidence | Evidence |
|---|---|---|---|
| `4365/2026`, case `WPN-I.6401.389.2026.AJC` | none | **NO_MATCH_FOUND** | SIOS `nocard=4365/2026` returned “Brak wyników”; case-mark keyword search returned no result table |
| `4364/2026` (related wniosek) | none | **NO_MATCH_FOUND** | Same case-mark search empty |
| `4130/2015`, case `WSTII-R.6401.102.2015.ML` | none | **NO_MATCH_FOUND** | SIOS `nocard` and case-mark searches empty |
| `5217/2025`, case `WSTS.6401.58.2025.DT` | none | **NO_MATCH_FOUND** | SIOS searches empty |
| `3392/2026`, case `WSTS.6401.40.2026.DT` | none | **NO_MATCH_FOUND** | SIOS searches empty |

Additional SIOS check: `id_provinces=7` (mazowieckie) + `Castor fiber` returned **3** cards, all published by **GDOŚ**, none by RDOŚ Warszawa.

The local SIOS SQLite sample (317 cards) contained **0** rows with Warszawa in `authority` and **0** with mazowieckie in `location`.

**ASSUMPTION.** RDOŚ Warszawa currently publishes the public environmental-card register on EkoKarty, not in SIOS. Overlap may still exist for other authorities that use both systems.

Do not write a cross-source identity rule yet. If a later match appears, corroborate on `(authority, znak sprawy, card number/year, document date)` and still keep namespaced IDs.

---

## NormalizedCard Mapping

Comparison against the current SIOS collector’s `CardRecord` / storage fields.

| Normalized field | SIOS | EkoKarty | Notes |
|---|---|---|---|
| source / source_system | derived (`sios`) | derived (`ekokarty`) | Keep namespaced |
| source_card_id / native_record_id | direct (`sios_id`) | derived (`{slug}:{cardId}`) | First URL segment, not card number |
| card_number | direct | direct | Format differs by institution |
| year | derived from card number | listing year direct; else derived | |
| authority | direct `Nazwa organu` | derived / inconsistent | Dataset heading is the register owner; field 8 is author/applicant |
| document_type | direct | direct | |
| document_name | direct | direct | |
| case_reference | direct | direct `Znak sprawy` | Strong case signal |
| voivodeship | direct | unavailable / derived | Free-text area only |
| county | direct | unavailable / derived | |
| municipality | direct | unavailable / derived | |
| entered_at | direct `Data wprowadzenia` | unavailable | Do not invent |
| published_at / listing date | `Data zamieszczenia dokumentu` | `Data zamieszczenie w wykazie…` / listing `Data karty` | Best incremental date |
| document date | `Data wydania` | `Data dokumentu` | |
| source_url | direct | direct | Full URL |
| attachments_metadata | direct when linked | inconsistent | External URL or `nie dotyczy` |
| related_cards | direct | direct | Card numbers + links |
| matched_keywords | derived | derived | Same collector concern |
| raw_fields | direct | direct | Preserve original labels |
| first_seen_at / last_seen_at | monitoring | monitoring | Ours, not source dates |
| province source | SIOS `id_provinces` | unavailable | EkoKarty scope is institution slug |

---

## Operational Constraints

**VERIFIED FACT.**

- No `robots.txt` is published; the path returns a 404-style HTML page
- No public regulamin/terms page was found on `ekokarty.pl`
- No CAPTCHA, CSRF token, or session cookie was required for public listing/detail
- No HTTP 429 was observed in this small sample
- 2000-row responses are about 1.1 MB of HTML
- Detail pages include clerk names in the version table and may include `Osoba prywatna` as applicant

**OPEN QUESTION.** Rate limits, WAF behaviour, and whether the operator objects to automated collection.

Treat this like SIOS: public metadata only, conservative pacing, identifiable User-Agent, organisational approval before scheduled collection. Do not implement evasion.

Personal data: treat stored EkoKarty HTML/SQLite as containing personal data under RODO.

---

## Recommended Collection Strategy

Recommend **direct HTTP + HTML parsing**.

Not required for the public path: browser automation, JSON API, or login.

Practical approach if an adapter is approved:

1. Configure known institution slugs, starting with `rdos-warszawa`.
2. `POST` the institution listing with `szukajRodzaj=NEW` and keyword union (`bóbr`, `Castor fiber`, `bobra europejskiego`, plus narrower terms).
3. If a response contains 2000 rows, repeat with `data_od` / `data_do` windows until each window is `< 2000`.
4. Parse `data-href`, fetch detail GETs, keep raw labels.
5. Identity: `("ekokarty", "{slug}:{cardId}")`.
6. Incremental date: listing/`Data zamieszczenie w wykazie`, not SIOS `entered_at`.
7. Record attachment URLs; do not download files in collection.
8. Keep SIOS mazowieckie province monitoring. Do not replace it with EkoKarty.

---

## Open Questions

1. What is the true size of the RDOŚ Warszawa register behind the 2000-row cap?
2. Is `cardId` unique across institutions, or only within a slug?
3. What does `secondaryId` represent (applicant, case, internal person/org id)?
4. Do all institutions share the 18-field current template?
5. Are any other RDOŚ present under unexpected slugs?
6. Can legacy `index.php?id=&id_inst=` URLs still resolve cards?
7. Are cited external PDFs durably public?
8. Does any authority publish the same card in both SIOS and EkoKarty?
9. Is there a public slug catalogue from Arisco/EDOŚ?
10. What incremental ordering guarantees exist besides “mostly newest listing date first”?

---

## Proposed Next Step

Do **not** implement a nationwide EkoKarty collector.

If product priority is RDOŚ Warszawa beaver/derogation monitoring, the next implementation step is:

- a small `ekokarty` adapter
- source key `rdos_warszawa`
- slug `rdos-warszawa`
- date-windowed POST search
- namespaced identity
- no attachment downloads
- no cross-source merge

Until that adapter exists, keep using SIOS province sources for the other voivodeships.
