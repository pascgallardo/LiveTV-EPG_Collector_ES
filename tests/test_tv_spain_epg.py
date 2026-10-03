"""Tests for the XMLTV merge in TV-Spain-EPG.py.

The merger is loaded by path because its filename is not a valid Python
identifier, and no test performs network I/O: `fetch_guide` is stubbed and the
guides are built inline. What is being pinned down is the filtering (only the
`tvg-id` of the published playlist survive), the deduplication across guides that
mirror each other, and the two properties that keep the output committable: the
nested elements of a kept programme are not lost, and the gzip container is a
pure function of the XML next to it.

Run with:
    python -m unittest discover -s tests -v
"""
import gzip
import importlib.util
import os
import pathlib
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "BugsfreeMain" / "TV-Spain-EPG.py"

def load_merger_module():
    """Import TV-Spain-EPG.py, whose filename cannot be used as a module name."""
    spec = importlib.util.spec_from_file_location("tv_spain_epg", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


epg = load_merger_module()


def channel(channel_id, names=("La 1",), icon=None):
    """An XMLTV `<channel>` with *names* as its display-name entries.

    *channel_id* is written as given, so a test that needs XML escaping passes
    the escaped form itself.
    """
    parts = [f'<channel id="{channel_id}">']
    for name in names:
        parts.append(f"<display-name>{name}</display-name>")
    if icon:
        parts.append(f'<icon src="{icon}" />')
    parts.append("</channel>")
    return "".join(parts)


def programme(channel_id, start, stop, title="Programa", desc=None):
    """An XMLTV `<programme>` with a title and, optionally, a description."""
    body = f"<title>{title}</title>"
    if desc is not None:
        body += f"<desc>{desc}</desc>"
    return (f'<programme start="{start}" stop="{stop}" channel="{channel_id}">'
            f"{body}</programme>")


def guide(*elements, generator="src"):
    """A complete XMLTV document wrapping *elements*."""
    body = "".join(elements)
    return f'<?xml version="1.0" encoding="UTF-8"?><tv generator-info-name="{generator}">{body}</tv>'


class MergerTestCase(unittest.TestCase):
    """Base case that keeps generated files out of the repository."""

    def setUp(self):
        # La estructura imita la del repositorio, con LiveTV/Spain dentro, para
        # que main() pueda probarse con sus rutas por defecto y sin parchear nada.
        self.repo_dir = tempfile.mkdtemp(prefix="tv-epg-tests-")
        self.addCleanup(shutil.rmtree, self.repo_dir, True)
        self.output_dir = os.path.join(self.repo_dir, "LiveTV")
        os.makedirs(os.path.join(self.output_dir, "Spain"), exist_ok=True)

    def make_merger(self, **kwargs):
        return epg.EPGMerger(base_dir=self.output_dir, **kwargs)

    def write_playlist(self, lines):
        path = os.path.join(self.output_dir, "Spain", "LiveTV.m3u")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def write_manifest(self, urls):
        import json
        path = os.path.join(self.output_dir, "Spain", "epg-sources.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"epg_urls": list(urls)}, f)
        return path

    def silence_logging(self):
        """The merger logs every step; on the tests that write files that is noise."""
        for level in ("debug", "info", "warning", "error"):
            patcher = mock.patch.object(epg.logging, level)
            patcher.start()
            self.addCleanup(patcher.stop)

    def path(self, *parts):
        return os.path.join(self.output_dir, "Spain", *parts)

    def read_bytes(self, name):
        with open(self.path(name), "rb") as f:
            return f.read()

    def parse(self, name="LiveTV.xml"):
        return ET.fromstring(self.read_bytes(name))

    @staticmethod
    def stub_fetch(merger, bodies):
        """Serve *bodies* instead of downloading, keyed by URL."""
        def fake_fetch(url):
            return bodies.get(url)
        merger.fetch_guide = fake_fetch


class TestGuideDiscovery(MergerTestCase):
    """Where the list of guides to merge comes from."""

    def test_reads_the_tvg_ids_of_the_playlist(self):
        self.write_playlist([
            '#EXTM3U url-tvg="https://g.example/a.xml"',
            '#EXTINF:-1 tvg-id="La1.es" group-title="G",La 1',
            "https://cdn.example/la1.m3u8",
            '#EXTINF:-1 tvg-id="La2.es" group-title="G",La 2',
            "https://cdn.example/la2.m3u8",
        ])
        _, wanted = self.make_merger().read_playlist()

        self.assertEqual(wanted, {"La1.es", "La2.es"})

    def test_channels_without_tvg_id_are_not_wanted(self):
        # There is nothing to match an EPG channel against, so such a channel can
        # never be kept and must not widen the filter.
        self.write_playlist([
            "#EXTM3U",
            '#EXTINF:-1 tvg-name="Sin id" group-title="G",Canal',
            "https://cdn.example/x.m3u8",
        ])
        _, wanted = self.make_merger().read_playlist()

        self.assertEqual(wanted, set())

    def test_a_repeated_tvg_id_is_wanted_once(self):
        self.write_playlist([
            "#EXTM3U",
            '#EXTINF:-1 tvg-id="La1.es",A', "https://cdn.example/a.m3u8",
            '#EXTINF:-1 tvg-id="La1.es",B', "https://cdn.example/b.m3u8",
        ])
        _, wanted = self.make_merger().read_playlist()

        self.assertEqual(wanted, {"La1.es"})

    def test_tvg_ids_are_trimmed_and_unescaped(self):
        # `Crimen&amp;Historia` is how some sources spell it; the guide writes
        # `Crimen&Historia`, and without the unescape the channel loses its guide.
        self.write_playlist([
            "#EXTM3U",
            '#EXTINF:-1 tvg-id="  Crimen&amp;Historia  ",C',
            "https://cdn.example/c.m3u8",
        ])
        _, wanted = self.make_merger().read_playlist()

        self.assertEqual(wanted, {"Crimen&Historia"})

    def test_a_missing_playlist_is_reported_rather_than_silently_empty(self):
        merger = self.make_merger()
        with self.assertRaises(FileNotFoundError):
            merger.read_playlist()

    def test_the_manifest_is_preferred_over_the_header(self):
        self.write_playlist(['#EXTM3U url-tvg="https://g.example/header.xml"'])
        self.write_manifest(["https://g.example/manifest.xml"])

        self.assertEqual(self.make_merger().source_urls(["https://g.example/header.xml"]),
                         ["https://g.example/manifest.xml"])

    def test_without_a_manifest_the_header_is_used(self):
        self.write_playlist(['#EXTM3U url-tvg="https://g.example/header.xml"'])

        self.assertEqual(self.make_merger().source_urls(["https://g.example/header.xml"]),
                         ["https://g.example/header.xml"])

    def test_the_header_fallback_ignores_the_merged_guide(self):
        # The circularity: the header advertises this merger's own output. Left
        # in, the merger would download its previous result and merge it again.
        merger = self.make_merger()
        merger.read_playlist = lambda: ([
            f"https://raw.githubusercontent.com/pascgallardo/LiveTV-EPG_Collector_ES/"
            f"refs/heads/main/LiveTV/Spain/{epg.OUTPUT_XML}.gz",
            "https://g.example/real.xml",
        ], {"La1.es"})

        self.assertEqual(merger.source_urls([
            "https://raw.githubusercontent.com/x/LiveTV/Spain/LiveTV.xml.gz",
            "https://raw.githubusercontent.com/x/LiveTV/Spain/LiveTV.xml",
            "https://g.example/real.xml",
        ]), ["https://g.example/real.xml"])

    def test_a_manifest_without_urls_is_ignored(self):
        import json
        with open(self.path("epg-sources.json"), "w", encoding="utf-8") as f:
            json.dump({"otra_cosa": []}, f)

        self.assertEqual(self.make_merger().source_urls(["https://g.example/h.xml"]),
                         ["https://g.example/h.xml"])

    def test_an_unreadable_manifest_is_ignored(self):
        with open(self.path("epg-sources.json"), "w", encoding="utf-8") as f:
            f.write("{esto no es json")

        self.assertEqual(self.make_merger().source_urls(["https://g.example/h.xml"]),
                         ["https://g.example/h.xml"])


class TestFetching(MergerTestCase):
    """Downloading the guides, compressed or not."""

    def response(self, content, status=200):
        resp = mock.Mock(status_code=status)
        resp.raise_for_status.return_value = None
        resp.content = content
        return resp

    def test_a_plain_xml_guide_is_returned_untouched(self):
        payload = guide(channel("La1.es")).encode()
        with mock.patch.object(epg.requests, "get", return_value=self.response(payload)):
            data = self.make_merger().fetch_guide("https://g.example/a.xml")

        self.assertEqual(data, payload)

    def test_a_gzipped_guide_is_decompressed(self):
        payload = guide(channel("La1.es")).encode()
        blob = gzip.compress(payload)
        with mock.patch.object(epg.requests, "get", return_value=self.response(blob)):
            data = self.make_merger().fetch_guide("https://g.example/a.xml.gz")

        self.assertEqual(data, payload)

    def test_decompression_does_not_rely_on_the_extension(self):
        # guiatv.xml and runtime.xml are plain .xml paths served gzipped, so the
        # magic bytes are the only dependable test.
        payload = guide(channel("La1.es")).encode()
        with mock.patch.object(epg.requests, "get", return_value=self.response(gzip.compress(payload))):
            data = self.make_merger().fetch_guide("https://g.example/a.xml")

        self.assertEqual(data, payload)

    def test_a_failing_guide_is_skipped_not_fatal(self):
        error = epg.requests.RequestException("404")
        with mock.patch.object(epg.requests, "get", side_effect=error):
            self.assertIsNone(self.make_merger().fetch_guide("https://g.example/gone.xml"))

    def test_an_empty_guide_is_rejected(self):
        with mock.patch.object(epg.requests, "get", return_value=self.response(b"   ")):
            self.assertIsNone(self.make_merger().fetch_guide("https://g.example/empty.xml"))

    def test_fetch_guides_keep_the_declared_order(self):
        # Downloads finish in whatever order they like; the merge depends on the
        # declared order to decide which guide owns a channel.
        urls = ["https://g.example/slow.xml", "https://g.example/fast.xml"]
        bodies = dict(zip(urls, [guide(channel("A")), guide(channel("B"))]))
        merger = self.make_merger()
        self.stub_fetch(merger, bodies)

        fetched = merger.fetch_guides(urls)
        self.assertEqual(fetched, [bodies[urls[0]], bodies[urls[1]]])

    def test_fetch_guides_drop_the_ones_that_failed(self):
        urls = ["https://g.example/ok.xml", "https://g.example/gone.xml"]
        bodies = {urls[0]: guide(channel("A"))}
        merger = self.make_merger()
        self.stub_fetch(merger, bodies)

        self.assertEqual(merger.fetch_guides(urls), [bodies[urls[0]]])


class TestFiltering(MergerTestCase):
    """Only the tvg-id of the published playlist reach the merged guide."""

    def merge(self, guides, wanted):
        return self.make_merger().merge([g.encode() for g in guides], set(wanted))

    def test_only_wanted_channels_survive(self):
        channels, _ = self.merge(
            [guide(channel("La1.es"), channel("Forge.es"), channel("La2.es"))],
            ["La1.es", "La2.es"])

        self.assertEqual([c.get("id") for c in channels], ["La1.es", "La2.es"])

    def test_only_programmes_of_wanted_channels_survive(self):
        _, programmes = self.merge([guide(
            programme("La1.es", "20260101000000 +0000", "20260101010000 +0000"),
            programme("Forge.es", "20260101000000 +0000", "20260101010000 +0000"),
        )], ["La1.es"])

        self.assertEqual([p.get("channel") for p in programmes], ["La1.es"])

    def test_a_guide_without_any_wanted_channel_yields_nothing(self):
        channels, programmes = self.merge([guide(
            channel("Forge.es"), programme("Forge.es", "a", "b"))], ["La1.es"])

        self.assertEqual((channels, programmes), ([], []))

    def test_a_channel_keeps_its_names_and_icon(self):
        channels, _ = self.merge(
            [guide(channel("La1.es", names=("La 1", "La Uno"), icon="https://i.example/l.png"))],
            ["La1.es"])

        self.assertEqual([d.text for d in channels[0].findall("display-name")],
                         ["La 1", "La Uno"])
        self.assertEqual(channels[0].find("icon").get("src"), "https://i.example/l.png")

    def test_the_playlist_escaped_id_still_matches_its_guide(self):
        # End to end, because the unescape lives in read_playlist: the playlist
        # spells the id `Crimen&amp;Historia` and the guide spells it
        # `Crimen&Historia`, and without the unescape that channel loses its guide.
        self.write_playlist([
            "#EXTM3U",
            '#EXTINF:-1 tvg-id="Crimen&amp;Historia",C',
            "https://cdn.example/c.m3u8",
        ])
        merger = self.make_merger()
        _, wanted = merger.read_playlist()

        channels, _ = merger.merge(
            [guide(channel("Crimen&amp;Historia")).encode()], wanted)

        self.assertEqual([c.get("id") for c in channels], ["Crimen&Historia"])

    def test_namespaces_do_not_hide_the_elements(self):
        payload = ('<tv xmlns="urn:some:xmltv">'
                   '<channel id="La1.es"><display-name>La 1</display-name></channel>'
                   '</tv>')
        channels, _ = self.merge([payload], ["La1.es"])

        self.assertEqual([c.get("id") for c in channels], ["La1.es"])

    def test_a_malformed_guide_is_skipped_without_failing_the_run(self):
        good = guide(channel("La1.es"))
        channels, _ = self.merge([good, "<tv><channel id=\""], ["La1.es"])

        self.assertEqual([c.get("id") for c in channels], ["La1.es"])


class TestDeduplication(MergerTestCase):
    """Mirrored guides must not repeat the same channel or the same slot."""

    def merge(self, guides, wanted):
        return self.make_merger().merge([g.encode() for g in guides], set(wanted))

    def test_a_channel_offered_by_two_guides_is_emitted_once(self):
        # guiatv.xml and the s2l workers both carry the national channels.
        channels, _ = self.merge([
            guide(channel("La1.es"), generator="a"),
            guide(channel("La1.es"), generator="b"),
        ], ["La1.es"])

        self.assertEqual(len(channels), 1)

    def test_the_first_guide_to_declare_a_channel_owns_it(self):
        channels, _ = self.merge([
            guide(channel("La1.es", icon="https://i.example/first.png"), generator="a"),
            guide(channel("La1.es", icon="https://i.example/second.png"), generator="b"),
        ], ["La1.es"])

        self.assertEqual(channels[0].find("icon").get("src"),
                         "https://i.example/first.png")

    def test_the_same_slot_offered_by_two_guides_is_emitted_once(self):
        slot = ("20260101000000 +0000", "20260101010000 +0000")
        _, programmes = self.merge([
            guide(programme("La1.es", *slot, title="Noticiario"), generator="a"),
            guide(programme("La1.es", *slot, title="Noticiario"), generator="b"),
        ], ["La1.es"])

        self.assertEqual(len(programmes), 1)

    def test_different_slots_of_one_channel_are_all_kept(self):
        _, programmes = self.merge([guide(
            programme("La1.es", "20260101000000 +0000", "20260101010000 +0000"),
            programme("La1.es", "20260101010000 +0000", "20260101020000 +0000"),
        )], ["La1.es"])

        self.assertEqual(len(programmes), 2)

    def test_guides_covering_different_ranges_both_contribute(self):
        _, programmes = self.merge([
            guide(programme("La1.es", "20260101000000 +0000", "20260101010000 +0000",
                            title="Madrugada"), generator="a"),
            guide(programme("La1.es", "20260101010000 +0000", "20260101020000 +0000",
                            title="Dia"), generator="b"),
        ], ["La1.es"])

        self.assertEqual([p.findtext("title") for p in programmes],
                         ["Madrugada", "Dia"])

    def test_the_same_slot_on_different_channels_is_kept(self):
        slot = ("20260101000000 +0000", "20260101010000 +0000")
        _, programmes = self.merge([guide(
            programme("La1.es", *slot), programme("La2.es", *slot))],
            ["La1.es", "La2.es"])

        self.assertEqual(len(programmes), 2)


class TestKeptContent(MergerTestCase):
    """A kept programme must keep its title and description.

    This is the regression that the filtering loop is easiest to get wrong:
    `iterparse` reports a child element's end before its parent's, so clearing
    every element as it arrives empties each programme before it is ever read,
    and the merge ends up publishing tens of thousands of blank entries.
    """

    def merge_one(self, payload, wanted=("La1.es",)):
        return self.make_merger().merge([payload.encode()], set(wanted))

    def test_a_kept_programme_keeps_its_title(self):
        _, programmes = self.merge_one(guide(
            programme("La1.es", "a", "b", title="El Noticias") ))

        self.assertEqual(programmes[0].findtext("title"), "El Noticias")

    def test_a_kept_programme_keeps_its_description(self):
        _, programmes = self.merge_one(guide(
            programme("La1.es", "a", "b", title="T", desc="La descripción")))

        self.assertEqual(programmes[0].findtext("desc"), "La descripción")

    def test_a_kept_programme_keeps_several_child_elements(self):
        payload = ('<tv><programme start="a" stop="b" channel="La1.es">'
                   "<title lang=\"es\">T</title><sub-title>S</sub-title>"
                   "<episode-num system=\"xmltv_ns\">1.2.</episode-num>"
                   "<category>Noticias</category></programme></tv>")
        _, programmes = self.merge_one(payload)

        self.assertEqual(programmes[0].findtext("sub-title"), "S")
        self.assertEqual(programmes[0].findtext("episode-num"), "1.2.")
        self.assertEqual(programmes[0].findtext("category"), "Noticias")

    def test_a_rejected_programme_does_not_leak_its_text_into_the_output(self):
        channels, programmes = self.make_merger().merge([guide(
            programme("Forge.es", "a", "b", title="Secreto"),
            programme("La1.es", "a", "b", title="Público"),
        ).encode()], {"La1.es"})

        titles = [p.findtext("title") for p in programmes]
        self.assertNotIn("Secreto", titles)

    def test_channel_metadata_survives_the_filter(self):
        channels, _ = self.merge_one(guide(
            channel("La1.es", names=("La 1",), icon="https://i.example/l.png")))

        self.assertEqual(channels[0].findtext("display-name"), "La 1")


class TestOutput(MergerTestCase):
    """The two published files, and what makes them reproducible."""

    def setUp(self):
        super().setUp()
        self.silence_logging()

    def build(self, wanted=("La1.es",)):
        """Merge one small guide and write it; returns both output paths."""
        merger = self.make_merger()
        channels, programmes = merger.merge([guide(
            channel("La1.es"),
            programme("La1.es", "20260101000000 +0000", "20260101010000 +0000",
                      title="El Noticias", desc="Resumen"),
        ).encode()], set(wanted))
        return merger.write(merger.build_document(channels, programmes))

    def test_both_files_are_written(self):
        xml_path, gz_path = self.build()

        self.assertTrue(os.path.isfile(xml_path))
        self.assertTrue(os.path.isfile(gz_path))
        self.assertEqual(os.path.basename(gz_path), "LiveTV.xml.gz")

    def test_the_compressed_file_holds_exactly_the_plain_one(self):
        xml_path, gz_path = self.build()
        with gzip.open(gz_path, "rb") as f:
            self.assertEqual(f.read(), self.read_bytes("LiveTV.xml"))

    def test_the_gzip_container_carries_no_timestamp(self):
        # Without mtime 0 two runs over the same guides would commit two
        # different blobs for identical data.
        self.build()
        header = self.read_bytes("LiveTV.xml.gz")[:10]

        self.assertEqual(int.from_bytes(header[4:8], "little"), 0)

    def test_the_gzip_container_carries_no_filename(self):
        self.build()
        header = self.read_bytes("LiveTV.xml.gz")[:10]

        self.assertFalse(header[3] & 0x08, "FNAME flag must be off")

    def test_two_identical_merges_produce_identical_files(self):
        merger = self.make_merger()
        payload = guide(
            channel("La1.es"),
            programme("La1.es", "20260101000000 +0000", "20260101010000 +0000"),
        ).encode()
        first = merger.build_document(*merger.merge([payload], {"La1.es"}))
        merger.write(first)
        before = (self.read_bytes("LiveTV.xml"), self.read_bytes("LiveTV.xml.gz"))

        second = merger.build_document(*merger.merge([payload], {"La1.es"}))
        merger.write(second)

        self.assertEqual((self.read_bytes("LiveTV.xml"), self.read_bytes("LiveTV.xml.gz")),
                         before)

    def test_the_document_is_valid_xmltv(self):
        self.build()
        root = self.parse()

        self.assertEqual(root.tag, "tv")
        self.assertEqual([c.tag for c in root][:2], ["channel", "programme"])

    def test_the_sources_generator_claim_is_not_repeated(self):
        self.build()
        root = self.parse()

        self.assertEqual(root.get("generator-info-name"), "LiveTVCollectorES EPG merger")

    def test_the_document_carries_no_publication_timestamp(self):
        # The instant is in the commit and in LiveTV.json; stamping the file would
        # make two runs over the same guides differ for no reason.
        self.build()
        self.assertIsNone(self.parse().get("generated-at"))


class TestMain(MergerTestCase):
    """The command line entry point, end to end with stubbed downloads."""

    def setUp(self):
        super().setUp()
        self.write_playlist([
            '#EXTM3U url-tvg="https://g.example/a.xml"',
            '#EXTINF:-1 tvg-id="La1.es" group-title="G",La 1',
            "https://cdn.example/la1.m3u8",
        ])
        self.write_manifest(["https://g.example/a.xml", "https://g.example/gone.xml"])
        self.bodies = {"https://g.example/a.xml": guide(
            channel("La1.es"),
            programme("La1.es", "20260101000000 +0000", "20260101010000 +0000"),
        ).encode()}

    def run_main(self, capture_logs=False):
        """Run main() as the workflow does: from the repository root, no network.

        The base directory is injected rather than changed so the test can still
        reach its fixtures, but everything else is the real entry point reading
        the real `LiveTV/Spain` layout.
        """
        original_init = epg.EPGMerger.__init__

        def patched_init(self_, **kwargs):
            kwargs.setdefault("base_dir", self.output_dir)
            original_init(self_, **kwargs)
            self_.fetch_guide = lambda url: self.bodies.get(url)

        cwd = os.getcwd()
        os.chdir(self.repo_dir)
        self.addCleanup(os.chdir, cwd)
        with mock.patch.object(epg.EPGMerger, "__init__", patched_init), \
             mock.patch.object(epg.requests, "get",
                               side_effect=AssertionError("no network in tests")):
            if not capture_logs:
                self.silence_logging()
                return epg.main([])
            with self.assertLogs(level="DEBUG") as captured:
                code = epg.main([])
        return code, "\n".join(captured.output)

    def test_a_healthy_run_publishes_and_succeeds(self):
        self.assertEqual(self.run_main(), 0)
        self.assertTrue(os.path.isfile(self.path("LiveTV.xml")))
        self.assertTrue(os.path.isfile(self.path("LiveTV.xml.gz")))

    def test_one_failing_guide_does_not_fail_the_run(self):
        self.assertEqual(self.run_main(), 0)

    def test_the_published_guide_holds_the_playlist_channels(self):
        self.run_main()
        root = self.parse()

        self.assertEqual([c.get("id") for c in root.findall("channel")], ["La1.es"])
        self.assertEqual([p.get("channel") for p in root.findall("programme")], ["La1.es"])

    def test_every_guide_failing_leaves_the_published_guide_untouched(self):
        # Publishing an empty guide would replace a good file with a broken one.
        self.bodies = {}
        with open(self.path("LiveTV.xml"), "w", encoding="utf-8") as f:
            f.write("<tv>previo</tv>")

        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.read_bytes("LiveTV.xml"), b"<tv>previo</tv>")

    def test_a_total_download_failure_is_reported_as_such(self):
        # Both this and an over-narrow filter end in an empty merge, but whoever
        # reads the log has to be told which of the two actually happened.
        self.bodies = {}
        _, logs = self.run_main(capture_logs=True)

        self.assertIn("failed to download", logs)
        self.assertNotIn("No channel of the playlist was found", logs)

    def test_a_filter_that_keeps_nothing_leaves_the_guide_untouched(self):
        self.bodies = {"https://g.example/a.xml": guide(channel("Forge.es")).encode()}
        with open(self.path("LiveTV.xml"), "w", encoding="utf-8") as f:
            f.write("<tv>previo</tv>")

        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.read_bytes("LiveTV.xml"), b"<tv>previo</tv>")

    def test_a_filter_that_keeps_nothing_is_reported_as_such(self):
        self.bodies = {"https://g.example/a.xml": guide(channel("Forge.es")).encode()}
        _, logs = self.run_main(capture_logs=True)

        self.assertIn("No channel of the playlist was found", logs)

    def test_a_playlist_with_no_guides_fails(self):
        os.remove(self.path("epg-sources.json"))
        self.write_playlist(["#EXTM3U"])

        self.assertEqual(self.run_main(), 1)

    def test_a_missing_playlist_fails(self):
        os.remove(self.path("LiveTV.m3u"))

        self.assertEqual(self.run_main(), 1)


if __name__ == "__main__":
    unittest.main()
