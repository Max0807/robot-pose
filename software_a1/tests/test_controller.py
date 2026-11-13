import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import run_route
from protocol import load_route

ROOT = Path(__file__).resolve().parents[1]


class ControllerTests(unittest.TestCase):
    def test_example_route_is_valid_and_configurable_per_segment(self):
        route = load_route(ROOT / 'path.example.json')
        self.assertEqual(len(route.segments), 4)
        self.assertEqual(route.initial_position.y, 0.2)
        self.assertNotEqual(route.segments[0].speed, route.segments[1].speed)

    def test_whole_config_is_checked_before_network_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            data = load_route(ROOT / 'path.example.json').model_dump()
            data['segments'][-1]['speed'] = -1
            path.write_text(json.dumps(data), encoding='utf-8')
            with patch('controller.request_json') as request, self.assertRaises(ValueError):
                run_route('http://127.0.0.1:8000', path, 1, 1, {'commands': []})
            request.assert_not_called()

    def test_invalid_speed_multiplier_exits_with_error(self):
        process = subprocess.run([sys.executable, str(ROOT / 'controller.py'), '--speed-scale', '0'],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(process.returncode, 2)

    def test_invalid_config_creates_failed_not_completed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.json'
            path.write_text('{}', encoding='utf-8')
            process = subprocess.run([sys.executable, str(ROOT / 'controller.py'), '--path', str(path),
                                      '--output-dir', str(Path(directory) / 'output')],
                                     capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(process.returncode, 1)
            result = json.loads((Path(directory) / 'output/last_run.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['commands'], [])


if __name__ == '__main__':
    unittest.main()
