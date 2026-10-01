"""Tests for the M3U parsing, URL deduplication and export logic in TV-Spain.py.

The collector module is loaded by path because its filename is not a valid
Python identifier. No test performs network I/O: every request is stubbed.

Run with:
    python -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "BugsfreeMain" / "TV-Spain.py"

EXTINF = '#EXTINF:-1 tvg-logo="{logo}" group-title="{group}",{name}'
EXTINF_FULL = (
    '#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" '
    'tvg-logo="{logo}" group-title="{group}",{name}'
)


def load_collector_module():
    """Import TV-Spain.py, whose filename cannot be used as a module name."""
    spec = importlib.util.spec_from_file_location("tv_spain", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tv = load_collector_module()


def extinf_line(logo="https://logos.example/la1.png", group="Generalistas", name="La 1"):
    return EXTINF.format(logo=logo, group=group, name=name)


def full_extinf_line(tvg_id="La1.es", tvg_name="La 1",
                     logo="https://logos.example/la1.png", group="Generalistas", name="La 1"):
    return EXTINF_FULL.format(tvg_id=tvg_id, tvg_name=tvg_name, logo=logo, group=group, name=name)


class CollectorTestCase(unittest.TestCase):
    """Base case that keeps generated files out of the repository."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp(prefix="tv-spain-tests-")
        self.addCleanup(shutil.rmtree, self.output_dir, True)

    def make_collector(self, check_links=False):
        return tv.M3UCollector(
            country="Spain",
            base_dir=self.output_dir,
            check_links=check_links,
        )

    def parse(self, collector, lines, source="https://source.example/list.m3u"):
        collector.parse_and_store(lines, source)
        return collector

    def all_channels(self, collector):
        return [channel for group in collector.channels.values() for channel in group]

    def read_text(self, *parts):
        with open(os.path.join(self.output_dir, *parts), encoding="utf-8") as handle:
            return handle.read()

    def read_json(self, *parts):
        return json.loads(self.read_text(*parts))


class TestM3UParsing(CollectorTestCase):
    def test_parses_extinf_attributes(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(logo="https://logos.example/la1.png", group="Generalistas", name="La 1"),
            "https://cdn.example/la1.m3u8",
        ])

        self.assertEqual(list(collector.channels), ["Generalistas"])
        channel = collector.channels["Generalistas"][0]
        self.assertEqual(channel["name"], "La 1")
        self.assertEqual(channel["logo"], "https://logos.example/la1.png")
        self.assertEqual(channel["group"], "Generalistas")
        self.assertEqual(channel["url"], "https://cdn.example/la1.m3u8")
        self.assertEqual(channel["source"], "https://source.example/list.m3u")

    def test_missing_logo_falls_back_to_default(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 group-title="Deportes",Cadena Ser',
            "https://cdn.example/ser.m3u8",
        ])

        channel = collector.channels["Deportes"][0]
        self.assertEqual(channel["logo"], collector.default_logo)

    def test_empty_logo_attribute_falls_back_to_default(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 tvg-logo="" group-title="Deportes",Cadena Ser',
            "https://cdn.example/ser.m3u8",
        ])

        self.assertEqual(collector.channels["Deportes"][0]["logo"], collector.default_logo)

    def test_missing_group_is_uncategorized(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 tvg-logo="https://logos.example/x.png",Canal Sin Grupo',
            "https://cdn.example/x.m3u8",
        ])

        self.assertIn("Uncategorized", collector.channels)
        self.assertEqual(collector.channels["Uncategorized"][0]["name"], "Canal Sin Grupo")

    def test_missing_name_is_unnamed(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 tvg-logo="https://logos.example/x.png" group-title="Local"',
            "https://cdn.example/x.m3u8",
        ])

        self.assertEqual(collector.channels["Local"][0]["name"], "Unnamed Channel")

    def test_url_without_preceding_extinf_is_ignored(self):
        collector = self.make_collector()
        self.parse(collector, ["https://cdn.example/orphan.m3u8"])

        self.assertEqual(self.all_channels(collector), [])

    def test_directive_lines_do_not_break_the_pending_channel(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(name="La 1"),
            "#EXTVLCOPT:http-user-agent=Mozilla/5.0",
            "#EXTGRP:Generalistas",
            "https://cdn.example/la1.m3u8",
        ])

        self.assertEqual(len(self.all_channels(collector)), 1)
        self.assertEqual(collector.channels["Generalistas"][0]["name"], "La 1")

    def test_consecutive_extinf_keeps_only_the_last_entry(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(name="En desuso"),
            extinf_line(name="La 1"),
            "https://cdn.example/la1.m3u8",
        ])

        channels = self.all_channels(collector)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["name"], "La 1")

    def test_stored_channel_is_not_mutated_by_the_next_one(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(group="Generalistas", name="La 1"),
            "https://cdn.example/la1.m3u8",
            extinf_line(group="Deportes", name="Cadena Ser"),
            "https://cdn.example/ser.m3u8",
        ])

        self.assertEqual(collector.channels["Generalistas"][0]["url"], "https://cdn.example/la1.m3u8")
        self.assertEqual(collector.channels["Deportes"][0]["url"], "https://cdn.example/ser.m3u8")

    def test_ignores_blank_lines_and_surrounding_whitespace(self):
        collector = self.make_collector()
        self.parse(collector, [
            "",
            f"  {extinf_line(name='La 1')}  ",
            "   https://cdn.example/la1.m3u8   ",
            "",
        ])

        self.assertEqual(len(self.all_channels(collector)), 1)


