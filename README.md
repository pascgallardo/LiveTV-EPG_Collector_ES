# LiveTVCollectorES

A GitHub repository that automatically collects, filters, and exports live TV streaming links per country using GitHub Actions. This project fetches M3U playlists from multiple sources, removes duplicates, and exports them into various formats under the `LiveTV/Country Name/` directory.

Fork of [bugsfreeweb/LiveTVCollector](https://github.com/bugsfreeweb/LiveTVCollector), currently tracking **Spain**.

# 📊 Project Stats
[![GitHub forks](https://img.shields.io/github/forks/pascgallardo/LiveTVCollectorES?logo=forks&style=plastic)](https://github.com/pascgallardo/LiveTVCollectorES/network) [![GitHub stars](https://img.shields.io/github/stars/pascgallardo/LiveTVCollectorES)](https://github.com/pascgallardo/LiveTVCollectorES/stargazers) [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)  [![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](https://lbesson.mit-license.org/)
![GitHub issues](https://img.shields.io/github/issues/pascgallardo/LiveTVCollectorES)
![GitHub pull requests](https://img.shields.io/github/issues-pr/pascgallardo/LiveTVCollectorES)

## Online Useable Tools:
<a href="https://gmtv.netlify.app" target="_blank"><img src="https://gmtv.netlify.app/img/gmtv.png" style="width:auto; height:60px" alt="GM TV Player"></a>
<a href="https://lolstream.netlify.app" target="_blank"><img src="https://lolstream.netlify.app/img/logo.png" style="width:auto; height:60px" alt="Stream Player"></a>
<a href="https://pismarttv.netlify.app" target="_blank"><img src="https://pismarttv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="IPTV Player"></a>
<a href="https://hodliptv.netlify.app" target="_blank"><img src="https://hodliptv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="IPTV Player"></a>
<a href="https://pixstream.netlify.app" target="_blank"><img src="https://pixstream.netlify.app/img/logo.png" style="width:auto; height:60px" alt="IPTV Player"></a>
<a href="https://buddytv.netlify.app" target="_blank"><img src="https://buddytv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="BuddyTv"></a>
<a href="https://m3uchecker.netlify.app" target="_blank"><img src="https://m3uchecker.netlify.app/img/logo.png" style="width:auto; height:60px" alt="M3U Checker"></a>
<a href="https://birdseyetv.netlify.app" target="_blank"><img src="https://birdseyetv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="BirdseyeTV player"></a>
<a href="https://circletv.netlify.app" target="_blank"><img src="https://circletv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="CircleTV player"></a>
<a href="https://bugsfreeweb.github.io/iptv" target="_blank"><img src="https://bugsfreeweb.github.io/iptv/img/logo.png" style="width:auto; height:60px" alt="IPTV player"></a>
<a href="https://m3ueditor.netlify.app" target="_blank"><img src="https://m3ueditor.netlify.app/img/logo.png" style="width:auto; height:60px" alt="M3U Editor"></a>
<a href="https://bugsfreeweb.github.io/WebIPTV" target="_blank"><img src="https://bugsfreeweb.github.io/iptv/img/logo.png" style="width:auto; height:60px" alt="Web IPTV"></a>
<a href="https://bugsfreetv.vercel.app" target="_blank"><img src="https://bugsfreetv.vercel.app/img/logo.png" style="width:auto; height:60px" alt="Web IPTV Player"></a>


## Features

- **Automated Updates**: Runs once a day via GitHub Actions, scheduled for **08:00 UTC**. GitHub evaluates cron in UTC and treats `schedule` as best effort, so the run really starts later: measured over the 978 scheduled runs this repository produced between April and September 2026, the median delay was 171 min at 00:00 UTC, **154 min at 08:00 UTC** and 103 min at 16:00 UTC, and no run ever started in under 28 minutes. 16:00 UTC was the least congested slot on record, but the cron was later moved 8 h earlier to 08:00 UTC to publish in the middle of the Spanish afternoon: the delay is a queue that has to be paid either way, so shifting the cron shifts the publication by the same amount, and the ~50 min of extra queueing is well worth the 8 h. In practice the playlists are republished roughly between **11:30 and 15:30 mainland Spain time**. There is deliberately no time gate: a gate could never pass, and would only have kept the workflow from running at all. See [Scheduling](#scheduling) for the full numbers.
- **Large Source Handling**: Streams M3U responses line by line instead of loading whole files, and only materialises the joined text for HTML sources that need parsing.
- **Optional Active Link Verification**: Off by default for speed. Run `python BugsfreeMain/TV-Spain.py --check-links` to probe every stream with 10 concurrent workers (HEAD, falling back to GET and then to the alternate protocol). Results are cached per URL.
- **Duplicate Removal**: Ensures no duplicate streams (based on URL) are included. When the same URL arrives from several playlists, the first source keeps ownership, but a `tvg-id` or `tvg-name` that the first one lacked is filled in from a later source.
- **tvg-* Metadata**: `tvg-id` and `tvg-name` are read from the source `#EXTINF` lines and carried through to every export format. Attributes a source does not provide are simply omitted from the generated `#EXTINF` line.
- **HTML Source Parsing**: A source ending in `.html` is scanned for nested playlist links, filtering out non-stream links (e.g., Telegram, GitHub).
- **Merged EPG Guides**: The EPG (XMLTV) URLs declared by each source playlist are read from its `#EXTM3U url-tvg` attribute, recorded in source order in `epg-sources.json`, and merged by `BugsfreeMain/TV-Spain-EPG.py` into a single `LiveTV.xml` plus its `LiveTV.xml.gz`. The generated playlist points at that merged guide. See [EPG](#epg).
- **Source Order Preserved**: The merged playlist keeps the order of its inputs. A channel stays where its source playlist had it, the first source's channels come first, and a group appears where its first channel appeared. Nothing is alphabetised, so the file reads like the playlists it was built from.
- **Duplicate Channels by `tvg-name`**: When several entries share the same `tvg-name`, only one survives: the first one in playlist order **whose stream actually answers**. The rest are dropped, so a channel never appears twice just because several providers carry it. Channels with no `tvg-name` are never compared with each other.
- **Deterministic Exports**: The order is not randomised: sources are consumed in a fixed sequence and link verification never reshuffles the result, so re-running without source changes produces identical files and no spurious commits. The only exception is the `tvg-name` deduplication, which reads live stream state by design: if a stream goes down, the next run publishes its working backup and the commit is the point.
- **Honest Timestamps**: The `date` field in `LiveTV.json` is the moment the collector actually ran, expressed in `Europe/Madrid` and written as ISO 8601 with an explicit UTC offset (e.g. `2026-09-30T21:14:07+02:00`). Because GitHub's cron never fires on time, this is the only trustworthy publication time, and the offset lets the browser resolve the instant correctly whatever timezone the visitor is in, so the "updated N min ago" banner in `index.html` is accurate.
- **Web Hub (`index.html`)**: Static browser UI to browse the generated playlists, search channels, copy/download links, and track download statistics locally.
- **Multiple Export Formats**:
  - `LiveTV.m3u`: Standard M3U playlist.
  - `LiveTV.txt`: Human-readable text format with detailed channel info.
  - `LiveTV.json`: Structured JSON with channel metadata.
  - `LiveTV`: Custom JSON format without extension, designed for easy integration.

## Exported File Formats

### `LiveTV.m3u`
Standard M3U playlist format. The `#EXTM3U` line carries the EPG guides of the merged sources in `url-tvg`, so the generated playlist keeps the guide data its sources shipped with:
```
#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml, https://www.tdtchannels.com/epg/TV.xml.gz, https://live.s2l.workers.dev/epg.xml"
#EXTINF:-1 tvg-id="AdventureTV.us" tvg-name="Adventure TV" tvg-logo="https://i.imgur.com/VQVr4Nk.png" group-title="Entertainment",Adventure TV
http://109.233.89.170/Adventure_HD/index.m3u8
```

Each source's own `#EXTM3U url-tvg` attribute is read and the URLs are merged in source order, dropping guides that several sources share. Sources that declare no EPG simply contribute nothing, and when no source has one the line stays bare, as `#EXTM3U`.

`url-tvg` only ever holds XMLTV guide URLs (`.xml` / `.xml.gz`); the M3U sources themselves are never listed there, since that attribute is the conventional pointer to EPG data.

`tvg-id` and `tvg-name` on the `#EXTINF` lines are emitted only when the source playlist provided them.

### `LiveTV.txt`
Readable text format. `TvgID` and `TvgName` are written only when present:
```
Group: Entertainment
Name: Adventure TV
TvgID: AdventureTV.us
TvgName: Adventure TV
URL: http://109.233.89.170/Adventure_HD/index.m3u8
Logo: https://i.imgur.com/VQVr4Nk.png
Source: https://example.com/source.m3u
--------------------------------------------------
```

### `LiveTV.json`
Structured JSON with timestamp:
```json
{
  "date": "2026-09-30T21:14:07+02:00",
  "channels": {
    "Entertainment": [
      {
        "name": "Adventure TV",
        "tvg_id": "AdventureTV.us",
        "tvg_name": "Adventure TV",
        "logo": "https://i.imgur.com/VQVr4Nk.png",
        "group": "Entertainment",
        "source": "https://example.com/source.m3u",
        "url": "http://109.233.89.170/Adventure_HD/index.m3u8"
      }
    ]
  }
}
```

### `LiveTV` (Custom Format)
Custom JSON list without extension:
```json
[
  {
    "name": "Adventure TV",
    "tvg_id": "AdventureTV.us",
    "tvg_name": "Adventure TV",
    "type": "Entertainment",
    "url": "http://109.233.89.170/Adventure_HD/index.m3u8",
    "img": "https://i.imgur.com/VQVr4Nk.png"
  }
]
```

## Setup Instructions

### Prerequisites
- A GitHub account and repository (`pascgallardo/LiveTVCollectorES`).
- No local setup required; everything runs via GitHub Actions.

### Steps
1. **Clone or Fork**:
   ```bash
   git clone https://github.com/pascgallardo/LiveTVCollectorES.git
   cd LiveTVCollectorES
   ```

2. **Customize Sources** (Optional):
   - Edit `BugsfreeMain/TV-Spain.py` to update the `source_urls` list with additional M3U sources.

3. **Push Changes**:
   ```bash
   git add .
   git commit -m "Initial setup or source update"
   git push origin main
   ```

4. **Verify Workflow**:
   - Go to the "Actions" tab in your GitHub repository.
   - The workflow "TV-Spain Update Files" runs daily (cron `0 16 * * *`, UTC) or can be triggered manually.

## How It Works

1. **Source Fetching**:
   - Streams M3U files and parses HTML for streaming URLs.
   - Uses `requests` with streaming to handle large files.

2. **Processing**:
   - Removes duplicates based on stream URLs.
   - Collapses duplicate `tvg-name`s across the merged playlist, keeping the first entry whose stream answers (see [Deduplication by `tvg-name`](#deduplication-by-tvg-name)).
   - Optionally verifies link activity with concurrent HEAD/GET requests (2-second timeout, 10 workers) when `--check-links` is passed.

3. **Exporting**:
   - Saves unique channels to four files in `LiveTV/Country Name/`, in source order, so diffs stay small and predictable.

4. **Automation**:
   - GitHub Actions runs `BugsfreeMain/TV-Spain.py` once a day, scheduled for 08:00 UTC.
   - A second job regenerates `LiveTV/index.json` and `Movies/index.json` from the directories present.
   - Commits and pushes changes automatically using `GITHUB_TOKEN`.

## Local usage

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .       # run the test suite
python BugsfreeMain/TV-Spain.py                # fast: no link verification
python BugsfreeMain/TV-Spain.py --check-links # slower: drop unreachable streams
python generate_indexes.py                     # refresh section indexes
```

`index.html` is a static page: serve the repository root over any static host and it reads the generated files from the raw GitHub URL (this repository first, the upstream repository as fallback).

## Deduplication by `tvg-name`

Providers overlap, so the same channel often arrives several times: `La 1` from `Generalistas` and again from `Entretenimiento`, `Runtime` from three different hosts. After the URL-level deduplication (which only removes the same stream repeated) the merged playlist still carried **82 duplicated `tvg-name` groups covering 182 channels**. The collector now collapses them.

**How the winner is chosen.** Candidates are ordered by their position in the merged playlist and probed in that order; the first one whose stream answers wins and the rest are dropped. If none of them answers, the first is kept anyway — a probe that fails because of a network blip must never make a channel disappear from the published playlist.

**How names are compared.** The key is the `tvg-name` trimmed, with internal whitespace collapsed and case ignored, so `La 1`, `la 1  ` and `LA 1` are one channel. Comparing raw strings would have found 72 groups instead of 82 and missed real variants such as `Pocoyó`/`pocoyó` or `24h`/`24H`.

**Scope.** Matching is global across the whole playlist, not per category, because 81 of the 82 duplicated groups span more than one category. A consequence worth knowing: after deduplication, a channel that used to appear under both `Generalistas` and `Entretenimiento` stays only in whichever category comes first.

**Channels without a `tvg-name` are never compared.** There is nothing to match on, so all 69 of them are kept. Treating the empty value as a single key would have deleted 68 channels.

**Cost.** Groups are resolved in parallel and each group stops probing at its winner, so a run probes about 94 URLs instead of the 182 involved — a fraction of the 929 that a full `--check-links` pass would need. With `--check-links` the answers are already in the link status cache and deduplication costs no extra requests.

**Order.** Nothing is reshuffled: the surviving channels keep their position, and a category keeps the position of its first surviving channel. A category left with no channels at all disappears. Measured on the live sources: 929 → 829 channels, 42 categories unchanged, and the surviving 829 entries in exactly the order they had before.

**Determinism.** This is the one place where the export depends on something other than the sources. A stream that goes down will make the next run publish its backup, and one that comes back will make it switch again, so the daily commit is no longer purely a function of the playlists. That is the intended behaviour, but it does trade away part of the deterministic-export guarantee above.

## EPG

`LiveTV.m3u` carries a `url-tvg` attribute pointing at `LiveTV/Spain/LiveTV.xml.gz`, the single guide `BugsfreeMain/TV-Spain-EPG.py` builds. It is refreshed on its own schedule, `0 8 */2 * *`, so every 48 hours at 08:00 UTC.

### What the merge does

The nine source guides the merged playlists declare hold **82 MB of XMLTV** describing 2 267 channels between them, of which the published playlist lists 737 `tvg-id`. Everything is filtered to those 737 before it is written, which is the difference between publishing all of it and publishing a guide that matches the playlist it belongs to: guiatv.xml alone is 33 MB with 644 channels, and only 72 of them are in the playlist.

Three things decide what ends up in the file:

- **Only the playlist's `tvg-id` survive.** Both the `<channel id>` of a guide and the `channel` attribute of a `<programme>` must be one of them. The 26 channels with no guide entry simply have no schedule, and a guide full of channels nobody in this playlist streams is dead weight for a player.
- **The first guide to declare a channel owns it.** guiatv.xml and the s2l workers mirror each other, so ownership has to be decided once and the same way every run, or the output would depend on which download finished first.
- **Programmes are deduplicated on channel, start and stop.** Guides covering different time ranges all contribute; guides repeating the same range do not. On the current data this drops 36 157 matching programmes to 26 915.

Current result: **712 of 737 channels (96.6 %) and 27 067 programmes**, as a 13.2 MB `LiveTV.xml` and a 1.7 MB `LiveTV.xml.gz`.

### Why the sources live in a sidecar file

Pointing `url-tvg` at the merged guide makes the playlist stop listing where that guide came from, which would leave the merger with no way to find its own inputs — it would read the header, find its previous output, and merge that. The collector therefore also writes the source list to `LiveTV/Spain/epg-sources.json`, and that is what the merger reads. The `url-tvg` header is still accepted as a fallback for a checkout that predates the manifest, with any entry pointing at the merger's own output filtered out.

### Guides are read compressed

Every one of the nine is served gzipped, including `guiatv.xml` and `runtime.xml`, whose URLs do not end in `.gz`. Decompression is therefore decided by the gzip magic bytes and never by the extension.

### Reproducibility

Unlike the playlist, the merged guide is *not* a pure function of its inputs: the upstream guides are regenerated with fresh timestamps constantly, so a real run almost always produces a new file and a new commit. What can be pinned down, and is, is everything this script controls. The gzip stream is written with `mtime=0` and no stored filename, so the archive is a pure function of the XML beside it, and no timestamp is written into the document — the publication instant is already in the commit and in `LiveTV.json`. Two runs over unchanged guides therefore produce byte-identical files.

### When it refuses to publish

A run that would replace a good guide with an unusable one fails instead of writing. That covers every guide failing to download and the filter matching nothing, which are reported as the separate causes they are: the first is a network problem, the second means the playlist changed shape.

Note on size: the merged guide is committed every 48 hours and changes almost completely each time, so it adds roughly 1.7 MB per run to the repository history. Publishing the `.gz` alone would halve that.

## Scheduling

GitHub Actions `schedule` is best effort: the trigger is honoured, the start time is not. This repository used to run three slots a day (`0 0,8,16 * * *`), which gives a clean dataset to measure that behaviour. Over the **978 scheduled runs it produced between April and September 2026**, the delay between the scheduled minute and the moment the run actually started was:

| Slot | Runs | Median | Mean | p75 | p90 | Started within +1 h | +2 h |
|---|---|---|---|---|---|---|---|
| `00:00Z` | 326 | 171 min | 180 min | 224 min | 251 min | 0.0 % | 15.3 % |
| `08:00Z` | 326 | 154 min | 170 min | 215 min | 287 min | 6.1 % | 27.6 % |
| **`16:00Z`** | 326 | **103 min** | 107 min | 128 min | 197 min | **19.3 %** | **69.0 %** |

Two facts drove the configuration:

1. **16:00 UTC was the least congested slot.** It had the lowest median delay in each of the six months on record, not just overall. `00:00Z` is 20:00 on the US east coast, the platform's busiest window; 16:00Z is midday there.
2. **No run in five months ever started in under 28 minutes.** That is why the previous "only run at 12:00 Europe/Madrid" gate — which woke the workflow twice a day and let it through only inside a ±30 min window — could never succeed: it would have rejected over 98 % of runs and the workflow would never have published anything.

So the cron is a single entry with **no gate**. `workflow_dispatch` still runs the collector immediately, whatever the local time. The workflow logs the real UTC and `Europe/Madrid` start time on every run, and `LiveTV.json` carries that same moment as its `date`, so `index.html` can display an honest "updated N min ago".

The merged [EPG](#epg) has its own workflow, `TV-Spain-EPG.yml`, on `0 8 */2 * *`. Cron has no 48-hour step, so the even days of the month is the closest it comes: the interval is exactly 48 h within a month and shortens to 24 h across the boundary, from the 30th to the 1st. It deliberately does not share a slot with the playlist collector, which rewrites the very files the guide job reads.

### Why the cron sits at 08:00 UTC

The least congested slot is not the same thing as the slot you want. The delay is a queue, not a fixed offset, so it has to be paid on whichever slot you pick: moving the cron 8 h earlier moves the publication 8 h earlier and buys nothing back. Running at `0 8 * * *` instead of `0 16 * * *` therefore costs about 50 min of extra queueing (median 154 min vs 103 min) and returns 8 h of daylight, landing the refreshed lists in the middle of the Spanish afternoon instead of late at night.

Expected publication window in mainland Spain time: roughly **11:30–15:30**, with a median around 12:35.

### Validation record

| Run | Trigger | Started (UTC) | Started (Madrid) | Delay vs 16:00Z | Result |
|---|---|---|---|---|---|
| [#660](https://github.com/pascgallardo/LiveTVCollectorES/actions/runs/36719445370) | `workflow_dispatch` | 2026-09-30 13:07:56 | 15:07:56 | — (manual) | both jobs green, lists committed as `09ebe56` |
| [#661](https://github.com/pascgallardo/LiveTVCollectorES/actions/runs/36772879590) | `schedule` | 2026-09-30 20:28:33 | **22:28:33** | **+4 h 28 min** | both jobs green, lists committed as `d085833` |

#660 confirmed the pipeline works end to end without a gate. #661 was the first programmed run and therefore the first real measurement of the slot: a **268 min delay**, against a historical median of 103 min for 16:00Z and a best-ever of 28 min. That lands at the 98.7th percentile of the 200 most recent scheduled runs, though still below the worst one on record (325 min), so on its own it proves nothing new — it is a single sample, and the slot was moved on the strength of the six-month picture rather than of this run.

From #661 onwards the delay is measured against `08:00Z`, where the historical median was 154 min.

If an exact wall-clock time ever becomes a hard requirement, the fix is to stop relying on `schedule` at all: call the `workflow_dispatch` endpoint from an external scheduler.

## Tests

The suite uses only the standard library (`unittest`), so no extra dependency is needed. It never touches the network: every HTTP call is stubbed, and generated files are written to a temporary directory.

`tests/test_tv_spain.py` covers:

- **M3U parsing** — `#EXTINF` attributes, missing or empty `tvg-logo` (default logo), missing `group-title` (`Uncategorized`), missing name (`Unnamed Channel`), orphan URLs, directive lines such as `#EXTVLCOPT`, consecutive `#EXTINF` entries, and channel dicts not being mutated by the next entry.
- **tvg metadata** (`TestTvgMetadataParsing`, `TestTvgMetadataMerging`, `TestTvgMetadataExports`) — reading `tvg-id` and `tvg-name` regardless of attribute order, values containing spaces and commas, quotes that cannot corrupt a line, filling missing metadata from a later source without ever overwriting existing values, emitting the attributes in the M3U only when present, and a round trip that re-parses an exported playlist.
- **URL deduplication** — repeated URLs within a playlist, across different sources (the first source wins), identical names with different URLs (both kept), and `seen_urls` being reset between runs.
- **Link filtering** — each unique URL probed once even when several channels share it, dead channels dropped, resolved URL replacing the original, and `check_links=False` skipping the probe entirely.
- **Link checking** — success, error status returning `(False, url)` instead of `None`, HEAD to GET fallback, alternate-protocol retry, and the per-URL cache.
- **HTML source extraction** — playlist detection, relative link resolution, and excluded hosts.
- **Exports** — the four output files, `#EXTM3U` structure, and all four formats agreeing on the same channel order.
- **Source order** (`TestSourceOrderIsPreserved`) — a single source keeps its own order, the first source's channels come before the second's, the declared order of the sources is respected, a group keeps the position of its first channel, a second identical run produces the same order, all four exports agree, link verification with `--check-links` does not reshuffle the result (futures completing in reverse still export in source order), and dropped channels do not disturb the rest.
- **Timestamps** (`TestExportTimestamp`) — the published `date` is Madrid local time under both CET and CEST, carries an explicit offset, and parses back to the same instant.
- **M3U EPG header** (`TestM3UEpgHeader`) — each source's `url-tvg` is read from its header line, single and multi-URL values are split and trimmed, sources without EPG contribute nothing, several sources are merged in order, a guide shared by two sources is listed once, the list is cleared between runs, the header stays bare without EPG, the source M3U never leaks into `url-tvg`, and the stream entries still follow the header.
- **`tvg-name` deduplication** (`TestTvgNameDeduplication`) — the key trims, collapses whitespace and ignores case and is `None` without a usable `tvg-name`; channels without metadata are all kept; the first copy wins when its stream answers; the search falls back to the next copy, and to the first one when nothing answers; probing stops at the winner; the resolved URL replaces the winner's; duplicates match across categories and across case and spacing variants; unique channels are never probed; survivors and categories keep their order, an emptied category disappears, all four exports agree, and a `--check-links` run reuses the status cache instead of probing again.

`tests/test_workflow_schedule.py` guards the scheduling configuration: one cron at 08:00 UTC, on the hour, agreeing with the banner the workflow prints and with the hour the README advertises, no leftover gate job, no stale reference to the removed gate script, and a well-formed job chain.

`tests/test_tv_spain_epg.py` guards the [EPG merge](#epg): the tvg-id filter on both channels and programmes, the unescaping that rescues an id like `Crimen&amp;Historia`, deduplication across mirrored guides, the first guide winning ownership, malformed input being skipped rather than fatal, the gzip container carrying no timestamp or filename, and both "do not publish" guards — including that the two of them are reported as the distinct causes they are.

`tests/test_epg_workflow.py` guards the guide workflow: the `0 8 */2 * *` cadence and its documented month-boundary drift, both published files being committed, the playlist being left alone, and the two crons not colliding.

The EPG merge was checked by mutation too: 23 deliberate defects — dropping either half of the tvg-id filter, disabling the normalisation or the unescaping, removing the deduplication, reversing the download order, clearing nested elements, copying elements by reference, stamping the gzip or the document, publishing an empty merge, letting the fallback read its own output, and the manifest and header changes — all fail the suite.

## Dependencies

Declared in `requirements.txt` and installed by the workflow with `pip install -r requirements.txt`:
- `requests`: For fetching M3U and HTML content.
- `beautifulsoup4`: For HTML parsing.

Timezone handling uses the standard library `zoneinfo`, so there is no third-party timezone dependency. The published timestamp is the moment the collector really ran: GitHub's cron cannot be relied on to start a workflow on time, so stamping the scheduled minute would be a lie.

## Troubleshooting

- **Empty Files**: Check the Actions logs for errors:
  - "Error fetching [url]": Source might be down or inaccessible.
  - "No channels parsed": Verify source format (`#EXTINF:` followed by URL).
  - "No channels exported": The workflow logs a warning and the run fails so a broken export is never committed.

- **Permissions Error**: Ensure `permissions: contents: write` is in `TV-Spain.yml`.

- **Index out of date**: The `update-indexes` job runs after the collector and regenerates the `index.json` files. It uses this repository's own reusable workflow (`.github/workflows/update-indexes.yml`), so it is not affected by upstream changes.

- **Logs**: View detailed logs in the "Actions" tab to diagnose issues.

## Contributing

Feel free to:
- Add more sources to `BugsfreeMain/TV-Spain.py`.
- Suggest improvements via issues or pull requests.

## License

This project is open-source and available under the [MIT License](LICENSE) (add a `LICENSE` file if desired).

## Disclaimer

This project is intended solely for educational and research purposes. It aggregates publicly available streaming links from various sources on the internet for convenience and does not host, distribute, or provide any streaming content itself. The maintainers of this repository are not affiliated with the content providers or the streams listed in the exported files.

- **Usage Responsibility**: Users are responsible for ensuring their use of the streaming links complies with local laws and regulations, including copyright and intellectual property rights.
- **No Warranty**: The links provided are sourced from third-party repositories and may become unavailable or change without notice. This project offers no guarantee regarding the availability, quality, or legality of the streams.
- **Content Ownership**: All streaming content belongs to its respective owners, and this project does not claim ownership or endorse any specific content.

By using this repository or its generated files, you acknowledge and agree to these terms.

## Usage Policy
- Personal Use Only: These files are intended for personal, non-commercial use.
- No Redistribution for Profit: Do not redistribute or sell these files for commercial purposes.
- Respect Source Terms: Adhere to the terms of service of the original stream providers.
- Attribution: If you share or use this data, please credit bugsfreeweb/LiveTVCollector.
- Modification: Feel free to modify the files for personal use, but do not misrepresent them as official or endorsed content.

## Donate the project
- DOGE: <b>DEtH2yFUjjUEBUyd3scjs38X7S1Z7ee7zD</b>
- BTC Lightening: <b>bugsfree@speed.app</b>
- SOL: <b>bugsfree.sol</b>
- EVM: <b>bugsfree.bnb</b>
