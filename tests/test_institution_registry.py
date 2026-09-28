import copy
import json
import unittest
from unittest.mock import patch

from certocr import institution_registry as registry


class InstitutionRegistryTests(unittest.TestCase):
    def tearDown(self):
        registry._index.cache_clear()

    def test_current_snapshot_covers_all_designated_categories(self):
        snapshot = json.loads(registry.SNAPSHOT_PATH.read_text(encoding="utf-8"))
        groups = snapshot["groups"][:5]
        self.assertEqual([len(group["names"]) for group in groups], [14, 16, 12, 46, 254])
        names = [name for group in groups for name in group["names"]]
        self.assertEqual(len(set(names)), 342)
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(registry.lookup_career_institution(name)["status"], "matched")

    def test_public_enterprise_has_source_and_historical_checks(self):
        actual = registry.lookup_career_institution(" 한국 전력 공사 ")
        self.assertEqual(actual["canonical_name"], "한국전력공사")
        self.assertEqual(actual["suggested_type"], "pub5")
        self.assertEqual(actual["as_of"], "2026-02-12")
        self.assertIn("mofe.go.kr", actual["source_url"])
        self.assertTrue(any("근무 당시" in item for item in actual["required_checks"]))
        self.assertTrue(any("담당업무" in item for item in actual["required_checks"]))

    def test_enterprise_type_changed_in_2026_does_not_keep_old_suggestion(self):
        actual = registry.lookup_career_institution("한국방송광고진흥공사")
        self.assertEqual(actual["legal_form"], "기타공공기관")
        self.assertEqual(actual["suggested_type"], "")
        self.assertTrue(any("별도 인정" in item for item in actual["required_checks"]))
        self.assertEqual(registry.lookup_career_institution("한국법무보호복지공단")["suggested_type"], "pub5")

    def test_educational_foundation_directly_named_in_directive(self):
        actual = registry.lookup_career_institution("동북아역사재단")
        self.assertEqual(actual["legal_form"], "기타공공기관")
        self.assertEqual(actual["suggested_type"], "pub5")
        self.assertIn("law.go.kr", actual["recognition_source_url"])
        self.assertEqual(registry.lookup_career_institution("노사발전재단")["suggested_type"], "")

    def test_official_rename_with_explicit_statutory_succession(self):
        actual = registry.lookup_career_institution("한국직업능력연구원")
        self.assertEqual(actual["suggested_type"], "pub5")
        self.assertIn("law.go.kr", actual["rename_source_url"])

    def test_fuzzy_or_substring_matching_is_not_used(self):
        for name in ["한국전력공사 협력업체", "한국전력공사서비스", "주식회사 한국전력공사", "한전", "우리지역문화재단", "공공기관", "재단법인", "한국도로공사 직원"]:
            with self.subTest(name=name):
                self.assertEqual(registry.lookup_career_institution(name)["status"], "not_found")
        self.assertEqual(registry.lookup_career_institution("한국도로공사")["suggested_type"], "pub5")
        self.assertEqual(registry.lookup_career_institution("한국도로공사서비스(주)")["suggested_type"], "")

    def test_only_explicit_aliases_and_unicode_normalization(self):
        self.assertEqual(registry.lookup_career_institution("(주)강원랜드")["canonical_name"], "㈜강원랜드")
        self.assertEqual(registry.lookup_career_institution("주식회사 강원랜드")["canonical_name"], "㈜강원랜드")
        self.assertEqual(registry.lookup_career_institution("ＡＰＥＣ기후센터")["canonical_name"], "아시아·태평양경제협력체 기후센터")
        self.assertEqual(registry.lookup_career_institution("강원랜드")["status"], "not_found")

    def test_colliding_aliases_abstain(self):
        snapshot = json.loads(registry.SNAPSHOT_PATH.read_text(encoding="utf-8"))
        modified = copy.deepcopy(snapshot)
        modified["aliases"]["한국도로공사"] = ["중복기관명"]
        modified["aliases"]["한국전력공사"] = ["중복기관명"]
        registry._index.cache_clear()
        with patch.object(type(registry.SNAPSHOT_PATH), "read_text", return_value=json.dumps(modified)):
            actual = registry.lookup_career_institution("중복기관명")
        self.assertEqual(actual["status"], "ambiguous")
        self.assertEqual(actual["suggested_type"], "")

    def test_unavailable_or_bad_snapshot_never_recommends(self):
        for content in ["{", '{"groups": []}', '{"groups": [], "required_checks": 1}']:
            registry._index.cache_clear()
            with patch.object(type(registry.SNAPSHOT_PATH), "read_text", return_value=content):
                actual = registry.lookup_career_institution("한국전력공사")
            self.assertEqual(actual["status"], "not_found")
            self.assertEqual(actual["suggested_type"], "")

    def test_returned_checklist_is_independent(self):
        actual = registry.lookup_career_institution("한국전력공사")
        actual["required_checks"].clear()
        self.assertGreater(len(registry.lookup_career_institution("한국전력공사")["required_checks"]), 0)


if __name__ == "__main__":
    unittest.main()