class TestTvgMetadataParsing(CollectorTestCase):
    def test_reads_tvg_id_and_tvg_name(self):
        collector = self.make_collector()
        self.parse(collector, [
            full_extinf_line(tvg_id="La1.es", tvg_name="La 1 HD"),
            "https://cdn.example/la1.m3u8",
        ])

        channel = collector.channels["Generalistas"][0]
        self.assertEqual(channel["tvg_id"], "La1.es")
        self.assertEqual(channel["tvg_name"], "La 1 HD")

    def test_missing_attributes_become_empty_strings(self):
        collector = self.make_collector()
        self.parse(collector, [extinf_line(), "https://cdn.example/la1.m3u8"])

        channel = collector.channels["Generalistas"][0]
        self.assertEqual(channel["tvg_id"], "")
        self.assertEqual(channel["tvg_name"], "")

    def test_empty_attributes_become_empty_strings(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 tvg-id="" tvg-name="" group-title="Local",Canal',
            "https://cdn.example/local.m3u8",
        ])

        channel = collector.channels["Local"][0]
        self.assertEqual(channel["tvg_id"], "")
        self.assertEqual(channel["tvg_name"], "")

    def test_attribute_order_in_the_source_does_not_matter(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 group-title="Deportes" tvg-name="Ser" tvg-id="Ser.md" Cadena Ser',
            "https://cdn.example/ser.m3u8",
        ])

        channel = collector.channels["Deportes"][0]
        self.assertEqual(channel["tvg_id"], "Ser.md")
        self.assertEqual(channel["tvg_name"], "Ser")

    def test_values_with_spaces_and_commas_are_preserved(self):
        collector = self.make_collector()
        self.parse(collector, [
            full_extinf_line(tvg_id="Canal.24.es, hd", tvg_name="Canal 24, versión HD"),
            "https://cdn.example/24.m3u8",
        ])

        channel = collector.channels["Generalistas"][0]
        self.assertEqual(channel["tvg_id"], "Canal.24.es, hd")
        self.assertEqual(channel["tvg_name"], "Canal 24, versión HD")

    def test_a_quote_in_a_value_cannot_corrupt_the_parse(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 tvg-name="Canal "Raro"" group-title="Local",Canal Raro',
            "https://cdn.example/raro.m3u8",
        ])

        # The value stops at the first quote instead of swallowing the rest of the line.
        self.assertEqual(collector.channels["Local"][0]["tvg_name"], "Canal")
        self.assertEqual(collector.channels["Local"][0]["name"], "Canal Raro")
        self.assertEqual(collector.channels["Local"][0]["url"], "https://cdn.example/raro.m3u8")

    def test_empty_group_title_falls_back_to_uncategorized(self):
        collector = self.make_collector()
        self.parse(collector, [
            '#EXTINF:-1 group-title="" tvg-id="X.es",Canal',
            "https://cdn.example/x.m3u8",
        ])

        self.assertIn("Uncategorized", collector.channels)


class TestTvgMetadataMerging(CollectorTestCase):
    def test_a_later_source_fills_in_a_missing_tvg_id(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(name="La 1"),
            "https://cdn.example/la1.m3u8",
        ], source="https://pobre.example/list.m3u")
        self.parse(collector, [
            full_extinf_line(tvg_id="La1.es", tvg_name="La 1"),
            "https://cdn.example/la1.m3u8",
        ], source="https-rico.example/list.m3u")

        channels = self.all_channels(collector)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["tvg_id"], "La1.es")
        self.assertEqual(channels[0]["tvg_name"], "La 1")
        self.assertEqual(channels[0]["source"], "https://pobre.example/list.m3u")

    def test_a_later_source_never_overwrites_existing_metadata(self):
        collector = self.make_collector()
        self.parse(collector, [
            full_extinf_line(tvg_id="Original.es", tvg_name="Original"),
            "https://cdn.example/la1.m3u8",
        ], source="https://primero.example/list.m3u")
        self.parse(collector, [
            full_extinf_line(tvg_id="Otro.es", tvg_name="Otro"),
            "https://cdn.example/la1.m3u8",
        ], source="https://segundo.example/list.m3u")

        channel = self.all_channels(collector)[0]
        self.assertEqual(channel["tvg_id"], "Original.es")
        self.assertEqual(channel["tvg_name"], "Original")

    def test_merge_metadata_fills_each_field_independently(self):
        collector = self.make_collector()
        stored = {"tvg_id": "", "tvg_name": "Ya presente"}
        collector.merge_metadata(stored, {"tvg_id": "Nuevo.es", "tvg_name": "Nuevo"})

        self.assertEqual(stored["tvg_id"], "Nuevo.es")
        self.assertEqual(stored["tvg_name"], "Ya presente")

    def test_channel_index_is_cleared_between_runs(self):
        collector = self.make_collector()
        lines = [extinf_line(), "https://cdn.example/la1.m3u8"]
        self.parse(collector, lines)
        collector.process_sources([])

        self.assertEqual(collector.channel_by_url, {})
        self.parse(collector, [full_extinf_line(), "https://cdn.example/la1.m3u8"])
        self.assertEqual(collector.channels["Generalistas"][0]["tvg_id"], "La1.es")


class TestTvgMetadataExports(CollectorTestCase):
    def setUp(self):
        super().setUp()
        self.collector = self.make_collector()
        self.collector.channels["Generalistas"] = [
            {"name": "La 1", "tvg_id": "La1.es", "tvg_name": "La 1 HD",
             "logo": "logo-la1", "group": "Generalistas", "source": "src",
             "url": "https://cdn.example/la1.m3u8"},
            {"name": "Sin Metadatos", "tvg_id": "", "tvg_name": "",
             "logo": "logo-none", "group": "Generalistas", "source": "src",
             "url": "https://cdn.example/none.m3u8"},
        ]

    def test_m3u_includes_the_tvg_attributes(self):
        self.collector.export_m3u()
        lines = self.read_text("Spain", "LiveTV.m3u").splitlines()
        extinf = [line for line in lines if line.startswith("#EXTINF:")]

        self.assertEqual(extinf[0], (
            '#EXTINF:-1 tvg-id="La1.es" tvg-name="La 1 HD" '
            'tvg-logo="logo-la1" group-title="Generalistas",La 1'
        ))

    def test_m3u_omits_the_attributes_the_source_did_not_provide(self):
        self.collector.export_m3u()
        extinf = [line for line in self.read_text("Spain", "LiveTV.m3u").splitlines()
                  if line.startswith("#EXTINF:")]

        self.assertEqual(extinf[1], (
            '#EXTINF:-1 tvg-logo="logo-none" group-title="Generalistas",Sin Metadatos'
        ))
        self.assertNotIn("tvg-id", extinf[1])
        self.assertNotIn("tvg-name", extinf[1])

    def test_json_includes_the_tvg_fields(self):
        self.collector.export_json()
        channels = self.read_json("Spain", "LiveTV.json")["channels"]["Generalistas"]

        self.assertEqual(channels[0]["tvg_id"], "La1.es")
        self.assertEqual(channels[0]["tvg_name"], "La 1 HD")
        self.assertEqual(channels[1]["tvg_id"], "")
        self.assertEqual(channels[1]["tvg_name"], "")

    def test_custom_format_includes_the_tvg_fields(self):
        self.collector.export_custom()
        entries = self.read_json("Spain", "LiveTV")

        self.assertEqual(entries[0]["tvg_id"], "La1.es")
        self.assertEqual(entries[0]["tvg_name"], "La 1 HD")
        self.assertEqual(entries[1]["tvg_id"], "")

    def test_txt_includes_the_tvg_lines_only_when_present(self):
        self.collector.export_txt()
        content = self.read_text("Spain", "LiveTV.txt")

        self.assertEqual(content.count("TvgID: La1.es"), 1)
        self.assertEqual(content.count("TvgName: La 1 HD"), 1)
        self.assertEqual(content.count("TvgID: "), 1, "the empty entry must not emit a line")

    def test_exported_playlist_can_be_parsed_again(self):
        self.collector.export_m3u()
        m3u = self.read_text("Spain", "LiveTV.m3u").splitlines()

        reimported = self.make_collector()
        reimported.parse_and_store(m3u, "https://exportado.example/live.m3u")
        original = self.collector.channels["Generalistas"]
        roundtrip = reimported.channels["Generalistas"]

        self.assertEqual(len(roundtrip), 2)
        for before, after in zip(original, roundtrip):
            self.assertEqual(after["tvg_id"], before["tvg_id"])
            self.assertEqual(after["tvg_name"], before["tvg_name"])
            self.assertEqual(after["url"], before["url"])
            self.assertEqual(after["logo"], before["logo"])


