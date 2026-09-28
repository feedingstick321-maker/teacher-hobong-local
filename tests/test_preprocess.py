from __future__ import annotations

import unittest
from PIL import Image, ImageDraw

from certocr.preprocess import fallback_variants, image_features


class PreprocessTests(unittest.TestCase):
    def test_variants_keep_size_and_are_distinct(self):
        image = Image.new("RGB", (240, 160), "white")
        ImageDraw.Draw(image).text((20, 50), "경력 2025.3.1", fill="gray")
        variants = fallback_variants(image)
        self.assertEqual([x[0] for x in variants], ["clahe_otsu", "clahe_adaptive"])
        self.assertTrue(all(x[1].size == image.size for x in variants))
        self.assertIn("laplacian_var", image_features(image))


if __name__ == "__main__":
    unittest.main()
