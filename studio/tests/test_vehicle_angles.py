import tempfile
import unittest
from pathlib import Path

from PIL import Image
from studio.lib.cinema import build_vehicle_sheet_prompt, split_vehicle_still


class VehicleAngleTests(unittest.TestCase):
    def test_prompt_requires_four_specific_views(self):
        prompt = build_vehicle_sheet_prompt("Black Phantom", "Red right mirror; black left mirror", has_ref=True)
        for requirement in ("2-by-2", "FRONT", "REAR", "RIGHT SIDE", "LEFT SIDE", "<Picture 1>", "Red right mirror"):
            self.assertIn(requirement, prompt)

    def test_grid_crops_preserve_order_and_every_pixel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sheet.png"
            image = Image.new("RGB", (101, 61))
            colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
            boxes = [(0, 0, 50, 30), (50, 0, 101, 30), (0, 30, 50, 61), (50, 30, 101, 61)]
            for color, box in zip(colors, boxes):
                image.paste(color, box)
            image.save(source)
            outputs = split_vehicle_still(source, root, "vehicle")
            self.assertEqual([p.stem for p in outputs], ["vehicle_front", "vehicle_rear", "vehicle_right", "vehicle_left"])
            area = 0
            for path, color in zip(outputs, colors):
                with Image.open(path) as part:
                    self.assertEqual(part.getpixel((0, 0)), color)
                    self.assertEqual(part.getpixel((part.width - 1, part.height - 1)), color)
                    area += part.width * part.height
            self.assertEqual(area, 101 * 61)


if __name__ == "__main__":
    unittest.main()