class TestM3UEpgHeader(CollectorTestCase):
    """`url-tvg` advertises the merged guide; the manifest carries the sources.

    The playlist can no longer list the nine source guides in its header: it
    points at the single XMLTV file `TV-Spain-EPG.py` merges them into, which is
    what a player wants. The list of sources therefore has to live somewhere else,
    and that is what the manifest is for. Without it the merger would read the
    header, find its own output, and merge that into itself.
    """

    EPG_A = "https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml"
    EPG_B = "https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/es.xml.gz"
    EPG_C = "https://raw.githubusercontent.com/Llorchico/Rakuten/refs/heads/main/rakuten.xml"

    def populate(self, collector):
        collector.channels["Generalistas"] = [{
            "name": "La 1", "logo": "logo", "group": "Generalistas",
            "source": "src", "url": "https://cdn.example/la1.m3u8",
        }]

    def header_with(self, *epg_urls):
        collector = self.make_collector()
        self.populate(collector)
        collector.epg_urls = list(epg_urls)
        collector.export_m3u()
        return self.read_text("Spain", "LiveTV.m3u").splitlines()[0]

    def collector_from_sources(self, *header_lines):
        """Feed *header_lines* as a source playlist and return the collector."""
        collector = self.make_collector()
        body = ['#EXTINF:-1 group-title="Generalistas",La 1', "https://cdn.example/la1.m3u8"]
        with mock.patch.object(tv.M3UCollector, "fetch_content",
                               return_value=(None, list(header_lines) + body)):
            collector.process_sources(["https://source.example/list.m3u"])
        return collector

    def collector_from_sources_declaring(self, *epg_urls):
        """Feed one source playlist per entry, each declaring that guide alone."""
        collector = self.make_collector()
        body = ['#EXTINF:-1 group-title="G",C', "https://cdn.example/c.m3u8"]
        sources = [f"https://src{i}.example/list.m3u" for i in range(len(epg_urls))]

        def fake_fetch(self, url):
            return (None, [f'#EXTM3U url-tvg="{epg_urls[sources.index(url)]}"'] + body)

        with mock.patch.object(tv.M3UCollector, "fetch_content", fake_fetch):
            collector.process_sources(sources)
        return collector

    # ---- reading the sources out of a playlist --------------------------

    def test_extracts_a_single_epg_url(self):
        self.assertEqual(tv.M3UCollector.epg_urls_from_header([f'#EXTM3U url-tvg="{self.EPG_A}"']), [self.EPG_A])

    def test_extracts_several_epg_urls_from_one_source(self):
        header = f'#EXTM3U url-tvg="{self.EPG_A}, {self.EPG_B}"'
        self.assertEqual(tv.M3UCollector.epg_urls_from_header([header]), [self.EPG_A, self.EPG_B])

    def test_trims_whitespace_around_each_url(self):
        header = f'#EXTM3U url-tvg="  {self.EPG_A} ,   {self.EPG_B}  "'
        self.assertEqual(tv.M3UCollector.epg_urls_from_header([header]), [self.EPG_A, self.EPG_B])

    def test_a_source_without_url_tvg_contributes_nothing(self):
        self.assertEqual(tv.M3UCollector.epg_urls_from_header(["#EXTM3U"]), [])

    def test_an_empty_url_tvg_contributes_nothing(self):
        self.assertEqual(tv.M3UCollector.epg_urls_from_header(['#EXTM3U url-tvg=""']), [])

    def test_a_trailing_comma_is_ignored(self):
        header = f'#EXTM3U url-tvg="{self.EPG_A}, "'
        self.assertEqual(tv.M3UCollector.epg_urls_from_header([header]), [self.EPG_A])

    def test_only_the_header_line_is_inspected(self):
        lines = [f'#EXTM3U url-tvg="{self.EPG_A}"', '#EXTINF:-1 group-title="G",C',
                 "https://x.example/s.m3u8"]
        self.assertEqual(tv.M3UCollector.epg_urls_from_header(lines), [self.EPG_A])

    def test_epg_is_cleared_between_runs(self):
        collector = self.make_collector()
        collector.epg_urls = [self.EPG_A]
        collector.process_sources([])
        self.assertEqual(collector.epg_urls, [])

    def test_several_sources_are_merged_in_order(self):
        collector = self.collector_from_sources_declaring("https://a.example/a.m3u",
                                                          "https://b.example/b.m3u")
        self.assertEqual(collector.epg_urls,
                         ["https://a.example/a.m3u", "https://b.example/b.m3u"])

    def test_a_guide_shared_by_two_sources_is_kept_once(self):
        collector = self.make_collector()
        collector.epg_urls = [self.EPG_A, self.EPG_B, self.EPG_A]
        self.assertEqual(collector.unique_epg_urls(), [self.EPG_A, self.EPG_B])

    # ---- what the playlist advertises -----------------------------------

    def test_header_points_at_the_merged_guide(self):
        header = self.header_with(self.EPG_A, self.EPG_B)
        self.assertEqual(header, f'#EXTM3U url-tvg="{tv.MERGED_EPG_URL}"')

    def test_merged_url_is_the_compressed_guide_of_this_repository(self):
        self.assertTrue(tv.MERGED_EPG_URL.startswith("https://raw.githubusercontent.com/"))
        self.assertTrue(tv.MERGED_EPG_URL.endswith("LiveTV/Spain/LiveTV.xml.gz"))

    def test_header_no_longer_lists_the_source_guides(self):
        header = self.header_with(self.EPG_A, self.EPG_B)
        self.assertNotIn(self.EPG_A, header)
        self.assertNotIn(self.EPG_B, header)

    def test_a_single_source_guide_is_enough_to_publish_the_pointer(self):
        self.assertEqual(self.header_with(self.EPG_A),
                         f'#EXTM3U url-tvg="{tv.MERGED_EPG_URL}"')

    def test_header_stays_bare_without_epg(self):
        self.assertEqual(self.header_with(), "#EXTM3U")

    def test_the_header_never_lists_an_m3u_source(self):
        collector = self.collector_from_sources(f'#EXTM3U url-tvg="{self.EPG_A}"')
        collector.export_m3u()
        header = self.read_text("Spain", "LiveTV.m3u").splitlines()[0]
        self.assertNotIn("list.m3u", header)

    def test_the_exported_header_parses_back(self):
        header = self.header_with(self.EPG_A)
        self.assertEqual(tv.M3UCollector.extinf_attribute(header, "url-tvg"),
                         tv.MERGED_EPG_URL)

    def test_stream_entries_still_follow_the_header(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.epg_urls = [self.EPG_A]
        collector.export_m3u()
        lines = self.read_text("Spain", "LiveTV.m3u").splitlines()
        self.assertTrue(lines[0].startswith("#EXTM3U "))
        self.assertTrue(lines[1].startswith("#EXTINF:"))
        self.assertEqual(lines[2], "https://cdn.example/la1.m3u8")

    # ---- the manifest the merger reads ----------------------------------

    def test_manifest_lists_the_source_guides(self):
        collector = self.collector_from_sources(f'#EXTM3U url-tvg="{self.EPG_A}, {self.EPG_B}"')
        collector.export_epg_manifest()

        self.assertEqual(self.read_json("Spain", "epg-sources.json")["epg_urls"],
                         [self.EPG_A, self.EPG_B])

    def test_manifest_records_exactly_what_the_sources_declared(self):
        # The manifest is a faithful copy of the collected list; the guard against
        # feeding the merger its own output lives in TV-Spain-EPG.py, which is
        # where the header fallback is read.
        collector = self.make_collector()
        collector.epg_urls = [self.EPG_A, tv.MERGED_EPG_URL]
        collector.export_epg_manifest()

        self.assertEqual(self.read_json("Spain", "epg-sources.json")["epg_urls"],
                         [self.EPG_A, tv.MERGED_EPG_URL])

    def test_manifest_keeps_the_source_order(self):
        collector = self.make_collector()
        collector.epg_urls = [self.EPG_C, self.EPG_A, self.EPG_B]
        collector.export_epg_manifest()

        self.assertEqual(self.read_json("Spain", "epg-sources.json")["epg_urls"],
                         [self.EPG_C, self.EPG_A, self.EPG_B])

    def test_manifest_drops_a_guide_shared_by_two_sources(self):
        collector = self.make_collector()
        collector.epg_urls = [self.EPG_A, self.EPG_B, self.EPG_A]
        collector.export_epg_manifest()

        self.assertEqual(self.read_json("Spain", "epg-sources.json")["epg_urls"],
                         [self.EPG_A, self.EPG_B])

    def test_manifest_is_empty_when_there_is_no_epg(self):
        collector = self.make_collector()
        collector.export_epg_manifest()

        self.assertEqual(self.read_json("Spain", "epg-sources.json")["epg_urls"], [])

    def test_the_manifest_sits_next_to_the_playlist(self):
        collector = self.make_collector()
        collector.export_m3u()
        collector.export_epg_manifest()

        self.assertEqual(sorted(os.listdir(os.path.join(self.output_dir, "Spain"))),
                         ["LiveTV.m3u", "epg-sources.json"])


class TestSourceOrderIsPreserved(CollectorTestCase):
    """A channel keeps the position it had in its source playlist.

    The merged file must read like the playlists it was built from: the first
    source contributes its channels first, each one in its original order.
    """

    def build(self, *per_source_lines):
        """Run process_sources over fake sources, each given as a list of lines."""
        collector = self.make_collector()
        queues = {f"https://src{i}.example/list.m3u": list(lines)
                  for i, lines in enumerate(per_source_lines)}
        urls = list(queues)
        with mock.patch.object(tv.M3UCollector, "fetch_content",
                               side_effect=lambda url: (None, queues[url])):
            collector.process_sources(urls)
        return collector

    @staticmethod
    def source(*names, group="G"):
        lines = []
        for name in names:
            lines.append(f'#EXTINF:-1 group-title="{group}",{name}')
            lines.append(f"https://cdn.example/{name}.m3u8")
        return lines

    def m3u_names(self, collector):
        collector.export_m3u()
        content = self.read_text("Spain", "LiveTV.m3u")
        return [line.split(",")[-1] for line in content.splitlines()
                if line.startswith("#EXTINF:")]

    def test_channels_follow_the_order_of_a_single_source(self):
        collector = self.build(self.source("Zeta", "Alfa", "Omega"))
        self.assertEqual(self.m3u_names(collector), ["Zeta", "Alfa", "Omega"])

    def test_channels_of_the_first_source_come_before_the_second(self):
        collector = self.build(self.source("A1", "A2"), self.source("B1", "B2"))
        self.assertEqual(self.m3u_names(collector), ["A1", "A2", "B1", "B2"])

    def test_sources_keep_the_declared_order(self):
        collector = self.build(self.source("X"), self.source("Y"), self.source("Z"))
        self.assertEqual(self.m3u_names(collector), ["X", "Y", "Z"])

    def test_the_same_order_repeats_on_a_second_identical_run(self):
        first = self.m3u_names(self.build(self.source("B", "A"), self.source("D", "C")))
        second = self.m3u_names(self.build(self.source("B", "A"), self.source("D", "C")))
        self.assertEqual(first, second)

    def test_a_group_keeps_the_position_of_its_first_channel(self):
        collector = self.make_collector()
        lines = ['#EXTINF:-1 group-title="Zeta",C1', "https://cdn.example/c1.m3u8",
                 '#EXTINF:-1 group-title="Alfa",C2', "https://cdn.example/c2.m3u8",
                 '#EXTINF:-1 group-title="Zeta",C3', "https://cdn.example/c3.m3u8"]
        with mock.patch.object(tv.M3UCollector, "fetch_content", return_value=(None, lines)):
            collector.process_sources(["https://src.example/list.m3u"])

        self.assertEqual(list(collector.channels), ["Zeta", "Alfa"])
        self.assertEqual(self.m3u_names(collector), ["C1", "C3", "C2"])

    def test_every_export_agrees_on_the_order(self):
        collector = self.build(self.source("B", "A"), self.source("C"))
        names = ["B", "A", "C"]
        self.m3u_names(collector)

        collector.export_txt()
        collector.export_json()
        collector.export_custom()
        from_txt = [l.split(": ", 1)[1] for l in self.read_text("Spain", "LiveTV.txt").splitlines()
                    if l.startswith("Name: ")]
        from_json = [c["name"] for group in self.read_json("Spain", "LiveTV.json")["channels"].values()
                     for c in group]
        from_custom = [e["name"] for e in self.read_json("Spain", "LiveTV")]

        self.assertEqual(from_txt, names)
        self.assertEqual(from_json, names)
        self.assertEqual(from_custom, names)

    def test_link_checking_does_not_reshuffle_the_channels(self):
        # Results arrive in completion order; the export must still be in source order.
        collector = self.make_collector(check_links=True)
        collector.channels["G"] = [
            {"name": name, "logo": "l", "group": "G", "source": "src",
             "url": f"https://cdn.example/{name}.m3u8"}
            for name in ("C1", "C2", "C3")
        ]

        # Complete in reverse order to imitate slow/fast futures.
        completed = []

        class FakeFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class FakeExecutor:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def submit(self, fn, url):
                completed.append(url)
                return FakeFuture((True, url))

        with mock.patch.object(tv.concurrent.futures, "ThreadPoolExecutor", FakeExecutor), \
             mock.patch.object(tv.concurrent.futures, "as_completed",
                               side_effect=lambda futs: reversed(list(futs))):
            collector.filter_active_channels()

        self.assertEqual(completed, ["https://cdn.example/C1.m3u8",
                                     "https://cdn.example/C2.m3u8",
                                     "https://cdn.example/C3.m3u8"])
        self.assertEqual([c["name"] for c in collector.channels["G"]], ["C1", "C2", "C3"])

    def test_dropped_channels_do_not_disturb_the_remaining_order(self):
        collector = self.make_collector(check_links=True)
        collector.channels["G"] = [
            {"name": name, "logo": "l", "group": "G", "source": "src",
             "url": f"https://cdn.example/{name}.m3u8"}
            for name in ("C1", "C2", "C3", "C4")
        ]
        dead = "https://cdn.example/C2.m3u8"

        class FakeFuture:
            def __init__(self, url):
                self._url = url

            def result(self):
                return (self._url != dead, self._url)

        class FakeExecutor:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def submit(self, fn, url):
                return FakeFuture(url)

        with mock.patch.object(tv.concurrent.futures, "ThreadPoolExecutor", FakeExecutor), \
             mock.patch.object(tv.concurrent.futures, "as_completed",
                               side_effect=lambda futs: list(futs)):
            collector.filter_active_channels()

        self.assertEqual([c["name"] for c in collector.channels["G"]], ["C1", "C3", "C4"])


class TestUrlDeduplication(CollectorTestCase):
    def test_duplicate_url_in_same_playlist_is_stored_once(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(name="La 1"),
            "https://cdn.example/la1.m3u8",
            extinf_line(name="La 1 (respaldo)"),
            "https://cdn.example/la1.m3u8",
        ])

        channels = self.all_channels(collector)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["name"], "La 1")

    def test_duplicate_url_across_sources_keeps_first_source(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(name="La 1"),
            "https://cdn.example/la1.m3u8",
        ], source="https://first.example/list.m3u")
        self.parse(collector, [
            extinf_line(name="La 1 duplicada"),
            "https://cdn.example/la1.m3u8",
        ], source="https://second.example/list.m3u")

        channels = self.all_channels(collector)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["source"], "https://first.example/list.m3u")

    def test_same_name_with_different_urls_is_kept(self):
        collector = self.make_collector()
        self.parse(collector, [
            extinf_line(name="La 1"),
            "https://cdn.example/la1.m3u8",
            extinf_line(name="La 1"),
            "https://backup.example/la1.m3u8",
        ])

        self.assertEqual(len(self.all_channels(collector)), 2)

    def test_seen_urls_is_reset_between_runs(self):
        collector = self.make_collector()
        lines = [extinf_line(name="La 1"), "https://cdn.example/la1.m3u8"]

        self.parse(collector, lines)
        first_run = len(self.all_channels(collector))
        collector.process_sources([])  # resets channels, seen_urls and the status cache
        self.parse(collector, lines)
        self.assertEqual(first_run, 1)
        self.assertEqual(len(self.all_channels(collector)), 1)


