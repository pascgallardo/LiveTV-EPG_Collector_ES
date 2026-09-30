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

- **Automated Updates**: Runs once a day at **12:00 mainland Spain time** via GitHub Actions. Because GitHub cron expressions are always interpreted in UTC and ignore daylight saving, the workflow is woken at both candidate hours (10:00 and 11:00 UTC) and a `gate` job checks `Europe/Madrid` with `zoneinfo` so only the correct one runs — `11:00 UTC` in winter (CET) and `10:00 UTC` in summer (CEST).
- **Large Source Handling**: Streams M3U responses line by line instead of loading whole files, and only materialises the joined text for HTML sources that need parsing.
- **Optional Active Link Verification**: Off by default for speed. Run `python BugsfreeMain/TV-Spain.py --check-links` to probe every stream with 10 concurrent workers (HEAD, falling back to GET and then to the alternate protocol). Results are cached per URL.
- **Duplicate Removal**: Ensures no duplicate streams (based on URL) are included. When the same URL arrives from several playlists, the first source keeps ownership, but a `tvg-id` or `tvg-name` that the first one lacked is filled in from a later source.
- **tvg-* Metadata**: `tvg-id` and `tvg-name` are read from the source `#EXTINF` lines and carried through to every export format. Attributes a source does not provide are simply omitted from the generated `#EXTINF` line.
- **HTML Source Parsing**: A source ending in `.html` is scanned for nested playlist links, filtering out non-stream links (e.g., Telegram, GitHub).
- **Traceable Merges**: The generated `LiveTV.m3u` lists every M3U that was merged into it in the `#EXTM3U url-tvg` header, in consumption order and without duplicates.
- **Deterministic Exports**: Groups and channels are sorted, so re-running without source changes produces identical files and no spurious commits.
- **Honest Timestamps**: The `date` field in `LiveTV.json` is the collector's own run time in `Europe/Madrid`, written as ISO 8601 with an explicit UTC offset (e.g. `2025-03-25T12:00:00+01:00`). The offset matters: it lets the browser resolve the instant correctly whatever timezone the visitor is in, so the "updated N min ago" banner in `index.html` is accurate.
- **Web Hub (`index.html`)**: Static browser UI to browse the generated playlists, search channels, copy/download links, and track download statistics locally.
- **Multiple Export Formats**:
  - `LiveTV.m3u`: Standard M3U playlist.
  - `LiveTV.txt`: Human-readable text format with detailed channel info.
  - `LiveTV.json`: Structured JSON with channel metadata.
  - `LiveTV`: Custom JSON format without extension, designed for easy integration.

## Exported File Formats

### `LiveTV.m3u`
Standard M3U playlist format. The `#EXTM3U` line carries every merged source in `url-tvg`, so the generated playlist documents which playlists it was built from:
```
#EXTM3U url-tvg="https://m3u.work/OI0Q3l.m3u, https://m3u.work/YawDD3.m3u, https://m3u.work/ICEQGPH.m3u"
#EXTINF:-1 tvg-id="AdventureTV.us" tvg-name="Adventure TV" tvg-logo="https://i.imgur.com/VQVr4Nk.png" group-title="Entertainment",Adventure TV
http://109.233.89.170/Adventure_HD/index.m3u8
```

The URLs are listed in the order they were consumed (playlists found inside an `.html` source are appended after the declared ones) and a source is never repeated. When no source is merged the line stays bare, as `#EXTM3U`.

`url-tvg` conventionally points at XMLTV EPG files rather than at M3U playlists, so players that expect EPG data there will not find any. It is published as traceability metadata, not as a working EPG pointer.

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
  "date": "2025-03-25T12:00:00+01:00",
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
   - The workflow "TV-Spain Update Files" runs daily at 12:00 Spain time or can be triggered manually (a manual run always executes, whatever the local time is).

## How It Works

