import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import load_records, latest_stations, retrieve, summary_facts, report_facts, make_context, validate_answer, current_status
from i18n import t
from map_view import map_payload, render_map

class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_records()
        root = Path(__file__).resolve().parents[1] / "data"
        cls.geo = {key:json.loads((root / filename).read_text()) for key,filename in {"states":"india_states.geojson", "districts":"districts.geojson", "blocks":"blocks.geojson"}.items()}

    def test_source_date_coverage_and_unique_observations(self):
        self.assertEqual(self.df.district.nunique(),36)
        self.assertEqual(self.df.station_key.nunique(),2360)
        self.assertFalse(self.df.duplicated(["station_key","date"]).any())
        self.assertEqual(str(self.df.date.max().date()),"2023-08-10")

    def test_districts_and_aliases_in_three_languages(self):
        cases = [("Compare Pune and Yavatmal",{"Pune","Yavatmal"}), ("पुणे और यवतमाल की तुलना करें",{"Pune","Yavatmal"}), ("पुण्याच्या नोंदी दाखवा",{"Pune"}), ("Dharashiv records",{"Osmanabad"}), ("Mumbai Suburban records",{"Mumbai Suburban"})]
        for question,expected in cases:
            with self.subTest(question=question):
                self.assertEqual(set(retrieve(self.df,question,"Yavatmal")["districts"]),expected)

    def test_no_unmeasured_current_or_future_answer(self):
        self.assertFalse(current_status(self.df)["supported"])
        self.assertEqual(retrieve(self.df,"What is the water level today?","Pune")["status"],"current")
        self.assertEqual(retrieve(self.df,"Predict next season","Yavatmal")["status"],"future")
        self.assertEqual(retrieve(self.df,"Pune records in 2026","Yavatmal")["status"],"year_missing")

    def test_unsupported_domain_does_not_borrow_another_district(self):
        for question in ["Is it safe to drink?", "Delhi records", "Which crop should I grow?"]:
            self.assertEqual(retrieve(self.df,question,"Yavatmal")["status"],"unsupported")

    def test_month_and_year_filters(self):
        result=retrieve(self.df,"Pune measurements in May 2023","Yavatmal")
        self.assertEqual(set(result["rows"].date.dt.year),{2023})
        self.assertEqual(set(result["rows"].date.dt.month),{5})

    def test_yearbook_is_separate_and_can_answer_2024(self):
        result=retrieve(self.df,"Yavatmal records in January 2024","Pune")
        self.assertEqual(result["status"],"ok")
        self.assertEqual(len(result["facts"]),1)
        self.assertEqual(result["facts"][0]["last_date"],"2024-01")
        self.assertIn("1687",result["facts"][0]["source"])
        full=report_facts("R1")
        self.assertEqual(full["station_count"],97)
        self.assertEqual(full["measurement_count"],369)

    def test_map_uses_shared_selection_and_language(self):
        stations=latest_stations(self.df[self.df.district.eq("Pune")])
        key=stations.iloc[0].station_key
        for language in ["English","Hindi","Marathi"]:
            payload=map_payload(self.df,self.geo,"Pune",key,language,"well")
            self.assertEqual(len([f for f in payload["districts"]["features"] if f["properties"]["selected"]]),1)
            selected=[p for p in payload["points"] if p["selected"]]
            self.assertEqual([p["id"] for p in selected],[key])
            self.assertEqual(payload["text"]["depth"],t("depth",language))
            html=render_map(payload)
            self.assertNotIn('<script src=',html)
            self.assertNotIn('tile.openstreetmap.org',html)

    def test_new_numbers_and_unknown_sources_are_rejected(self):
        facts=[summary_facts(self.df[self.df.district.eq("Yavatmal")],"Yavatmal")]
        lookup,_=make_context(facts)
        valid={"answer":"{{R1_label}} has {{R1_station_count}} stations. Last record: {{R1_last_date}}.","sources":["R1"]}
        self.assertIn("121 stations",validate_answer(valid,facts,lookup,"English"))
        for result in [
            {"answer":"It will be 12 metres deep today.","sources":["R1"]},
            {"answer":"{{R9_depth}}","sources":["R1"]},
            {"answer":"No data.","sources":["R9"]},
            {"answer":"{{R1_station_count}}","sources":[]},
        ]:
            with self.assertRaises(ValueError):validate_answer(result,facts,lookup,"English")

if __name__ == "__main__":
    unittest.main()