class TestTvgNameDeduplication(CollectorTestCase):
    """Duplicates are spotted on tvg-name; the winner is the first live stream."""

    def stub_streams(self, collector, alive_urls, calls=None):
        """Replace the network probe: *alive_urls* answer, everything else is down."""
        def fake_check(url, timeout=2):
            if calls is not None:
                calls.append(url)
            return url in alive_urls, url
        collector.check_link_active = fake_check

    def dedupe(self, collector, alive_urls, calls=None):
        self.stub_streams(collector, alive_urls, calls)
        collector.dedupe_by_tvg_name()
        return [ch["name"] for ch in self.all_channels(collector)]

    def build(self, collector, specs, source="https://source.example/list.m3u"):
        """Store one channel per (tvg_name, name, group, url) tuple.

        A tvg_name of None emits an #EXTINF with no tvg-* attributes at all,
        which is what a source that ships no metadata looks like.
        """
        lines = []
        for tvg_name, name, group, url in specs:
            if tvg_name is None:
                entry = extinf_line(group=group, name=name)
            else:
                entry = full_extinf_line(
                    tvg_id=f"id-{name}", tvg_name=tvg_name, group=group, name=name)
            lines += [entry, url]
        return self.parse(collector, lines, source=source)

    # ---- the key itself -------------------------------------------------

    def test_key_normalises_case_and_inner_whitespace(self):
        self.assertEqual(tv.M3UCollector.duplicate_key({"tvg_name": "La  1 "}), "la 1")
        self.assertEqual(tv.M3UCollector.duplicate_key({"tvg_name": "  LA   1"}), "la 1")
        self.assertEqual(tv.M3UCollector.duplicate_key({"tvg_name": "Pocoyó"}), "pocoyó")

    def test_key_is_none_without_a_usable_tvg_name(self):
        # Without metadata to match on, a channel must not be lumped together
        # with every other channel that has no tvg-name.
        for channel in ({}, {"tvg_name": ""}, {"tvg_name": "   "}, {"tvg_name": None}):
            self.assertIsNone(tv.M3UCollector.duplicate_key(channel))

    def test_channels_without_tvg_name_are_all_kept(self):
        collector = self.make_collector()
        self.build(collector, [
            (None, "Sin metadatos A", "Generalistas", "https://cdn.example/a.m3u8"),
            (None, "Sin metadatos B", "Generalistas", "https://cdn.example/b.m3u8"),
            (None, "Sin metadatos C", "Generalistas", "https://cdn.example/c.m3u8"),
        ])
        self.assertEqual(
            self.dedupe(collector, alive_urls=set()),
            ["Sin metadatos A", "Sin metadatos B", "Sin metadatos C"],
        )

    # ---- who wins -------------------------------------------------------

    def test_keeps_the_first_copy_when_its_stream_works(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Segunda", "Entretenimiento", "https://b.example/la1.m3u8"),
        ])
        self.assertEqual(
            self.dedupe(collector, alive_urls={"https://a.example/la1.m3u8"}),
            ["Primera"],
        )

    def test_falls_back_to_the_next_copy_when_the_first_is_down(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Caida", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Viva", "Entretenimiento", "https://b.example/la1.m3u8"),
            ("La 1", "Tercera", "Spain", "https://c.example/la1.m3u8"),
        ])
        self.assertEqual(
            self.dedupe(collector, alive_urls={"https://b.example/la1.m3u8"}),
            ["Viva"],
        )

    def test_keeps_the_first_copy_when_none_of_them_answers(self):
        # A probe that fails because of a network blip must never make a channel
        # disappear from the published playlist.
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Segunda", "Entretenimiento", "https://b.example/la1.m3u8"),
        ])
        self.assertEqual(
            self.dedupe(collector, alive_urls=set()),
            ["Primera"],
        )

    def test_probing_stops_at_the_first_working_copy(self):
        # Laziness is the whole point: a group is never probed past the winner.
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Caida", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Viva", "Entretenimiento", "https://b.example/la1.m3u8"),
            ("La 1", "Intacta", "Spain", "https://c.example/la1.m3u8"),
        ])
        probed = []
        self.dedupe(collector, alive_urls={"https://b.example/la1.m3u8"}, calls=probed)
        self.assertEqual(probed, ["https://a.example/la1.m3u8", "https://b.example/la1.m3u8"])

    def test_resolved_url_replaces_the_winner_url(self):
        # check_link_active may find the stream on the other protocol.
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "http://a.example/la1.m3u8"),
            ("La 1", "Segunda", "Entretenimiento", "https://b.example/la1.m3u8"),
        ])

        def fake_check(url, timeout=2):
            return True, url.replace("http://", "https://")

        collector.check_link_active = fake_check
        collector.dedupe_by_tvg_name()
        self.assertEqual(self.all_channels(collector)[0]["url"], "https://a.example/la1.m3u8")

    # ---- matching -------------------------------------------------------

    def test_case_and_spacing_variants_are_duplicates(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("  la   1 ", "Tercera", "Spain", "https://c.example/la1.m3u8"),
        ])
        self.assertEqual(self.dedupe(collector, alive_urls=set()), ["Primera"])

    def test_duplicates_are_matched_across_categories(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Segunda", "Entretenimiento", "https://b.example/la1.m3u8"),
            ("La 2", "Otra", "Generalistas", "https://c.example/la2.m3u8"),
        ])
        self.assertEqual(self.dedupe(collector, alive_urls=set()), ["Primera", "Otra"])

    def test_unique_channels_are_never_probed(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 2", "Segunda", "Generalistas", "https://b.example/la2.m3u8"),
        ])
        probed = []
        self.assertEqual(
            self.dedupe(collector, alive_urls=set(), calls=probed),
            ["Primera", "Segunda"],
        )
        self.assertEqual(probed, [])

    # ---- order is preserved ---------------------------------------------

    def test_survivors_keep_their_original_order(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "A", "Generalistas", "https://a.example/1.m3u8"),
            ("La 2", "B", "Generalistas", "https://b.example/2.m3u8"),
            ("La 1", "C", "Generalistas", "https://c.example/1.m3u8"),
            ("La 3", "D", "Generalistas", "https://d.example/3.m3u8"),
        ])
        self.assertEqual(
            self.dedupe(collector, alive_urls={"https://a.example/1.m3u8"}),
            ["A", "B", "D"],
        )

    def test_a_category_left_empty_disappears(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Duplicada", "Entretenimiento", "https://b.example/la1.m3u8"),
            ("La 2", "Segunda", "Generalistas", "https://c.example/la2.m3u8"),
        ])
        self.dedupe(collector, alive_urls=set())
        self.assertEqual(list(collector.channels), ["Generalistas"])

    def test_groups_keep_the_position_of_their_first_surviving_channel(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "A", "Primero", "https://a.example/1.m3u8"),
            ("La 1", "Duplicada", "Segundo", "https://b.example/1.m3u8"),
            ("La 2", "C", "Tercero", "https://c.example/2.m3u8"),
        ])
        self.dedupe(collector, alive_urls=set())
        self.assertEqual(list(collector.channels), ["Primero", "Tercero"])

    # ---- it reaches the published files ---------------------------------

    def test_every_export_reflects_the_deduplicated_playlist(self):
        collector = self.make_collector()
        self.build(collector, [
            ("La 1", "Primera", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Duplicada", "Entretenimiento", "https://b.example/la1.m3u8"),
        ])
        self.dedupe(collector, alive_urls=set())
        collector.export_m3u("LiveTV.m3u")
        collector.export_txt("LiveTV.txt")
        collector.export_json("LiveTV.json")
        collector.export_custom("LiveTV")

        m3u = self.read_text("Spain", "LiveTV.m3u")
        self.assertIn("Primera", m3u)
        self.assertNotIn("Duplicada", m3u)
        self.assertEqual(m3u.count("#EXTINF"), 1)
        self.assertNotIn("Duplicada", self.read_text("Spain", "LiveTV.txt"))
        self.assertNotIn("Duplicada", self.read_text("Spain", "LiveTV"))
        self.assertEqual(
            [c["name"] for c in self.read_json("Spain", "LiveTV.json")["channels"]["Generalistas"]],
            ["Primera"],
        )

    def test_runs_after_link_filtering_so_the_cache_is_reused(self):
        # With --check-links the streams were already probed; dedup must work on
        # that result instead of probing the whole playlist again.
        collector = self.make_collector(check_links=True)
        self.build(collector, [
            ("La 1", "Caida", "Generalistas", "https://a.example/la1.m3u8"),
            ("La 1", "Viva", "Entretenimiento", "https://b.example/la1.m3u8"),
        ])
        probed = []
        self.stub_streams(collector, {"https://b.example/la1.m3u8"}, probed)

        collector.filter_active_channels()
        collector.dedupe_by_tvg_name()

        self.assertEqual([c["name"] for c in self.all_channels(collector)], ["Viva"])
        # b.example was already known to be alive from the filtering pass.
        self.assertEqual(probed.count("https://b.example/la1.m3u8"), 1)


class TestLinkFiltering(CollectorTestCase):
    def build_channels(self):
        return [
            {"name": "La 1", "logo": "l", "group": "Generalistas", "source": "s", "url": "https://cdn.example/la1.m3u8"},
            {"name": "La 1 alt", "logo": "l", "group": "Generalistas", "source": "s", "url": "https://cdn.example/la1.m3u8"},
            {"name": "La 2", "logo": "l", "group": "Generalistas", "source": "s", "url": "https://cdn.example/la2.m3u8"},
            {"name": "Muerta", "logo": "l", "group": "Deportes", "source": "s", "url": "https://cdn.example/dead.m3u8"},
        ]

    def test_each_unique_url_is_probed_once(self):
        collector = self.make_collector(check_links=True)
        collector.channels["Generalistas"] = self.build_channels()[:3]
        probed = []

        def fake_check(url, timeout=2):
            probed.append(url)
            return True, url

        collector.check_link_active = fake_check
        collector.filter_active_channels()

        self.assertCountEqual(probed, [
            "https://cdn.example/la1.m3u8",
            "https://cdn.example/la2.m3u8",
        ])
        self.assertEqual(len(probed), 2, "the shared URL must not be probed twice")

    def test_inactive_channels_are_dropped(self):
        collector = self.make_collector(check_links=True)
        collector.channels["Generalistas"] = self.build_channels()

        def fake_check(url, timeout=2):
            return (not url.endswith("dead.m3u8"), url)

        collector.check_link_active = fake_check
        collector.filter_active_channels()

        names = [channel["name"] for channel in self.all_channels(collector)]
        self.assertNotIn("Muerta", names)
        self.assertIn("La 1", names)
        self.assertNotIn("Deportes", collector.channels, "empty groups must be removed")

    def test_working_url_is_replaced_by_the_resolved_url(self):
        collector = self.make_collector(check_links=True)
        collector.channels["Generalistas"] = [{
            "name": "La 1", "logo": "l", "group": "Generalistas", "source": "s",
            "url": "http://cdn.example/la1.m3u8",
        }]
        collector.check_link_active = lambda url, timeout=2: (True, url.replace("http://", "https://"))
        collector.filter_active_channels()

        self.assertEqual(collector.channels["Generalistas"][0]["url"], "https://cdn.example/la1.m3u8")

    def test_check_links_disabled_skips_probing(self):
        collector = self.make_collector(check_links=False)
        collector.channels["Generalistas"] = self.build_channels()

        def explode(url, timeout=2):
            raise AssertionError("check_link_active must not be called when check_links is False")

        collector.check_link_active = explode
        collector.filter_active_channels()

        self.assertEqual(len(self.all_channels(collector)), 4)


class TestCheckLinkActive(CollectorTestCase):
    def setUp(self):
        super().setUp()
        self.collector = self.make_collector(check_links=True)

    def test_error_status_returns_false_instead_of_none(self):
        response = mock.Mock(status_code=404)
        with mock.patch.object(tv.requests, "head", return_value=response):
            result = self.collector.check_link_active("https://cdn.example/missing.m3u8")

        self.assertEqual(result, (False, "https://cdn.example/missing.m3u8"))

    def test_successful_head_returns_true(self):
        response = mock.Mock(status_code=200)
        with mock.patch.object(tv.requests, "head", return_value=response):
            result = self.collector.check_link_active("https://cdn.example/live.m3u8")

        self.assertEqual(result, (True, "https://cdn.example/live.m3u8"))

    def test_falls_back_to_get_when_head_fails(self):
        head_error = tv.requests.RequestException("no HEAD support")
        get_response = mock.Mock(status_code=200)
        get_response.__enter__ = mock.Mock(return_value=get_response)
        get_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.object(tv.requests, "head", side_effect=head_error), \
             mock.patch.object(tv.requests, "get", return_value=get_response):
            result = self.collector.check_link_active("https://cdn.example/live.m3u8")

        self.assertEqual(result, (True, "https://cdn.example/live.m3u8"))

    def test_retries_the_alternate_protocol_on_connection_error(self):
        head_error = tv.requests.ConnectionError("refused")
        get_error = tv.requests.ConnectionError("refused")
        ok = mock.Mock(status_code=200)

        def head(url, **kwargs):
            return ok if url.startswith("https://") else (_ for _ in ()).throw(head_error)

        with mock.patch.object(tv.requests, "head", side_effect=head), \
             mock.patch.object(tv.requests, "get", side_effect=get_error):
            result = self.collector.check_link_active("http://cdn.example/live.m3u8")

        self.assertEqual(result, (True, "https://cdn.example/live.m3u8"))

    def test_result_is_cached_per_url(self):
        response = mock.Mock(status_code=200)
        with mock.patch.object(tv.requests, "head", return_value=response) as head:
            first = self.collector.check_link_active("https://cdn.example/live.m3u8")
            second = self.collector.check_link_active("https://cdn.example/live.m3u8")

        self.assertEqual(first, second)
        self.assertEqual(head.call_count, 1)


class TestHtmlExtraction(CollectorTestCase):
    def setUp(self):
        super().setUp()
        self.collector = self.make_collector()

    def extract(self, html, base_url="https://site.example/live/index.html"):
        return self.collector.extract_stream_urls_from_html(html, base_url)

    def test_extracts_playlist_links(self):
        urls = self.extract("""
            <a href="https://cdn.example/la1.m3u8">La 1</a>
            <a href="https://cdn.example/ser.m3u">Ser</a>
        """)

        self.assertCountEqual(urls, [
            "https://cdn.example/la1.m3u8",
            "https://cdn.example/ser.m3u",
        ])

    def test_resolves_relative_links_against_the_page(self):
        urls = self.extract('<a href="/play/la1.m3u8">La 1</a>')

        self.assertEqual(urls, ["https://site.example/play/la1.m3u8"])

    def test_skips_excluded_hosts_and_extensions(self):
        urls = self.extract("""
            <a href="https://t.me/channel">Telegram</a>
            <a href="https://site.example/player.html">Player</a>
            <a href="https://github.com/user/repo">Repo</a>
            <a href="https://site.example/login">Login</a>
            <a href="https://cdn.example/la1.m3u8">La 1</a>
        """)

        self.assertEqual(urls, ["https://cdn.example/la1.m3u8"])

    def test_returns_nothing_for_empty_input(self):
        self.assertEqual(self.extract(""), [])
        self.assertEqual(self.extract(None), [])


class TestExports(CollectorTestCase):
    def populate(self, collector):
        # Inserted in a deliberate non-alphabetical order (Generalistas first, and
        # Telecinco before La 1 inside it) so the exports must reproduce it verbatim.
        collector.channels["Generalistas"] = [
            {"name": "Telecinco", "logo": "logo-t5", "group": "Generalistas",
             "source": "src", "url": "https://cdn.example/t5.m3u8"},
            {"name": "La 1", "logo": "logo-la1", "group": "Generalistas",
             "source": "src", "url": "https://cdn.example/la1.m3u8"},
        ]
        collector.channels["Deportes"] = [{
            "name": "Cadena Ser", "logo": "logo-ser", "group": "Deportes",
            "source": "src", "url": "https://cdn.example/ser.m3u8",
        }]

    def test_exports_every_format(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.export_m3u()
        collector.export_txt()
        collector.export_json()
        collector.export_custom()

        produced = sorted(os.listdir(os.path.join(self.output_dir, "Spain")))
        self.assertEqual(produced, ["LiveTV", "LiveTV.json", "LiveTV.m3u", "LiveTV.txt"])

    def test_m3u_writes_a_header_and_one_entry_per_channel(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.export_m3u()
        lines = [line for line in self.read_text("Spain", "LiveTV.m3u").splitlines() if line]

        self.assertEqual(lines[0], "#EXTM3U")
        self.assertEqual(sum(1 for line in lines if line.startswith("#EXTINF:")), 3)
        self.assertEqual(sum(1 for line in lines if line.startswith("http")), 3)
        # Groups keep the order of their first appearance, so Generalistas leads.
        self.assertIn('tvg-logo="logo-t5"', lines[1])
        self.assertIn('group-title="Generalistas"', lines[1])
        self.assertTrue(lines[1].endswith(",Telecinco"))
        self.assertIn('group-title="Deportes"', lines[5])
        self.assertIn('group-title="Generalistas"', lines[3])
        self.assertTrue(lines[3].endswith(",La 1"))

    def test_channels_keep_the_source_order_in_every_format(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.export_m3u()
        collector.export_txt()
        collector.export_json()
        collector.export_custom()
        # populate() inserts Generalistas first (Telecinco, La 1) and Deportes
        # second (Cadena Ser), so the export must not regroup or alphabetise.
        m3u = self.read_text("Spain", "LiveTV.m3u")
        self.assertLess(m3u.index("Telecinco"), m3u.index("La 1"))
        self.assertLess(m3u.index("La 1"), m3u.index("Cadena Ser"))

        data = self.read_json("Spain", "LiveTV.json")
        self.assertEqual(list(data["channels"]), ["Generalistas", "Deportes"])
        self.assertEqual(
            [channel["name"] for channel in data["channels"]["Generalistas"]],
            ["Telecinco", "La 1"],
        )

        custom = self.read_json("Spain", "LiveTV")
        self.assertEqual([entry["name"] for entry in custom], ["Telecinco", "La 1", "Cadena Ser"])

    def test_txt_separates_entries_with_a_rule(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.export_txt()
        content = self.read_text("Spain", "LiveTV.txt")

        self.assertEqual(content.count("Group: "), 2)
        self.assertEqual(content.count("URL: "), 3)
        self.assertEqual(content.count("-" * 50), 3)

    def test_json_metadata_contains_a_timestamp(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.export_json()
        data = self.read_json("Spain", "LiveTV.json")

        self.assertIn("date", data)
        self.assertRegex(data["date"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


class TestExportTimestamp(CollectorTestCase):
    """The published `date` must be the real run time, in Madrid time.

    GitHub's cron is best effort and never starts a workflow on time, so the
    scheduled minute would be a lie. The timestamp is therefore the instant the
    collector actually ran, expressed in Europe/Madrid: a timestamp in any other
    zone makes the "updated N min ago" banner in index.html wrong. It is also
    written as ISO 8601 with an explicit offset, so the browser resolves the
    instant correctly no matter which timezone the visitor is in.
    """

    def export_with_now(self, now):
        collector = self.make_collector()
        collector.channels["Generalistas"] = [{
            "name": "La 1", "logo": "logo", "group": "Generalistas",
            "source": "src", "url": "https://cdn.example/la1.m3u8",
        }]
        real_datetime = tv.datetime

        class FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now

        with mock.patch.object(tv, "datetime", FakeDatetime):
            collector.export_json()
        return self.read_json("Spain", "LiveTV.json")["date"]

    def test_timestamp_is_madrid_time_in_summer(self):
        # 16:00 UTC is 18:00 in Madrid during CEST.
        now = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(self.export_with_now(now), "2026-07-15T18:00:00+02:00")

    def test_timestamp_is_madrid_time_in_winter(self):
        # 16:00 UTC is 17:00 in Madrid during CET.
        now = datetime(2026, 1, 15, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(self.export_with_now(now), "2026-01-15T17:00:00+01:00")

    def test_timestamp_is_not_the_collector_local_timezone(self):
        # The same instant expressed in Asia/Kolkata would be 21:30; the fix must
        # not depend on whatever timezone the machine running the script has.
        now = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)
        self.assertNotIn("21:30", self.export_with_now(now))

    def test_timestamp_carries_an_explicit_offset(self):
        # Without the offset, `new Date(...)` in the browser would silently
        # interpret the value in the visitor's timezone.
        now = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)
        self.assertTrue(self.export_with_now(now).endswith("+02:00"))

    def test_timestamp_parses_back_to_the_same_instant(self):
        now = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)
        published = self.export_with_now(now)
        self.assertEqual(datetime.fromisoformat(published), now)

    def test_timestamp_is_the_real_run_time_not_the_scheduled_one(self):
        # Unmocked: the exported `date` must track the wall clock, because the
        # cron minute is not when the workflow starts. The export truncates to
        # whole seconds, hence the one second of slack.
        collector = self.make_collector()
        collector.channels["Generalistas"] = [{
            "name": "La 1", "logo": "logo", "group": "Generalistas",
            "source": "src", "url": "https://cdn.example/la1.m3u8",
        }]
        before = datetime.now(timezone.utc)
        collector.export_json()
        after = datetime.now(timezone.utc)
        published = datetime.fromisoformat(self.read_json("Spain", "LiveTV.json")["date"])
        self.assertGreaterEqual(published, before - timedelta(seconds=1))
        self.assertLessEqual(published, after + timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
