"""Merge the XMLTV guides of the published playlist into a single guide.

The playlist published by `TV-Spain.py` declares the guide URLs its sources
shipped with. This script downloads each of them, keeps only the channels whose
`tvg-id` the playlist actually carries, and writes the result as both a plain
XMLTV file and its gzipped twin.

Keeping the filter is the whole point. The guides are large and mostly describe
channels nobody in Spain watches: guiatv.xml alone is 33 MB of XMLTV with 644
channels, of which 72 belong to this playlist. Merging everything would publish a
file several times the size of the playlist it has to describe, most of it dead
weight for a player.

Two things make the output stable enough to be committed. Channels and
programmes are deduplicated across guides, because several of these sources are
mirrors of each other and would otherwise repeat the same schedule twice; and the
gzip container is written with a zeroed timestamp, so an unchanged guide
produces a byte-identical file and does not show up as a diff.

Where the source list comes from is circular by design, and deliberately so. The
M3U header now advertises *this* file as its single `url-tvg`, which is what a
player wants, but reading the sources back from there would make the merge feed
on its own output. The collector therefore also writes the list to a sidecar
manifest, and that is what this script reads, with the header as a fallback for a
checkout that predates the manifest.
"""
import argparse
import copy
import gzip
import html
import io
import json
import logging
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# As in the M3U collector: the schedule is best effort, so the published guide
# records the moment it really ran, in mainland Spain time with an explicit
# offset.
MADRID = ZoneInfo("Europe/Madrid")

# Guides come back compressed whether or not the URL says so: guiatv.xml and
# runtime.xml are plain .xml paths that are served gzipped. The magic bytes are
# the only reliable test, so the .gz suffix is deliberately not used.
GZIP_MAGIC = b'\x1f\x8b'

# XMLTV elements this script understands. XMLTV files in the wild occasionally
# carry a namespace, so tags are compared on their local name.
CHANNEL = 'channel'
PROGRAMME = 'programme'

# What this script writes, and therefore must never read.
OUTPUT_XML = "LiveTV.xml"