1. **Source Fetching**:
   - Streams M3U files and parses HTML for streaming URLs.
   - Uses `requests` with streaming to handle large files.

2. **Processing**:
   - Removes duplicates based on stream URLs.
   - Optionally verifies link activity with concurrent HEAD/GET requests (2-second timeout, 10 workers) when `--check-links` is passed.

3. **Exporting**:
   - Saves unique channels to four files in `LiveTV/Country Name/`, sorted for stable diffs.

4. **Automation**:
   - GitHub Actions runs `BugsfreeMain/TV-Spain.py` once a day at 12:00 Europe/Madrid, honouring CET and CEST.
   - A second job regenerates `LiveTV/index.json` and `Movies/index.json` from the directories present.
   - Commits and pushes changes automatically using `GITHUB_TOKEN`.

## Local usage

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .       # run the test suite
python BugsfreeMain/TV-Spain.py                # fast: no link verification
python BugsfreeMain/TV-Spain.py --check-links # slower: drop unreachable streams
python generate_indexes.py                     # refresh section indexes
python scripts/madrid_noon_gate.py             # exit 0 only at 12:00 Europe/Madrid
```

`index.html` is a static page: serve the repository root over any static host and it reads the generated files from the raw GitHub URL (this repository first, the upstream repository as fallback).

## Tests

The suite uses only the standard library (`unittest`), so no extra dependency is needed. It never touches the network: every HTTP call is stubbed, and generated files are written to a temporary directory.

`tests/test_tv_spain.py` covers:

- **M3U parsing** — `#EXTINF` attributes, missing or empty `tvg-logo` (default logo), missing `group-title` (`Uncategorized`), missing name (`Unnamed Channel`), orphan URLs, directive lines such as `#EXTVLCOPT`, consecutive `#EXTINF` entries, and channel dicts not being mutated by the next entry.
- **tvg metadata** (`TestTvgMetadataParsing`, `TestTvgMetadataMerging`, `TestTvgMetadataExports`) — reading `tvg-id` and `tvg-name` regardless of attribute order, values containing spaces and commas, quotes that cannot corrupt a line, filling missing metadata from a later source without ever overwriting existing values, emitting the attributes in the M3U only when present, and a round trip that re-parses an exported playlist.
- **URL deduplication** — repeated URLs within a playlist, across different sources (the first source wins), identical names with different URLs (both kept), and `seen_urls` being reset between runs.
- **Link filtering** — each unique URL probed once even when several channels share it, dead channels dropped, resolved URL replacing the original, and `check_links=False` skipping the probe entirely.
- **Link checking** — success, error status returning `(False, url)` instead of `None`, HEAD to GET fallback, alternate-protocol retry, and the per-URL cache.
- **HTML source extraction** — playlist detection, relative link resolution, and excluded hosts.
- **Exports** — the four output files, `#EXTM3U` structure, and identical deterministic ordering across all formats.
- **Timestamps** (`TestExportTimestamp`) — the published `date` is Madrid local time under both CET and CEST, carries an explicit offset, and parses back to the same instant.
- **M3U header** (`TestM3UHeaderSources`) — the merged sources appear in the `#EXTM3U url-tvg` attribute in declared order, duplicates are dropped, playlists discovered inside an HTML source are recorded, the list is cleared between runs, the header stays bare without sources, and the stream entries still follow it.
- **Scheduling gate** (`tests/test_madrid_noon_gate.py`) — `Europe/Madrid` noon detection under CET and CEST, both daylight saving switch days, late-start tolerance, and a sweep of two full years asserting that exactly one of the two candidate hours fires on every single day.

## Dependencies

Declared in `requirements.txt` and installed by the workflow with `pip install -r requirements.txt`:
- `requests`: For fetching M3U and HTML content.
- `beautifulsoup4`: For HTML parsing.

Timezone handling uses the standard library `zoneinfo`, so there is no third-party timezone dependency.

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
