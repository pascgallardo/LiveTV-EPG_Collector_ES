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
from datetime import datetime, timezone
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
    """The #EXTM3U url-tvg header carries the EPG URLs of the merged sources.

    `url-tvg` points at XMLTV guide data, never at the M3U sources themselves,
    so the header is built from the EPG URLs each source declared.
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

    def header_of_source(self, *header_lines):
        """Feed *header_lines* as a source playlist and return the merged header."""
        collector = self.make_collector()
        body = ['#EXTINF:-1 group-title="Generalistas",La 1', "https://cdn.example/la1.m3u8"]
        with mock.patch.object(tv.M3UCollector, "fetch_content", return_value=(None, list(header_lines) + body)):
            collector.process_sources(["https://source.example/list.m3u"])
        collector.export_m3u()
        return self.read_text("Spain", "LiveTV.m3u").splitlines()[0]

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
        lines = [f'#EXTM3U url-tvg="{self.EPG_A}"', '#EXTINF:-1 group-title="G",C', "https://x.example/s.m3u8"]
        self.assertEqual(tv.M3UCollector.epg_urls_from_header(lines), [self.EPG_A])

    def test_header_carries_the_epg_urls_of_the_sources(self):
        header = self.header_of_source(f'#EXTM3U url-tvg="{self.EPG_A}, {self.EPG_B}"')
        self.assertEqual(header, f'#EXTM3U url-tvg="{self.EPG_A}, {self.EPG_B}"')

    def test_several_sources_are_merged_in_order(self):
        collector = self.make_collector()
        body = ['#EXTINF:-1 group-title="G",C', "https://cdn.example/c.m3u8"]
        def fake_fetch(self, url):
            return (None, [f'#EXTM3U url-tvg="{url}"]'] + body)
        with mock.patch.object(tv.M3UCollector, "fetch_content", fake_fetch):
            collector.process_sources(["https://a.example/a.m3u", "https://b.example/b.m3u"])
        collector.export_m3u()
        header = self.read_text("Spain", "LiveTV.m3u").splitlines()[0]
        self.assertEqual(header, '#EXTM3U url-tvg="https://a.example/a.m3u, https://b.example/b.m3u"')

    def test_a_guide_shared_by_two_sources_is_listed_once(self):
        header = self.header_with(self.EPG_A, self.EPG_B, self.EPG_A)
        self.assertEqual(header.count(self.EPG_A), 1)
        self.assertEqual(header, f'#EXTM3U url-tvg="{self.EPG_A}, {self.EPG_B}"')

    def test_header_stays_bare_without_epg(self):
        self.assertEqual(self.header_with(), "#EXTM3U")

    def test_the_header_never_lists_an_m3u_source(self):
        # The source URL is an .m3u; it must not reach url-tvg.
        header = self.header_of_source(f'#EXTM3U url-tvg="{self.EPG_A}"')
        self.assertNotIn("list.m3u", header)

    def test_epg_is_cleared_between_runs(self):
        collector = self.make_collector()
        collector.epg_urls = [self.EPG_A]
        collector.process_sources([])
        self.assertEqual(collector.epg_urls, [])

    def test_the_exported_header_parses_back(self):
        header = self.header_with(self.EPG_A, self.EPG_B)
        self.assertEqual(tv.M3UCollector.extinf_attribute(header, "url-tvg"),
                         f"{self.EPG_A}, {self.EPG_B}")

    def test_stream_entries_still_follow_the_header(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.epg_urls = [self.EPG_A]
        collector.export_m3u()
        lines = self.read_text("Spain", "LiveTV.m3u").splitlines()
        self.assertTrue(lines[0].startswith("#EXTM3U "))
        self.assertTrue(lines[1].startswith("#EXTINF:"))
        self.assertEqual(lines[2], "https://cdn.example/la1.m3u8")


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
        # Inserted in reverse alphabetical order so the exports must actually sort them.
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
        # Groups are exported in alphabetical order, so Deportes comes before Generalistas.
        self.assertIn('tvg-logo="logo-ser"', lines[1])
        self.assertIn('group-title="Deportes"', lines[1])
        self.assertTrue(lines[1].endswith(",Cadena Ser"))
        self.assertIn('tvg-logo="logo-la1"', lines[3])
        self.assertIn('group-title="Generalistas"', lines[3])
        self.assertTrue(lines[3].endswith(",La 1"))

    def test_channels_are_sorted_in_every_format(self):
        collector = self.make_collector()
        self.populate(collector)
        collector.export_m3u()
        collector.export_txt()
        collector.export_json()
        collector.export_custom()
        m3u = self.read_text("Spain", "LiveTV.m3u")
        self.assertLess(m3u.index("Cadena Ser"), m3u.index("La 1"))
        self.assertLess(m3u.index("La 1"), m3u.index("Telecinco"))

        data = self.read_json("Spain", "LiveTV.json")
        self.assertEqual(list(data["channels"]), ["Deportes", "Generalistas"])
        self.assertEqual(
            [channel["name"] for channel in data["channels"]["Generalistas"]],
            ["La 1", "Telecinco"],
        )

        custom = self.read_json("Spain", "LiveTV")
        self.assertEqual([entry["name"] for entry in custom], ["Cadena Ser", "La 1", "Telecinco"])

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
    """The published `date` must be Madrid time, not some upstream default.

    The collector runs at 12:00 Europe/Madrid, so a timestamp in any other
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
        # 10:00 UTC is 12:00 in Madrid during CEST.
        now = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(self.export_with_now(now), "2026-07-15T12:00:00+02:00")

    def test_timestamp_is_madrid_time_in_winter(self):
        # 11:00 UTC is 12:00 in Madrid during CET.
        now = datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)
        self.assertEqual(self.export_with_now(now), "2026-01-15T12:00:00+01:00")

    def test_timestamp_is_not_the_collector_local_timezone(self):
        # The same instant expressed in Asia/Kolkata would be 17:30; the fix must
        # not depend on whatever timezone the machine running the script has.
        now = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        self.assertNotIn("17:30", self.export_with_now(now))

    def test_timestamp_carries_an_explicit_offset(self):
        # Without the offset, `new Date(...)` in the browser would silently
        # interpret the value in the visitor's timezone.
        now = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(self.export_with_now(now).endswith("+02:00"))

    def test_timestamp_parses_back_to_the_same_instant(self):
        now = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        published = self.export_with_now(now)
        self.assertEqual(datetime.fromisoformat(published), now)


if __name__ == "__main__":
    unittest.main()