class EPGMerger:
    def __init__(self, country="Spain", base_dir="LiveTV", timeout=60, workers=4):
        self.output_dir = os.path.join(base_dir, country)
        self.playlist_path = os.path.join(self.output_dir, "LiveTV.m3u")
        self.manifest_path = os.path.join(self.output_dir, "epg-sources.json")
        self.timeout = timeout
        self.workers = workers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    # ------------------------------------------------------------------- inputs

    @staticmethod
    def m3u_attribute(line, name):
        """Return the value of an M3U attribute, or '' when absent or empty."""
        match = re.search(rf'{re.escape(name)}="([^"]*)"', line)
        return match.group(1).strip() if match else ''

    @staticmethod
    def normalise(tvg_id):
        """Return the key used to match a playlist id against a guide channel.

        Trimming and collapsing whitespace is the obvious part. The unescape
        matters too: some source playlists carry `Crimen&amp;Historia` where the
        guide writes `Crimen&Historia`, and without it that channel silently
        loses its schedule. The emitted channel keeps the guide's own id, so this
        only widens the match, it never rewrites the output.
        """
        return ' '.join(html.unescape(tvg_id).split())

    def read_playlist(self):
        """Return (guide urls, tvg ids) exactly as published in LiveTV.m3u."""
        if not os.path.isfile(self.playlist_path):
            raise FileNotFoundError(
                f"{self.playlist_path} is missing; run the M3U collector first")

        epg_urls, tvg_ids = [], set()
        with open(self.playlist_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#EXTM3U'):
                    # Only the first header line carries url-tvg; a later one
                    # would be a stray line in the playlist, not a second list.
                    if not epg_urls:
                        value = self.m3u_attribute(line, 'url-tvg')
                        epg_urls = [u.strip() for u in value.split(',') if u.strip()]
                elif line.startswith('#EXTINF'):
                    tvg_id = self.m3u_attribute(line, 'tvg-id')
                    if tvg_id:
                        tvg_ids.add(self.normalise(tvg_id))
        return epg_urls, tvg_ids

    def read_manifest(self):
        """Return the guide list the collector recorded, or None when unusable.

        The manifest only exists to break the circularity described in the module
        docstring. It is not a second source of truth: the header and the
        manifest are written from the same list in the same run.
        """
        if not os.path.isfile(self.manifest_path):
            return None
        try:
            with open(self.manifest_path, encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logging.warning(f"Ignoring unreadable manifest {self.manifest_path}: {exc}")
            return None
        urls = data.get("epg_urls") if isinstance(data, dict) else None
        if not isinstance(urls, list):
            logging.warning(
                f"Ignoring manifest without an epg_urls list: {self.manifest_path}")
            return None
        return [u.strip() for u in urls if isinstance(u, str) and u.strip()]

    def is_own_output(self, url):
        """Whether *url* points at the file this script writes.

        The playlist header advertises the merged guide, so the fallback path
        would otherwise hand the merger its own output as an input and it would
        happily merge that into itself. The name is compared rather than the full
        URL so the guard survives the repository or the country being renamed.
        """
        name = url.rsplit('/', 1)[-1].split('?', 1)[0]
        return name in {OUTPUT_XML, OUTPUT_XML + '.gz'}

    def source_urls(self, header_urls):
        """Return the guides to merge, preferring the manifest over the header."""
        manifest = self.read_manifest()
        if manifest:
            logging.info(f"Guide list read from {os.path.basename(self.manifest_path)}")
            return manifest
        logging.warning(
            f"{os.path.basename(self.manifest_path)} is missing, falling back to the "
            "url-tvg header of the playlist")
        sources = [url for url in header_urls if not self.is_own_output(url)]
        dropped = len(header_urls) - len(sources)
        if dropped:
            logging.info(f"Ignored {dropped} entry pointing at this merger's own output")
        return sources

    # ------------------------------------------------------------------ fetching

    def fetch_guide(self, url):
        """Download one guide and return its decompressed XML bytes, or None.

        `requests` transparently decodes a `Content-Encoding: gzip` response,
        but a `.gz` file served as a plain attachment keeps its magic bytes, so
        both cases are covered. A guide that cannot be fetched is not fatal: the
        others still merge and the run reports what was lost.
        """
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.headers)
            response.raise_for_status()
            data = response.content
        except requests.RequestException as exc:
            logging.warning(f"Failed to fetch {url}: {exc}")
            return None
        if data[:2] == GZIP_MAGIC:
            try:
                data = gzip.decompress(data)
            except OSError as exc:
                logging.warning(f"Failed to decompress {url}: {exc}")
                return None
        if not data.strip():
            logging.warning(f"Guide at {url} is empty")
            return None
        return data

    def fetch_guides(self, urls):
        """Fetch every guide in parallel and return them in the declared order.

        `executor.map` yields in input order, which is what keeps the merge
        deterministic: the first guide to declare a channel owns it, so a
        download that happens to finish early must not be able to win.
        """
        with ThreadPoolExecutor(max_workers=max(1, self.workers)) as executor:
            fetched = executor.map(self.fetch_guide, urls)
            return [data for data in fetched if data is not None]

    # ------------------------------------------------------------------- merging

    @staticmethod
    def local_name(tag):
        """Return an element's tag without its XML namespace, if it has one."""
        return tag.rpartition('}')[2]

    def merge(self, guides, wanted):
        """Return (channels, programmes) restricted to *wanted*.

        Guides overlap: guiatv.xml and the s2l workers mirror each other and the
        national channels, so the same programme arrives more than once. A
        channel is emitted by the first guide that declares it, and a programme
        by the first guide that lists it, keyed on channel plus start and stop.
        Guides covering different time ranges therefore all contribute, while
        guides repeating the same range do not.

        Elements are pulled with `iterparse` and the top-level ones are cleared as
        they go, only the survivors being copied first. Building the tree and
        filtering afterwards would hold several guides at once, which at tens of
        megabytes each is the difference between a comfortable and an exhausted
        runner.

        Only the direct children of `<tv>` may be cleared, which the depth counter
        below identifies. `iterparse` emits the `end` event of a child before the
        one of its parent, so clearing every element would wipe the `<title>` and
        `<desc>` of each programme before the programme itself was ever seen, and
        the merged guide would publish thousands of entries with nothing in them.
        """
        channels, programmes = [], []
        seen_channels, seen_programmes = set(), set()

        for guide in guides:
            source = io.BytesIO(guide)
            depth = 0
            try:
                for event, element in ET.iterparse(source, events=('start', 'end')):
                    if event == 'start':
                        depth += 1
                        continue
                    depth -= 1
                    if depth == 0:
                        # The root, now that its children have been taken.
                        element.clear()
                        continue
                    if depth != 1:
                        continue  # a nested title, desc or icon: left alone

                    tag = self.local_name(element.tag)
                    if tag == CHANNEL:
                        channel_id = (element.get('id') or '').strip()
                        if channel_id in wanted and channel_id not in seen_channels:
                            seen_channels.add(channel_id)
                            channels.append(copy.deepcopy(element))
                    elif tag == PROGRAMME:
                        channel_id = (element.get('channel') or '').strip()
                        if channel_id not in wanted:
                            continue
                        key = (channel_id, element.get('start'), element.get('stop'))
                        if key not in seen_programmes:
                            seen_programmes.add(key)
                            programmes.append(copy.deepcopy(element))
                    # Cleared whether kept or not; the kept ones were copied.
                    element.clear()
            except ET.ParseError as exc:
                logging.warning(f"Skipping the rest of a malformed guide: {exc}")

        return channels, programmes

    def build_document(self, channels, programmes):
        """Wrap the kept elements in a fresh `<tv>` root.

        The sources' own generator attributes are dropped rather than copied,
        since they would claim an upstream tool produced this file, and no
        timestamp is added: the publication instant is already in the git commit
        and in LiveTV.json, and stamping the file here would make two runs over
        the same guides produce different bytes for no reason.
        """
        root = ET.Element('tv', {
            'generator-info-name': 'LiveTVCollectorES EPG merger',
            'generator-info-url': 'https://github.com/pascgallardo/LiveTV-EPG_Collector_ES',
        })
        for element in channels:
            root.append(element)
        for element in programmes:
            root.append(element)
        return root

    # ------------------------------------------------------------------- writing

    def write(self, root, xml_name=OUTPUT_XML):
        """Write the plain guide and its gzipped twin, returning both paths.

        The gzip stream is written with mtime 0, and the archive gets no stored
        name, so the `.gz` is a pure function of the XML next to it. Both would
        otherwise vary between two runs over identical data and fill the history
        with diffs that carry no information.
        """
        xml_path = os.path.join(self.output_dir, xml_name)
        gz_path = xml_path + '.gz'

        ET.ElementTree(root).write(xml_path, encoding='utf-8', xml_declaration=True)
        with open(xml_path, 'rb') as src, open(gz_path, 'wb') as dst:
            with gzip.GzipFile(filename='', mode='wb', fileobj=dst, mtime=0) as gz:
                shutil.copyfileobj(src, gz)

        for path in (xml_path, gz_path):
            logging.info(f"Wrote {path} ({os.path.getsize(path) / 1e6:.2f} MB)")
        return xml_path, gz_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Merge the playlist's XMLTV guides.")
    parser.add_argument('--timeout', type=int, default=60,
                        help='seconds to wait for each guide (default: 60)')
    parser.add_argument('--workers', type=int, default=4,
                        help='guides downloaded in parallel (default: 4)')
    args = parser.parse_args(argv)

    merger = EPGMerger(timeout=args.timeout, workers=args.workers)

    try:
        header_urls, wanted = merger.read_playlist()
    except FileNotFoundError as exc:
        logging.error(str(exc))
        return 1

    logging.info(f"{len(wanted)} distinct tvg-id in the playlist")
    urls = merger.source_urls(header_urls)
    if not urls:
        logging.error("No EPG guides to merge: the playlist declares none")
        return 1

    logging.info(f"Merging {len(urls)} guides")
    guides = merger.fetch_guides(urls)
    logging.info(f"Fetched {len(guides)}/{len(urls)} guides, "
                 f"{sum(len(g) for g in guides) / 1e6:.1f} MB of XML")
    if not guides:
        logging.error("Every guide failed to download; the published guide is left untouched")
        return 1

    channels, programmes = merger.merge(guides, wanted)
    logging.info(f"Channels kept: {len(channels)}/{len(wanted)} "
                 f"({100 * len(channels) / len(wanted):.1f}% of the playlist)")
    logging.info(f"Programmes kept: {len(programmes)}")

    # An empty merge means every filter rejected everything, which is a bug or a
    # playlist that changed shape rather than a normal run. Publishing it would
    # replace a good guide with an empty one, so the run fails instead.
    if not channels:
        logging.error("No channel of the playlist was found in any guide; nothing written")
        return 1

    merger.write(merger.build_document(channels, programmes))
    logging.info(f"Guide published at {datetime.now(MADRID).isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
