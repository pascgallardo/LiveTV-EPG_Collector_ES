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

class M3UCollector:
    def __init__(self, country="Spain", base_dir="LiveTV", check_links=True):
        self.channels = defaultdict(list)
        self.default_logo = "https://buddytv.netlify.app/img/no-logo.png"
        self.seen_urls = set()
        self.channel_by_url = {}
        self.url_status_cache = {}
        # EPG (XMLTV) URLs declared by the merged sources, in the order they were
        # seen. Published in the #EXTM3U url-tvg header so the generated playlist
        # keeps the guide data its sources shipped with.
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

    def m3u_header(self):
        """The `#EXTM3U` line, carrying the EPG URLs of every merged source.

        `url-tvg` is the conventional place to point players at the XMLTV guide,
        so it only ever holds EPG URLs — never the M3U sources themselves. The
        list keeps the order in which the sources were merged and drops
        duplicates, since several sources commonly share the same guide. With no
        EPG at all the line stays bare, which keeps the output valid.
        """
        seen = set()
        epg = [url for url in self.epg_urls if not (url in seen or seen.add(url))]
        if not epg:
            return '#EXTM3U'
        return f'#EXTM3U url-tvg="{", ".join(epg)}"'

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

    total_channels = sum(len(ch) for ch in collector.channels.values())
    logging.info(f"[{datetime.now(MADRID)}] Collected {total_channels} unique channel for Spain")
    logging.info(f"Groups found: {len(collector.channels)}")
    if not total_channels:
        logging.warning("No channels exported — sources may be unreachable or empty.")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(check_links="--check-links" in sys.argv[1:]))
