# SIOS Technical Research

**Source:** public search at [https://system.sios.pl/search/common](https://system.sios.pl/search/common)  
**Investigation date:** 2026-10-06  
**Keyword used for primary tests:** `bóbr`  
**Scope:** public search UI and URLs it exposes. No login, no CAPTCHA bypass, no non-public endpoints.

Evidence below is from:

- Browser inspection of the live form and results
- Direct `curl` GET requests without a prior session cookie
- Public JavaScript: `public/js/common.js`, `public/js/application.js`

## Executive Summary

Public SIOS search is a **classic server-rendered PHP page**, not a JSON/REST/GraphQL API. Submitting the form issues an HTTP **GET** to the same URL (`/search/common`) with query parameters. The response is **HTML** (`text/html; charset=UTF-8`, HTTP 200) containing a results table.

Card details are a second HTML GET: `/documents/details/id/{numericId}`. In the browser they often open in Fancybox (`type: 'ajax'` in application JS); the same URL also returns the HTML fragment when requested directly.

**Recommended collection method: direct HTTP GET + HTML parsing.** A session cookie is issued (`PHPSESSID`) but is **not required** for search or public card HTML. Playwright is unnecessary for the public search path.

Nationwide search works: omit `iid` or use hidden default `iid=0`. Unfiltered nationwide search on 2026-10-06 returned **354 954** cards. Keyword `bóbr` returned **3 115**. `iid` is an **institution / authority scope**, not a voivodeship.

## Search Architecture

| Question | Verified answer |
|---|---|
| Fetch / XHR for results? | **No.** Results arrive as a full HTML page after GET navigation. |
| REST JSON API? | **Not used** by the public search form. |
| GraphQL? | **Not observed.** |
| Server-side form submission? | **Yes.** `<form method="get">` with `action` resolving to `https://system.sios.pl/search/common`. |
| Server-rendered HTML? | **Yes.** |
| CSRF token? | **None** in the form, meta tags, or request. |
| CAPTCHA on public search? | **None** observed. |

Auxiliary XHR **does** exist, but only for cascading location dropdowns (not for result lists):

- `GET https://system.sios.pl/ajax/districts/id_provinces/{provinceId}` → HTML `<select name="id_districts">`
- `GET https://system.sios.pl/ajax/communities/id_districts/{districtId}` → HTML `<select name="id_communities">`

Card preview in the UI uses jQuery Fancybox AJAX against `/documents/details/id/{id}` (same HTML as a direct GET).

Authenticated/internal routes exist in JS (`documents/advancedsearch`, `documents/get-no-card/year/...`) but **`/documents/advancedsearch` returned HTTP 302 to `/index/charakt` without a login session**. Those were not used further.

Stack signals (response headers / markup): Apache, PHP session cookies, Plesk (`X-Powered-By: PleskLin`), jQuery 1.x UI, vendor “Internet Community”.

## Network Requests

Session cookie values are omitted. The server **Set-Cookie: PHPSESSID=...; path=/** on almost every response. Sending that cookie is **not required** for the requests below (verified with fresh `curl`).

No special request headers were required beyond a normal GET. `Content-Type` is not sent on these GETs. Request body is empty.

### 1. Public search (primary)

- **Endpoint:** `https://system.sios.pl/search/common`
- **Method:** `GET`
- **Content type (response):** `text/html; charset=UTF-8`
- **Status:** `200` (verified)
- **Parameters:** see [Search Parameters](#search-parameters)
- **Cookies:** optional `PHPSESSID`; also JS may set `screenWidth`, `screenHeight`, `acceptCookie` (not required for search)
- **CSRF:** none

**Example request (nationwide keyword search, equivalent to the filled form):**

```http
GET /search/common?doc_date_from=&doc_date_to=&doc_receipt_from=&doc_receipt_to=&approved_date_from=&approved_date_to=&id_provinces=&keywords=b%C3%B3br&nocard=&id_doctype=0&docname=&id_doctopic=0&id_provinces1=&id_districts1=&id_communities1=&iid=0&submitSearch=Szukaj HTTP/1.1
Host: system.sios.pl
```

A shorter request also works:

```http
GET /search/common?keywords=b%C3%B3br&iid=0 HTTP/1.1
Host: system.sios.pl
```

`submitSearch=Szukaj` is **not required** if `keywords` is present (verified: same 3 115 hits and same first-page IDs).

**Example response structure (HTML, abbreviated):**

```html
<div>Liczba wyświetlanych pozycji: 3115</div>
<select name="results" id="results">
  <option value="10">10</option>
  <option value="20">20</option>
  <option value="30" selected="selected">30</option>
  <option value="50">50</option>
  <option value="100">100</option>
</select>

<div class="pages">
  <a href="https://system.sios.pl/search/common?&amp;page=1&amp;keywords=bóbr&amp;..." class="page active">1</a>
  <a href="...page=2..." class="page ">2</a>
  <!-- ... -->
  <span class="kropki">...</span>
  <a href="...page=104...">104</a>
</div>

<table>
  <tr>
    <th>Nr karty</th>
    <th>Rodzaj / Temat dokumentu</th>
    <th>Nazwa / zakres dokumentu</th>
    <th>Data / znak sprawy</th>
    <th>Lokalizacja</th>
    <th>Opcje</th>
  </tr>
  <tr>
    <td><a href="documents/details/id/449913" class="fancybox">2047/2026</a></td>
    <td>decyzje <br>Tematy:<br>- ochrona zwierząt oraz roślin<br></td>
    <td>Decyzja <br>w której zezwolono na ... bobry europejskie ...</td>
    <td><br>WOPN.6401.7.79.2026.ASM.3</td>
    <td>warmińsko-mazurskie / olsztyński / Dywity</td>
    <td>
      <a href="documents/details/id/449913" class="fancybox">...</a>
      <a href="documents/details/id/449913" onclick="printDetailsFast(...)">...</a>
    </td>
  </tr>
</table>
```

### 2. Pagination / page size

Same endpoint. Extra query params:

- `page` — 1-based page index
- `results` — page size

```http
GET /search/common?page=2&keywords=b%C3%B3br&id_doctype=0&id_doctopic=0&iid=0&submitSearch=Szukaj
GET /search/common?keywords=b%C3%B3br&iid=0&results=100&submitSearch=Szukaj
```

Changing the UI page-size `<select id="results">` does a full navigation: current URL with `results={n}` appended (`common.js`).

### 3. Column sort (`/search/extend`)

Header links go to **`/search/extend`** (still HTML, HTTP 200), not JSON.

Example:

```http
GET /search/extend?sort=nodoc&nodocdirection=asc&keywords=b%C3%B3br&iid=0&submitSearch=Szukaj
```

Verified `sort` keys from live header links:

| UI label | `sort=` | direction param |
|---|---|---|
| Nr karty | `nodoc` | `nodocdirection` |
| Rodzaj | `type` | `typedirection` |
| Temat dokumentu | `topic` | `topicdirection` |
| Nazwa / zakres dokumentu | `docname` | `docnamedirection` |
| Data | `doc_date` | `doc_datedirection` |
| znak sprawy | `mark_case` | `mark_casedirection` |
| Lokalizacja | `id_provinces` | `id_provincesdirection` |

Default list order (no `sort`) for `bóbr` was newest-looking numeric IDs first (`449913`, `449844`, …). `sort=nodoc&nodocdirection=asc` started at card `39/2011` (`id=3362`). Hit count stayed **3 115**.

### 4. Card detail HTML

- **Endpoint:** `https://system.sios.pl/documents/details/id/{id}`
- **Method:** `GET`
- **Status:** `200`
- **Response:** HTML **fragment** (no full document chrome), `text/html; charset=UTF-8`
- **Example:** `GET /documents/details/id/449913`

Related public exports (same card metadata, not a hidden API):

| URL | Status | Notes |
|---|---|---|
| `/documents/pdfdetails/id/449913` | 200 | `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="podglad_karty.pdf"` |
| `/documents/xlsdetails/id/449913` | 200 | Excel-compatible HTML/XLS download `podglad_karty.xls` |

### 5. Public attachment download (when the card lists a file)

- **Endpoint:** `https://system.sios.pl/documents/download/id/{fileId}`
- **Method:** `GET` / `HEAD`
- **Status:** `200` (verified `HEAD` on `id/27565`, linked from public card `449707`)
- **Headers:** `Content-Disposition: attachment; filename=wop.6401.2.116.2026.dwa_wniosek.pdf`

File IDs (`27565`) are **not** the same as card IDs (`449707`).

### 6. Location dropdown AJAX

```http
GET /ajax/districts/id_provinces/14 HTTP/1.1
```

Response `200`, `text/html`, body is a `<select>` of counties in warmińsko-mazurskie (`value="319"` = olsztyński, etc.).

```http
GET /ajax/communities/id_districts/1 HTTP/1.1
```

Response `200`, HTML `<select>` of gminas (for district id `1`: Bolesławiec area).

### 7. Not a public search API

```http
GET /documents/advancedsearch
→ 302 location: https://system.sios.pl/index/charakt
```

## Search Parameters

All form fields are **optional**. Empty nationwide search (`submitSearch=Szukaj&iid=0`) returned **354 954** rows — institution and voivodeship are **not** required.

| UI label | HTML `name` | Type | Backend influence | Notes |
|---|---|---|---|---|
| Data wpływu dokumentu Od/Do | `doc_date_from`, `doc_date_to` | text, `yy-mm-dd` | submitted when non-empty | Datepicker class `datepicker`; JS `yearRange: '1990:2025'` but typed/GET `2026-…` still works |
| Data wydania dokumentu Od/Do | `doc_receipt_from`, `doc_receipt_to` | text, `yy-mm-dd` | yes | **Name is `doc_receipt_*` despite “wydania” label.** `bóbr` + issuance 2026-01-01..2026-12-31 → **796** hits |
| Data zatwierdzenia Od/Do | `approved_date_from`, `approved_date_to` | text | submitted | not separately counted |
| Województwo | `id_provinces` | select `1`–`16` | yes | empty = all. `14` (warmińsko-mazurskie) + `bóbr` → **610** |
| Powiat | `id_districts` | select, disabled until province chosen | omitted while disabled | values from `/ajax/districts/...` |
| gmina | `id_communities` | select, disabled until county chosen | omitted while disabled | values from `/ajax/communities/...` |
| Słowo kluczowe | `keywords` | text, `maxlength=64` | yes | see keyword section |
| Numer karty informacyjnej w roku | `nocard` | text | yes | placeholder `1/2026`. Year alone (`2026`) → **no hits**. `2047/2026` → **2** cards (not unique nationally) |
| Rodzaj dokumentu | `id_doctype` | select | default `0` = all | values `1`–`23` |
| Nazwa dokumentu | `docname` | text | submitted | not separately counted |
| Temat dokumentu | `id_doctopic` | select | default `0` = all | values look like bit flags: 1,2,4,8,16,32,**64**,128. `64` = ochrona zwierząt oraz roślin. `bóbr` + topic 64 → **2591** (vs 3115) |
| *(hidden)* | `id_provinces1`, `id_districts1`, `id_communities1` | hidden | submitted empty | purpose **not verified** (second location?) |
| *(hidden)* | `iid` | hidden | **yes** | default `0` = nationwide; `>0` = one institution |
| Szukaj | `submitSearch` | submit | optional | value `Szukaj` |
| Liczba wyników na stronę | `results` | select / query | yes | UI: 10,20,30,50,100. **200 and 500 also accepted** via query string |

### Document type values (`id_doctype`)

Verified from the live `<select>`:

1. wnioski o wydanie decyzji  
2. wnioski o udzielenie wskazań lokalizacyjnych  
3. inne wnioski  
4. decyzje  
5. postanowienia  
6. polityki, strategie, plany lub programy  
7. projekt polityk, strategii, planów lub programów  
8. projekty innych dokumentów  
9. raporty o oddziaływaniu przedsięwzięcia na środowisko  
10. inne raporty  
11. przeglądy ekologiczne  
12. prognozy oddziaływania na środowisko  
13. wykazy zawierające informacje i dane o zakresie korzystania ze środowiska  
14. rejestry  
15. zgłoszenia  
16. strategiczne oceny oddziaływania na środowisko  
17. koncesje, pozwolenia, zezwolenia  
18. analizy, opracowania ekofizjologiczne, wyniki badań i pomiarów  
19. mapy akustyczne  
20. świadectwa  
21. sprawozdania  
22. deklaracje środowiskowe  
23. inne dokumenty  

### Document topic values (`id_doctopic`)

| Value | Label |
|---:|---|
| 0 | (all / empty) |
| 1 | ochrona powietrza |
| 2 | ochrona wód |
| 4 | ochrona powierzchni ziemi |
| 8 | ochrona przed hałasem |
| 16 | ochrona przed polami elektromagnetycznymi |
| 32 | ochrona kopalin |
| 64 | ochrona zwierząt oraz roślin |
| 128 | inne |

Whether multiple topic bits can be OR-ed in one request was **not tested**.

### Voivodeship values (`id_provinces`)

1 dolnośląskie … 16 zachodniopomorskie (full list in the form). There is **no year-only filter** in the public form.

## Pagination

Verified for `keywords=bóbr`, `iid=0`, default page size:

| Fact | Value |
|---|---|
| Total hits | **3115** (`Liczba wyświetlanych pozycji`) |
| Default page size | **30** (`selected` on `#results`) |
| UI page sizes | 10, 20, 30, 50, 100 |
| Extra page sizes accepted | **200** (200 unique IDs), **500** (500 unique IDs) |
| Page parameter | `page` (1-based) |
| Last page | **104** (103×30 + 25 = 3115) |
| Page 1 vs page 2 | **no overlapping** document IDs |
| Page 104 vs 105 | **identical 25 IDs** — overflow pages **repeat the last page**, they do not 404 or return empty |
| Exhaustive retrieval | **Yes**, by walking `page=1..ceil(total/pageSize)` **or** using a larger `results` and fewer pages |
| Within-page duplicates | Each card ID appears 3 times in HTML (number link + preview + print). Unique IDs per page = page size |

**Collector implication:** stop using `ceil(total/results)`, not “stop when a page is empty”. A naive empty-page loop will never terminate if it only checks for missing rows after the last page.

Sorting is stable enough for pagination **within one result snapshot**, but the index is live (`Cache-Control: no-store`). New cards can shift pages. Use the numeric `documents/details/id/{id}` as the dedup key, not page offsets.

## Search Result Schema

Source: first result row for `bóbr` (card `2047/2026`, id `449913`) plus neighbouring rows.

| Field | Example | Source | Notes |
|---|---|---|---|
| Card number / year | `2047/2026` | results table, link text | **Not globally unique** (see Identifiers) |
| Internal card ID | `449913` | URL `documents/details/id/449913` | **Stable unique ID** in all tests |
| Direct card URL | `https://system.sios.pl/documents/details/id/449913` | results + details | Relative in HTML |
| Document type (label) | `decyzje` | results col “Rodzaj” | Text, not the numeric `id_doctype` |
| Topics | `ochrona zwierząt oraz roślin` | results “Tematy:” | May be multiple lines |
| Document name | `Decyzja` | first line of “Nazwa / zakres” | Often short |
| Subject / scope (truncated) | `w której zezwolono na ... bobry europejskie ...` | rest of same cell | Truncated with `...` on the list |
| Date | `2026-09-16` or empty | “Data / znak sprawy” | Sometimes missing (e.g. first `2047/2026` row had no date, only case mark) |
| Case mark (`znak sprawy`) | `WOPN.6401.7.79.2026.ASM.3` | same cell | |
| Voivodeship | `warmińsko-mazurskie` | “Lokalizacja” | `woj / powiat / gmina` |
| County | `olsztyński` | Lokalizacja | May be empty (`śląskie / /` on another `2047/2026`) |
| Municipality | `Dywity` | Lokalizacja | |
| Institution ID | — | **not in result rows** | Only via search `iid` when scoped |
| Authority / organ name | — | **not in result rows** | On detail page |
| Description full text | truncated | list | Full text on detail page |

## Card Detail Schema

Verified on several public cards (`449913`, `449844`, `449792`, `3362`, `445167`, `434045`, `449707`). Additional fields beyond the list:

| Field | Example | Notes |
|---|---|---|
| Numer karty/rok | `2047/2026` | |
| Rodzaj dokumentu | `decyzje` | |
| Temat dokumentu | `- ochrona zwierząt oraz roślin` | |
| Nazwa dokumentu | `Decyzja` | |
| Zakres przedmiotowy dokumentu | full untruncated subject | Includes species, plots, gmina, prohibited acts |
| Województwo / Powiat / Gmina | as list, sometimes empty | |
| Znak sprawy | `WOPN.6401.7.79.2026.ASM.3` | |
| Dokument wytworzył | `Regionalny Dyrektor Ochrony Środowiska w Olsztynie, ul. Dworcowa 60, 10-437 Olsztyn` | Person or office |
| Data wpływu dokumentu | empty or `2011-02-16` | |
| Data wydania dokumentu | `2026-10-06` | |
| Dokument zatwierdził | `nie dotyczy` | |
| Data zatwierdzenia dokumentu | `nie dotyczy` | |
| Nazwa organu (storage) | `Regionalna Dyrekcja Ochrony Środowiska w Olsztynie` | Holding authority |
| Siedziba | address | |
| Telefon / E-mail | public contact | |
| Dokument uległ zniszczeniu | `NIE` | |
| Wersja elektroniczna | `Brak załączników.` **or** named file + `/documents/download/id/{fileId}` | Public when linked |
| Czy dokument jest ostateczny | `TAK` | |
| Data zamieszczenia dokumentu | `2026-10-06` | Publication in SIOS |
| Uwagi | often empty | |
| Informacja może być udostępniona | `TAK` | Flag that the information **may be disclosed** (access-to-information pathway), even when a file is already attached |
| Podstawa prawna | often empty | |
| Zakres (access scope) | often empty | Distinct from “zakres przedmiotowy” |
| Numery kart innych dokumentów w sprawie | link `1939/2026` → `/documents/details/id/449844` | Related cards |
| Informacje wprowadził/a — imię i nazwisko | clerk name | |
| Data wprowadzenia | `2026-10-06 13:40:13` | |
| PDF/XLS export of the **card** | `/documents/pdfdetails/id/{id}` | Metadata printout, not necessarily the source PDF |

**What typically still needs an information-access request**

- Cards with **Brak załączników** (majority of the sample): only the information card is public, not the underlying decision/application file.
- Empty “Podstawa prawna” / “Zakres” do not block the “Informacja może być udostępniona = TAK” flag.
- This research did **not** log in or request non-public files. If a download URL is not rendered on the public card, it was not fetched.

**Public attachments** (when shown) use `/documents/download/id/{fileId}` and returned HTTP 200 without authentication on a HEAD of a file linked from card `449707`.

## Identifiers

| Identifier | Example | Stable? | Unique? |
|---|---|---|---|
| Document / card ID | `449913` in `/documents/details/id/449913` | Yes in all samples (monotonic, used in all card URLs) | **Best unique key** |
| Card number | `2047/2026` (`nocard`) | Year-scoped number **per institution** | **No nationally.** Same `2047/2026` → ids `449913` (RDOŚ Olsztyn / Dywity) and `434045` (śląskie / Wody Polskie / RDOŚ Katowice matter) |
| Institution ID (`iid`) | `9` = Starostwo Powiatowe w Tarnowskich Górach | Yes as a SIOS tenant key | Scopes the whole search. **Not printed on the card HTML** |
| Attachment file ID | `27565` in `/documents/download/id/27565` | Appears stable | Distinct from card ID |
| Case mark | `WOPN.6401.7.79.2026` | Useful correlator | Not unique across related wniosek/decyzja cards |
| URL structure | `/search/common?…`, `/documents/details/id/{id}`, `/search/extend?sort=…` | Path style is Zend/PHP MVC | |

**URL patterns**

```
https://system.sios.pl/search/common                  # national (iid omitted or 0)
https://system.sios.pl/search/common?iid=9            # one institution
https://system.sios.pl/documents/details/id/449913    # card
https://system.sios.pl/documents/download/id/27565    # attachment
https://system.sios.pl/documents/pdfdetails/id/449913
https://system.sios.pl/ajax/districts/id_provinces/14
https://system.sios.pl/ajax/communities/id_districts/319
```

## Geographic Scope

**Yes — `/search/common` without a positive `iid` searches the national SIOS public index** (all participating institutions that publish into this system). Evidence:

- Homepage copy: public BIP search is offered at `https://system.sios.pl/search/common`
- Hidden field `iid=0` on the unscoped form
- Omitting `iid` entirely produced the **same 3 115** `bóbr` IDs as `iid=0`
- Empty search: **354 954** cards
- Result locations span many voivodeships; `id_provinces` further filters that national set

**`iid` means institution / authority (SIOS licensee), not voivodeship.** Verified by live headings `Wyszukiwanie kart: {organ name}`:

| `iid` | Heading | `bóbr` hits |
|---:|---|---:|
| 0 / omitted | *(no institution name)* | 3115 |
| 1 | Internet Community | 0 |
| 2 | Urząd Miasta Testowo | 0 |
| 8 | Urząd Miasta Olsztyn | 1 |
| 9 | Starostwo Powiatowe w Tarnowskich Górach | 131 |
| 14 | Gmina Miasta Sopotu | 0 |
| 16 | Starostwo Powiatowe w Grodzisku Wielkopolskim | 0 |

Reset JS keeps `iid` only when `iid > 0`, confirming it is a dataset/tenant scope.

**Not verified:** that every Polish public authority is in SIOS. Vendor pages describe a licensed product. Empty nationwide search counts **SIOS-published** cards, not the entire Polish environmental-case universe. RDOŚ cards appear in the national index (e.g. Olsztyn, Opole, Katowice on details) even when a small `iid` sample of gminas/starostwa was used.

Nationwide beaver monitoring should use **`iid=0` / omit `iid`**, not a loop of all `iid` values (unless the goal is per-institution partitions).

## Keyword Search Behaviour

All tests: `iid=0`, `id_doctype=0`, `id_doctopic=0`, 2026-10-06.

| Query | Hits | First-page IDs (sample) | Notes |
|---|---:|---|---|
| `bóbr` | **3115** | 449913, 449844, 449792… | Baseline |
| `bobr` (no ó) | **3115** | **identical first page** | Accent-insensitive for this pair |
| `bobry` | **414** | 449913, 449739, 449528… | **Not** the same set as `bóbr`. First page: 29/30 IDs also appeared in the `bóbr` `results=200` window; 1 did not (so `bobry` is not a strict subset of the first 200 `bóbr` hits, and totals differ a lot) |
| `Castor fiber` | **749** | 449713, 449558, 449528… | Scientific name; **substantially different count**. All 30 first-page IDs were inside the `bóbr` top-200 |
| `zwierząt chronionych` | **21** | 445167, 444918, 444912… | Phrase/token search; almost disjoint from `bóbr` top-200 (1 overlap) |
| `bóbr europejski` | **104** | 449488, 448834, 448833… | Far fewer than `bóbr` alone → **all tokens required** (AND), not OR, and not a synonym expansion of `bóbr` |

**Interpretation (evidence-based, not vendor docs):**

- **Not** simple stemming of `bóbr` ↔ `bobry` (counts 3115 vs 414).
- **Not** a synonym thesaurus that maps `Castor fiber` onto `bóbr` (749 vs 3115).
- **Substring / full-text over card fields** is plausible: `bóbr` matches “bobra”, “bobry”, “bobrów”, “bobrowych” inside descriptions, while `bobry` matches a narrower token.
- **Diacritics:** `bobr` ≡ `bóbr` in this test.
- **Multi-word:** AND of tokens (`bóbr europejski` ⊂ conceptually `bóbr`).
- Topic filter `id_doctopic=64` still misses some `bóbr` hits (2591 vs 3115), so keyword search is **not limited** to the “ochrona zwierząt oraz roślin” topic.

For beaver monitoring, a **union of several queries** (`bóbr`, `bobry`, `Castor fiber`, maybe `bobrow`) will be more complete than a single keyword. Do not assume one query is exhaustive.

## Recommended Collection Strategy

**Recommend: direct HTTP GET + HTML parsing.**

| Option | Verdict |
|---|---|
| 1. Direct HTTP to a public endpoint | **Yes.** Stable GET URLs, no CSRF, no login, HTML 200. |
| 2. Parsing server-rendered HTML | **Required**, because that endpoint returns HTML, not JSON. |
| 3. Playwright | **Not necessary** for search/list/details/downloads that are already plain GET. Use only later if a public path starts requiring JS-only anti-bot (none seen today). |

Practical approach for a later collector:

1. `GET /search/common` with `keywords`, `iid=0`, `results=100` (or 200/500), `page=n`.
2. Parse total count, unique `documents/details/id/{id}`, list columns.
3. `GET /documents/details/id/{id}` for full metadata and attachment links.
4. Optionally `GET` listed `/documents/download/id/{fileId}` only when the public card already exposes the link.
5. Deduplicate on numeric card ID.
6. Repeat for keyword variants; union by ID.

Do **not** use `/documents/advancedsearch` (login redirect). Do **not** invent a JSON API.

## Risks and Limitations

### Verified

- **No JSON schema** — HTML scrape will break if markup changes.
- **`Cache-Control: no-store`** — live index; pages can shift between runs.
- **Pagination overflow repeats the last page** — easy to over-count if not using unique IDs.
- **Card number is not a unique key.**
- **Keyword incompleteness** — `bóbr` / `bobry` / `Castor fiber` return different sets.
- **SIOS is a licensed subset** of public bodies, not a legal guarantee of every Polish case.
- **`robots.txt`:** `User-Agent: *` / `Disallow: /` — automated collection is technically possible but **politely disallowed**. A production collector needs an explicit legal/ops decision (rate limits, identification, ToS/regulamin).
- **Clerk personal names** appear on cards (`Informacje wprowadził/a`) — treat as personal data under RODO.
- **Related-card graph** exists but is incomplete on some cards.
- **Datepicker JS `yearRange` ends at 2025** while data in 2026 exists — UI-only limitation; GET params still work.
- **Disabled geo selects are omitted** from GET (standard HTML). Collector must enable/include `id_districts` / `id_communities` only after loading AJAX options.
- **`documents/advancedsearch` is not public.**

### Not verified (do not treat as facts)

- Presence or absence of **rate limiting** / WAF beyond this session. Dozens of sequential GETs returned 200; no `429` was seen. That does **not** prove unlimited access.
- Whether `results` above 500 is capped.
- Whether topic values can be combined as bitmasks.
- Exact full-text engine (MySQL `LIKE` vs `FULLTEXT` vs other).
- Completeness of location fields (some rows have empty powiat/gmina).
- Long-term stability of numeric IDs if the vendor ever migrates the DB (they behaved as durable primary keys today).
- Whether **all** attachments linked on public cards remain unauthenticated (only one `HEAD` was checked).
- Session timeout JS (30 minutes → `/logout`) — relevant to logged-in users, **not** to the public GET flow tested.

### Ways a scraper can miss records (technical)

1. Using only one keyword.
2. Filtering `id_doctopic=64` and assuming it equals “protected species”.
3. Using `nocard` or card number as the primary key.
4. Stopping pagination on a non-empty repeated last page, or assuming page 105 is empty.
5. Scraping a single `iid` and thinking it is national.
6. Parsing only visible text and missing IDs in `href`.
7. Ignoring cards whose list snippet does not contain the keyword but whose full “zakres” does (mitigated if search itself is used).
8. Too-high concurrency triggering untested throttling (assumption).

## Proposed Next Step

Build a **minimal collector** (not in this task) that:

1. Issues polite, identifiable GETs to `/search/common` with a small keyword list (`bóbr`, `bobry`, `Castor fiber`).
2. Uses `iid=0`, `results=100`, walks `page=1..N` from the reported total.
3. Parses HTML for numeric IDs and list fields; fetches `/documents/details/id/{id}` for each new ID.
4. Stores raw HTML or a mapped record keyed by numeric ID; records query, page, and fetch timestamp.
5. Sleeps between requests; does not log in; downloads `/documents/download/id/{fileId}` only when the public card already lists it.
6. Treats “Informacja może być udostępniona” as a later workflow flag for generating information-access requests when attachments are missing.

Do **not** add a frontend, database productization, or AI classification until this collector is proven against a short keyword run and ID-level diffs between queries.

## Appendix — Example detail fragment (public)

Card `449913` (`GET /documents/details/id/449913`), fields only:

- Numer karty/rok: `2047/2026`
- Rodzaj: `decyzje`
- Temat: ochrona zwierząt oraz roślin
- Organ: Regionalna Dyrekcja Ochrony Środowiska w Olsztynie
- Załączniki: Brak załączników
- Informacja może być udostępniona: TAK
- Related card: `1939/2026` → id `449844`
