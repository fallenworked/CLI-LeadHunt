"""Базовые тесты Lead Hunter без обращения к сети."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.deduplicator import deduplicate, fingerprint
from core.dictionaries import find_niche
from core.engine import LeadEngine
from core.filters import FilterSpec, apply_filters
from core.geocoder import Geocoder
from core.models import CityInfo, Lead, SearchParams, SearchStats
from core.parser import build_overpass_query, parse_overpass_elements
from core.settings import Settings
from database.storage import Storage
from exporters.csv_export import CSV_COLUMNS, export_csv
from exporters.html_export import export_html
from sources.base import SourceResult


CITY = CityInfo("Москва", 55.7558, 37.6173, "RU", "Россия", "", 5000, "dictionary")

SAMPLE_ELEMENTS = [
    {
        "type": "node",
        "id": 101,
        "lat": 55.7600,
        "lon": 37.6200,
        "tags": {
            "name": "Улыбка",
            "amenity": "dentist",
            "phone": "+7 999 111-22-33",
            "addr:street": "Тверская",
            "addr:housenumber": "10",
            "opening_hours": "Mo-Fr 09:00-20:00",
            "contact:vk": "https://vk.com/ulybka",
        },
    },
    {
        "type": "node",
        "id": 102,
        "lat": 55.7610,
        "lon": 37.6210,
        "tags": {
            "name": "Сайт-клиника",
            "amenity": "dentist",
            "website": "https://example.com",
        },
    },
    {"type": "node", "id": 103, "tags": {"amenity": "dentist"}},
]


class FakeSource:
    id = "fake"
    name = "Fake source"

    def __init__(self, leads, fail: bool = False) -> None:
        self.leads = leads
        self.fail = fail

    def search(self, city, params, progress=None, cancel=None):
        if self.fail:
            raise RuntimeError("источник недоступен")
        return SourceResult(
            source_id=self.id,
            source_name=self.name,
            leads=list(self.leads),
            raw_elements=len(self.leads),
            elapsed_ms=12,
        )


class ParserTests(unittest.TestCase):
    def test_parse_filters_nameless_and_keeps_contacts(self):
        leads = parse_overpass_elements(SAMPLE_ELEMENTS, "OSM", CITY, "стоматология")
        self.assertEqual(len(leads), 2)
        lead = leads[0]
        self.assertEqual(lead.name, "Улыбка")
        self.assertEqual(lead.phone, "+7 999 111-22-33")
        self.assertEqual(lead.address, "Тверская 10")
        self.assertEqual(lead.lead_type, "dentist")
        self.assertEqual(lead.extra["contacts"]["vk"], "https://vk.com/ulybka")
        self.assertAlmostEqual(lead.lat, 55.76)

    def test_website_lead_is_filtered_by_default(self):
        leads = parse_overpass_elements(SAMPLE_ELEMENTS, "OSM", CITY, "стоматология")
        result, reasons = apply_filters(leads, FilterSpec())
        self.assertEqual([lead.name for lead in result], ["Улыбка"])
        self.assertEqual(reasons.get("Есть сайт"), 1)

    def test_include_website(self):
        leads = parse_overpass_elements(SAMPLE_ELEMENTS, "OSM", CITY, "стоматология")
        result, _ = apply_filters(leads, FilterSpec(include_website=True))
        self.assertEqual(len(result), 2)

    def test_keyword_filter(self):
        leads = parse_overpass_elements(SAMPLE_ELEMENTS, "OSM", CITY, "стоматология")
        result, reasons = apply_filters(leads, FilterSpec(include_website=True, keywords="улыбка"))
        self.assertEqual([lead.name for lead in result], ["Улыбка"])
        self.assertEqual(reasons.get("Не совпало по ключевым словам"), 1)

    def test_query_for_niche_and_custom(self):
        query = build_overpass_query(CITY, "стоматология", radius=5000, limit=100)
        self.assertIn('node["amenity"="dentist"]', query)
        self.assertIn("out center", query)
        custom = build_overpass_query(CITY, "", keywords="кофейня", radius=1000, limit=20)
        self.assertIn('node["name"~"кофейня",i]', custom)

    def test_query_requires_keyword(self):
        with self.assertRaises(ValueError):
            build_overpass_query(CITY, "", keywords="", radius=1000, limit=20)

    def test_niche_aliases(self):
        self.assertEqual(find_niche("кофейня").key, "кафе")
        self.assertEqual(find_niche("стоматолог").key, "стоматология")


class DedupTests(unittest.TestCase):
    def test_same_geo_and_name_dedup_and_merge(self):
        first = Lead(source="OSM", source_id="node/1", name="Тест", lat=55.7501, lon=37.6101)
        second = Lead(
            source="OSM",
            source_id="node/2",
            name="тест",
            lat=55.7502,
            lon=37.6102,
            phone="+79990000000",
            extra={"contacts": {"vk": "x"}},
        )
        unique, duplicates = deduplicate([first, second])
        self.assertEqual(duplicates, 1)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0].phone, "+79990000000")
        self.assertEqual(unique[0].extra["contacts"]["vk"], "x")
        self.assertEqual(len(fingerprint(unique[0])), 40)


class GeocoderTests(unittest.TestCase):
    def test_dictionary_city(self):
        city = Geocoder().resolve("Москва", radius=7000)
        self.assertIsNotNone(city)
        self.assertEqual(city.name, "Москва")
        self.assertEqual(city.country_code, "RU")
        self.assertEqual(city.radius, 7000)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _lead(self, name="Клиника", phone="+79990000000", lat=55.75, lon=37.62):
        return Lead(
            source="OSM",
            source_id="node/1",
            name=name,
            phone=phone,
            city="Москва",
            niche="стоматология",
            lat=lat,
            lon=lon,
        )

    def test_settings_roundtrip(self):
        settings = Settings(self.storage)
        settings.set("default_city", "Казань")
        settings.set("page_size", 22)
        self.assertEqual(settings.get("default_city"), "Казань")
        self.assertEqual(settings.get_int("page_size"), 22)

    def test_save_dedup_between_searches(self):
        first = self.storage.create_search(SearchParams(city="Москва", niche="стоматология"))
        saved = self.storage.save_leads(first, [self._lead()])
        self.assertEqual(saved, {"new": 1, "duplicates": 0, "saved": 1})
        lead = self._lead()
        second = self.storage.create_search(SearchParams(city="Москва", niche="стоматология"))
        saved = self.storage.save_leads(second, [lead])
        self.assertEqual(saved["new"], 0)
        self.assertEqual(saved["duplicates"], 1)
        self.assertEqual(self.storage.count_leads(), 1)
        self.assertEqual(self.storage.count_leads({"search_id": first}), 1)
        self.assertEqual(self.storage.count_leads({"search_id": second}), 1)

    def test_status_notes_and_search(self):
        search_id = self.storage.create_search(SearchParams(city="Москва", niche="стоматология"))
        lead = self._lead()
        self.storage.save_leads(search_id, [lead])
        lead_id = int(lead.db_id)
        self.storage.update_lead_status(lead_id, "contacted")
        self.storage.update_lead_notes(lead_id, "позвонить завтра")
        loaded = self.storage.get_lead(lead_id)
        self.assertEqual(loaded["status"], "contacted")
        self.assertIn("завтра", loaded["notes"])
        self.assertEqual(self.storage.count_leads({"query": "позвонить"}), 1)
        self.assertEqual(self.storage.count_leads({"query": "Клиника"}), 1)

    def test_history_and_stats(self):
        params = SearchParams(city="Москва", niche="стоматология")
        search_id = self.storage.create_search(params)
        stats = SearchStats(raw_found=3, after_dedup=2, saved=1, new_leads=1)
        self.storage.finish_search(search_id, stats, ["test error"], 1500, "ok", city=CITY)
        history = self.storage.list_searches()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["errors"], ["test error"])
        self.assertEqual(history[0]["duration_ms"], 1500)
        totals = self.storage.stats()
        self.assertEqual(totals["searches"], 1)
        self.assertEqual(totals["found_total"], 3)

    def test_delete_lead_and_history(self):
        search_id = self.storage.create_search(SearchParams(city="Москва", niche="стоматология"))
        lead = self._lead()
        self.storage.save_leads(search_id, [lead])
        self.storage.delete_lead(int(lead.db_id))
        self.assertEqual(self.storage.count_leads(), 0)
        self.storage.delete_search(search_id)
        self.assertEqual(len(self.storage.list_searches()), 0)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "engine.db")
        self.settings = Settings(self.storage)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def test_engine_survives_one_failed_source(self):
        lead = Lead(
            source="Fake",
            source_id="node/1",
            name="Тестовая клиника",
            phone="+79990000000",
            lat=55.75,
            lon=37.62,
        )
        engine = LeadEngine(
            self.storage,
            self.settings,
            sources=[FakeSource([], fail=True), FakeSource([lead])],
        )
        events = []
        outcome = engine.search(
            SearchParams(city="Москва", niche="стоматология", limit=50),
            progress=events.append,
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.stats.saved, 1)
        self.assertEqual(outcome.stats.new_leads, 1)
        self.assertTrue(any("источник недоступен" in item for item in outcome.errors))
        self.assertEqual(self.storage.count_leads(), 1)
        self.assertTrue(any(event.get("type") == "source_error" for event in events))
        self.assertTrue(any(event.get("type") == "done" for event in events))

    def test_engine_unknown_city_does_not_crash(self):
        engine = LeadEngine(self.storage, self.settings, sources=[FakeSource([])])
        outcome = engine.search(
            SearchParams(city="", niche="стоматология", limit=10),
            progress=lambda event: None,
        )
        self.assertEqual(outcome.status, "error")
        self.assertTrue(outcome.errors)
        self.assertEqual(self.storage.count_leads(), 0)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rows = [
            {
                "id": 1,
                "name": "Клиника <script>alert(1)</script>",
                "phone": "+7 999 111-22-33",
                "email": "a@example.com",
                "address": "Тверская 1",
                "city": "Москва",
                "region": "",
                "country": "Россия",
                "niche": "стоматология",
                "lead_type": "dentist",
                "opening_hours": "09:00-20:00",
                "website": "",
                "source": "OpenStreetMap / Overpass",
                "status": "new",
                "keywords": "",
                "found_at": "2026-01-01T10:00:00+03:00",
                "notes": "",
                "lat": 55.75,
                "lon": 37.62,
                "extra": {"contacts": {"vk": "https://vk.com/test"}},
            }
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_csv_export(self):
        path = export_csv(self.rows, Path(self.tmp.name) / "leads.csv")
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertIn(";".join(CSV_COLUMNS), text)
        self.assertIn("Клиника", text)
        self.assertIn("+7 999 111-22-33", text)

    def test_html_export_is_standalone_and_escaped(self):
        path = export_html(self.rows, Path(self.tmp.name) / "report.html", title="Тест")
        text = path.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("LEAD <span>HUNTER</span>", text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("id=\"fCity\"", text)
        self.assertIn("function apply()", text)
        self.assertIn("OpenStreetMap contributors", text)
        self.assertNotIn("http://cdn", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
