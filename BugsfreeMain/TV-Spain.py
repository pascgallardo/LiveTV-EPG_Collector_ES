import requests
import json
import os
import re
import sys
from urllib.parse import urlparse
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import concurrent.futures
import threading
import logging
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# GitHub's `schedule` is best effort, so the collector cannot run at a fixed
# wall-clock moment. The published timestamp is therefore the instant it really
# ran, expressed in mainland Spain time. It is written as ISO 8601 with an
# explicit UTC offset, which is unambiguous: the browser does not have to guess
# the visitor's timezone when index.html parses it with `new Date(...)`.
MADRID = ZoneInfo("Europe/Madrid")

# The single guide `TV-Spain-EPG.py` merges every source guide into, published by
# this repository. It is what `url-tvg` advertises, because pointing a player at
# nine scattered sources instead of one complete guide is worse for it, and the
# merged file is already restricted to the channels below.
MERGED_EPG_URL = (
    "https://raw.githubusercontent.com/pascgallardo/LiveTVCollectorES/"
    "refs/heads/main/LiveTV/Spain/LiveTV.xml.gz"
)

class M3UCollector:
    def __init__(self, country="Spain", base_dir="LiveTV", check_links=True):
        self.channels = defaultdict(list)
        self.default_logo = "https://buddytv.netlify.app/img/no-logo.png"
        self.seen_urls = set()
        self.channel_by_url = {}
        self.url_status_cache = {}
        # EPG (XMLTV) URLs declared by the merged sources, in the order they were
        # seen. Not published in the playlist: `TV-Spain-EPG.py` merges them into
        # one guide and that is what url-tvg points at, so the list is exported to
        # a sidecar manifest instead.
        self.epg_urls = []
        self.output_dir = os.path.join(base_dir, country)
        self.lock = threading.Lock()
        self.check_links = check_links  # Toggle link checking
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_content(self, url):
        """Fetch content (M3U or HTML) with streaming.

        The joined text is only built for HTML sources, which need it for parsing; M3U sources
        are consumed line by line so a large playlist is not held in memory twice.
        """
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

        try:
            with requests.get(url, stream=True, headers=headers, timeout=10) as response:
                response.raise_for_status()
                lines = [line.decode('utf-8', errors='ignore') if isinstance(line, bytes) else line for line in response.iter_lines()]
                if not lines:
                    logging.warning(f"No content fetched from {url}")
                else:
                    logging.info(f"Fetched {len(lines)} lines from {url}")
                content = '\n'.join(lines) if url.endswith('.html') else None
                return content, lines
        except requests.RequestException as e:
            logging.error(f"Failed to fetch {url}: {str(e)}")
            return None, []

    def extract_stream_urls_from_html(self, html_content, base_url):
        """Extract streaming URLs from HTML."""
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        stream_urls = set()
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            parsed_base = urlparse(base_url)
            parsed_href = urlparse(href)
            if not parsed_href.scheme:
                href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
            
            if (href.endswith(('.m3u', '.m3u8')) or 
                re.match(r'^https?://.*\.(ts|mp4|avi|mkv|flv|wmv)$', href) or 
                'playlist' in href.lower() or 'stream' in href.lower()):
                if not any(exclude in href.lower() for exclude in ['telegram', '.html', '.php', 'github.com', 'login', 'signup']):
                    stream_urls.add(href)
        
        logging.info(f"Extracted {len(stream_urls)} streaming URLs from {base_url}")
        return list(stream_urls)

    def check_link_active(self, url, timeout=2):
        """Check if a link is active, optimized for speed. Always returns (bool, url)."""
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

        with self.lock:
            if url in self.url_status_cache:
                return self.url_status_cache[url]

        # Try original URL
        try:
            response = requests.head(url, timeout=timeout, headers=headers, allow_redirects=True)
            if response.status_code < 400:
                logging.info(f"Checked {url}: Active (HEAD)")
                with self.lock:
                    self.url_status_cache[url] = (True, url)
                return True, url
        except requests.RequestException:
            # Only try GET if HEAD fails, skip alternate protocol for speed
            try:
                with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
                    if r.status_code < 400:
                        logging.info(f"Checked {url}: Active (GET)")
                        with self.lock:
                            self.url_status_cache[url] = (True, url)
                        return True, url
            except requests.RequestException as e:
                logging.warning(f"Link check failed for {url}: {e}")
                # Try alternate protocol only if not a timeout
                if not isinstance(e, requests.Timeout):
                    alt_url = url.replace('http://', 'https://') if url.startswith('http://') else url.replace('https://', 'http://')
                    try:
                        response = requests.head(alt_url, timeout=timeout, headers=headers, allow_redirects=True)
                        if response.status_code < 400:
                            logging.info(f"Checked {alt_url}: Active (HEAD, switched protocol)")
                            with self.lock:
                                self.url_status_cache[url] = (True, alt_url)
                            return True, alt_url
                    except requests.RequestException:
                        pass

        # HEAD succeeded but reported an error status, or every attempt failed.
        with self.lock:
            self.url_status_cache[url] = (False, url)
        return False, url

    @staticmethod
    def epg_urls_from_header(lines):
        """Return the EPG URLs a playlist declares in its `#EXTM3U url-tvg` attribute.

        `url-tvg` holds a comma separated list, so every entry is extracted and
        trimmed. A source without the attribute, or with an empty one, simply
        contributes nothing.
        """
        for line in lines or []:
            if line.startswith('#EXTM3U'):
                value = M3UCollector.extinf_attribute(line, 'url-tvg')
                return [url.strip() for url in value.split(',') if url.strip()]
        return []

    @staticmethod
    def extinf_attribute(line, name):
        """Return the value of an `#EXTINF` attribute, or '' when absent or empty."""
        match = re.search(rf'{re.escape(name)}="([^"]*)"', line)
        return match.group(1).strip() if match else ''

    @staticmethod
    def merge_metadata(existing, candidate):
        """Complete an already stored channel with metadata from another source.

        The first source that provides a URL wins, but a later playlist may still
        carry the tvg-id or tvg-name that the first one was missing, so those fields
        are filled in whenever the stored channel does not have them yet.
        """
        for field in ('tvg_id', 'tvg_name'):
            if not existing.get(field) and candidate.get(field):
                existing[field] = candidate[field]

    def parse_and_store(self, lines, source_url):
        """Parse M3U lines and store channels."""
        current_channel = {}
        channel_count = 0
        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                logo = self.extinf_attribute(line, 'tvg-logo') or self.default_logo
                group = self.extinf_attribute(line, 'group-title') or "Uncategorized"
                tvg_id = self.extinf_attribute(line, 'tvg-id')
                tvg_name = self.extinf_attribute(line, 'tvg-name')

                match = re.search(r',(.+)$', line)
                name = match.group(1).strip() if match else "Unnamed Channel"

                current_channel = {
                    'name': name,
                    'tvg_id': tvg_id,
                    'tvg_name': tvg_name,
                    'logo': logo,
                    'group': group,
                    'source': source_url
                }
            elif line.startswith('http') and current_channel:
                with self.lock:
                    existing = self.channel_by_url.get(line)
                    if existing is not None:
                        self.merge_metadata(existing, current_channel)
                    else:
                        self.seen_urls.add(line)
                        current_channel['url'] = line
                        self.channel_by_url[line] = current_channel
                        self.channels[current_channel['group']].append(current_channel)
                        channel_count += 1
                current_channel = {}
        logging.info(f"Parsed {channel_count} channels from {source_url}")

    def filter_active_channels(self):
        """Filter out inactive channels, skippable for speed."""
        if not self.check_links:
            logging.info("Skipping link activity check for speed")
            return

        active_channels = defaultdict(list)
        all_channels = [(group, ch) for group, chans in self.channels.items() for ch in chans]
        checked_urls = set()

        logging.info(f"Total channels to check: {len(all_channels)}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_channel = {}
            for group, channel in all_channels:
                url = channel.get('url')
                if not url or url in checked_urls:
                    continue
                checked_urls.add(url)
                future_to_channel[executor.submit(self.check_link_active, url)] = (group, channel)
            logging.info(f"Unique URLs to check: {len(future_to_channel)}")
            # Collect the results first, then re-apply them in source order:
            # as_completed yields in completion order, which would reshuffle the
            # playlist and make the export differ between runs.
            is_active_by_url = {}
            for future in concurrent.futures.as_completed(future_to_channel):
                group, channel = future_to_channel[future]
                url = channel.get('url')
                try:
                    is_active, updated_url = future.result()
                    is_active_by_url[url] = (is_active, updated_url)
                except Exception as e:
                    logging.error(f"Error checking {url}: {e}")
                    is_active_by_url[url] = (False, url)

            for group, channels in self.channels.items():
                for channel in channels:
                    outcome = is_active_by_url.get(channel.get('url'))
                    if not outcome:
                        continue
                    is_active, updated_url = outcome
                    if is_active:
                        channel['url'] = updated_url
                        active_channels[group].append(channel)

        self.channels = active_channels
        logging.info(f"Active channels after filtering: {sum(len(ch) for ch in active_channels.values())}")

    @staticmethod
    def duplicate_key(channel):
        """Return the normalised tvg-name that identifies a channel, or None.

        Sources spell the same channel in several ways ("La 1", "la 1  ",
        "LA 1"), so the key trims the value, collapses internal whitespace and
        ignores case. A channel with no tvg-name returns None and is never
        compared with anything: without metadata to match on, every such channel
        is treated as distinct instead of collapsing into one giant group.
        """
        name = (channel.get('tvg_name') or '').strip()
        if not name:
            return None
        return ' '.join(name.split()).casefold()

    def _first_working(self, candidates):
        """Return (channel, url) of the first candidate whose stream answers.

        Candidates are probed in playlist order and the search stops at the first
        one that responds, so a group is never probed further than it needs to be.
        If nothing answers, the first candidate is returned anyway: a probe that
        fails because of a network blip must not make a channel disappear from
        the published playlist.
        """
        fallback = None
        for channel in candidates:
            if fallback is None:
                fallback = (channel, channel.get('url'))
            url = channel.get('url')
            if not url:
                continue
            is_active, updated_url = self.check_link_active(url)
            if is_active:
                return channel, updated_url
        return fallback

    def dedupe_by_tvg_name(self):
        """Keep a single entry per tvg-name in the merged playlist.

        Duplicates are matched on the tvg-name metadata across the whole merged
        playlist, not per category, and the winner is the earliest entry in
        playlist order whose stream actually answers. The remaining copies are
        dropped. Groups keep the position of their first surviving channel and
        the survivors keep their own order, so nothing is reshuffled.

        Each group of duplicates is resolved independently and in parallel, and
        every probe goes through `check_link_active`, whose cache means a run
        with --check-links already knows the answer and pays nothing here.
        """
        candidates = defaultdict(list)
        for channels in self.channels.values():
            for channel in channels:
                key = self.duplicate_key(channel)
                if key is not None:
                    candidates[key].append(channel)

        duplicated = {key: members for key, members in candidates.items() if len(members) > 1}
        if not duplicated:
            logging.info("No duplicate tvg-name found, nothing to deduplicate")
            return

        logging.info(f"Duplicate tvg-name groups: {len(duplicated)} "
                     f"({sum(len(m) for m in duplicated.values())} channels)")
        winners = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_key = {
                executor.submit(self._first_working, members): key
                for key, members in duplicated.items()
            }
            for future in concurrent.futures.as_completed(future_to_key):
                winners[future_to_key[future]] = future.result()

        kept = defaultdict(list)
        dropped = 0
        for group, channels in self.channels.items():
            for channel in channels:
                key = self.duplicate_key(channel)
                if key is not None and key in winners:
                    winner, resolved_url = winners[key]
                    if channel is not winner:
                        dropped += 1
                        continue
                    if resolved_url:
                        channel['url'] = resolved_url
                kept[group].append(channel)
        self.channels = kept

        total = sum(len(ch) for ch in kept.values())
        logging.info(f"Kept the first working stream of every duplicate: "
                     f"{total} channels in {len(kept)} groups ({dropped} duplicates removed)")

    def process_sources(self, source_urls):
        """Process sources sequentially for better control."""
        self.channels.clear()
        self.seen_urls.clear()
        self.channel_by_url.clear()
        self.url_status_cache.clear()
        self.epg_urls.clear()

        all_m3u_urls = set()
        for url in source_urls:
            html_content, lines = self.fetch_content(url)
            if url.endswith('.html'):
                m3u_urls = self.extract_stream_urls_from_html(html_content, url)
                all_m3u_urls.update(m3u_urls)
            else:
                self.epg_urls.extend(self.epg_urls_from_header(lines))
                self.parse_and_store(lines, url)

        for m3u_url in sorted(all_m3u_urls):
            _, lines = self.fetch_content(m3u_url)
            self.epg_urls.extend(self.epg_urls_from_header(lines))
            self.parse_and_store(lines, m3u_url)

        if self.channels:
            self.filter_active_channels()
            self.dedupe_by_tvg_name()
        else:
            logging.warning("No channels parsed from sources")

    def grouped_channels(self):
        """Yield each group with its channels in the order the sources provided them.

        Nothing is sorted here: a channel keeps the position it had in its
        source playlist, and a group keeps the position of its first appearance,
        so the merged file reads like the playlists it was built from. The order
        is still fully deterministic because the sources are consumed in a fixed
        sequence, which is what keeps re-runs free of spurious commits.
        """
        for group, channels in self.channels.items():
            yield group, channels

    @staticmethod
    def extinf_line(group, channel):
        """Build an `#EXTINF` line, omitting the tvg-* attributes the source did not provide."""
        attributes = []
        for name, value in (
            ('tvg-id', channel.get('tvg_id')),
            ('tvg-name', channel.get('tvg_name')),
            ('tvg-logo', channel.get('logo')),
            ('group-title', group),
        ):
            if value:
                attributes.append(f'{name}="{value}"')
        return f'#EXTINF:-1 {" ".join(attributes)},{channel["name"]}'

    def unique_epg_urls(self):
        """The guides of every merged source, in order and without duplicates."""
        seen = set()
        return [url for url in self.epg_urls if not (url in seen or seen.add(url))]

    def m3u_header(self):
        """The `#EXTM3U` line, pointing players at the merged XMLTV guide.

        `url-tvg` advertises the single guide that `TV-Spain-EPG.py` builds out
        of every source guide, not the sources themselves: a player is better
        served by one file that already contains every channel below than by nine
        scattered ones it has to merge and filter on its own.

        The list of sources that went into that merge is written separately, to
        the manifest, because it can no longer be recovered from here. With no
        EPG at all the line stays bare, which keeps the output valid.
        """
        if not self.epg_urls:
            return '#EXTM3U'
        return f'#EXTM3U url-tvg="{MERGED_EPG_URL}"'

    def export_epg_manifest(self, filename="epg-sources.json"):
        """Record the source guides the merged guide is built from.

        This is what lets `TV-Spain-EPG.py` find its inputs: the playlist header
        points at the merge output, so a merger that read the header would be
        merging its own file into itself. Written in source order, because the
        first guide to declare a channel owns it and that choice has to survive
        until the next run.
        """
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({"epg_urls": self.unique_epg_urls()}, f, ensure_ascii=False, indent=2)
            f.write('\n')
        logging.info(f"Exported EPG manifest to {filepath}")
        return filepath

    def export_m3u(self, filename="LiveTV.m3u"):
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.m3u_header() + '\n')
            for group, channels in self.grouped_channels():
                for channel in channels:
                    f.write(self.extinf_line(group, channel) + '\n')
                    f.write(f'{channel["url"]}\n')
        logging.info(f"Exported M3U to {filepath}")
        return filepath

    def export_txt(self, filename="LiveTV.txt"):
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            for group, channels in self.grouped_channels():
                f.write(f"Group: {group}\n")
                for channel in channels:
                    f.write(f"Name: {channel['name']}\n")
                    if channel.get('tvg_id'):
                        f.write(f"TvgID: {channel['tvg_id']}\n")
                    if channel.get('tvg_name'):
                        f.write(f"TvgName: {channel['tvg_name']}\n")
                    f.write(f"URL: {channel['url']}\n")
                    f.write(f"Logo: {channel['logo']}\n")
                    f.write(f"Source: {channel['source']}\n")
                    f.write("-" * 50 + "\n")
                f.write("\n")
        logging.info(f"Exported TXT to {filepath}")
        return filepath

    def export_json(self, filename="LiveTV.json"):
        filepath = os.path.join(self.output_dir, filename)
        current_time = datetime.now(MADRID).isoformat(timespec='seconds')

        json_data = {
            "date": current_time,
            "channels": {group: channels for group, channels in self.grouped_channels()}
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        logging.info(f"Exported JSON to {filepath}")
        return filepath

    def export_custom(self, filename="LiveTV"):
        """Export to custom format without extension."""
        filepath = os.path.join(self.output_dir, filename)
        custom_data = []

        for group, channels in self.grouped_channels():
            for channel in channels:
                custom_data.append({
                    "name": channel['name'],
                    "tvg_id": channel.get('tvg_id', ''),
                    "tvg_name": channel.get('tvg_name', ''),
                    "type": group,
                    "url": channel['url'],
                    "img": channel['logo']
                })

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(custom_data, f, ensure_ascii=False, indent=2)
        logging.info(f"Exported custom format to {filepath}")
        return filepath

def main(check_links=False):
    # M3U sources. An entry ending in .html is scanned for nested playlist links.
    source_urls = [
        "https://m3u.work/OI0Q3l.m3u",
        "https://m3u.work/YawDD3.m3u",
        "https://m3u.work/ICEQGPH.m3u",
        "https://m3u.work/hJiHE3ad.m3u",
        "https://m3u.work/qKChzP8.m3u"
    ]

    collector = M3UCollector(country="Spain", check_links=check_links)
    collector.process_sources(source_urls)

    # Export files
    collector.export_m3u("LiveTV.m3u")
    collector.export_txt("LiveTV.txt")
    collector.export_json("LiveTV.json")
    collector.export_custom("LiveTV")
    collector.export_epg_manifest()

    total_channels = sum(len(ch) for ch in collector.channels.values())
    logging.info(f"[{datetime.now(MADRID)}] Collected {total_channels} unique channel for Spain")
    logging.info(f"Groups found: {len(collector.channels)}")
    if not total_channels:
        logging.warning("No channels exported — sources may be unreachable or empty.")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(check_links="--check-links" in sys.argv[1:]))
