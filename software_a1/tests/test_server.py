import json
import time
import unittest
from contextlib import contextmanager

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import create_app


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    @contextmanager
    def viewer(self, visible=True):
        with self.client.websocket_connect('/ws') as ws:
            self.assertEqual(ws.receive_json()['type'], 'hello')
            ws.send_json({'type': 'ready', 'visible': visible})
            self.assertEqual(ws.receive_json()['type'], 'ready')
            yield ws

    def move(self, command_id='test-1', target=None, speed=1.0):
        return self.client.post('/api/move', json={
            'type': 'move', 'command_id': command_id,
            'target': target or {'x': 1.0, 'y': 0.2, 'z': 0.0}, 'speed': speed,
        })

    def telemetry(self, ws, phase, command_id='test-1', position=None, elapsed=1.0):
        ws.send_json({'type': 'telemetry', 'command_id': command_id, 'phase': phase,
                      'position': position or {'x': 1.0, 'y': 0.2, 'z': 0.0}, 'elapsed_s': elapsed})

    def wait_command(self, command_id, phase):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = self.client.get(f'/api/commands/{command_id}').json()
            if current['status'] == phase:
                return current
            time.sleep(0.005)
        self.fail(f'Expected {phase}: {current}')

    def test_page_and_local_modules_are_served(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('三维轨迹控制台', response.text)
        for path in ('main.js', 'scene.js', 'motion.js', 'styles.css', 'vendor/three/three.module.js', 'vendor/three/three.core.js'):
            self.assertEqual(self.client.get('/static/' + path).status_code, 200, path)

    def test_move_requires_a_ready_viewer(self):
        self.assertEqual(self.move().status_code, 409)
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()
            self.assertEqual(self.move().status_code, 409)

    def test_accepted_is_not_completed(self):
        with self.viewer() as ws:
            response = self.move()
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()['command']['status'], 'accepted')
            message = ws.receive_json()
            self.assertEqual(message['type'], 'move')
            self.assertEqual(message['command']['expected_motion_s'], 1.0)
            self.telemetry(ws, 'arrived')
            self.assertEqual(self.wait_command('test-1', 'arrived')['position']['x'], 1.0)
            self.assertIsNone(self.client.get('/api/state').json()['active_command_id'])

    def test_busy_does_not_replace_current_command(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.assertEqual(self.move('another').status_code, 409)
            self.assertEqual(self.client.get('/api/state').json()['active_command_id'], 'test-1')

    def test_duplicate_command_is_idempotent_and_conflicting_reuse_is_rejected(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.assertTrue(self.move().json()['duplicate'])
            self.assertEqual(self.move(speed=2.0).status_code, 409)
            self.telemetry(ws, 'arrived'); self.wait_command('test-1', 'arrived')
            duplicate = self.move().json()
            self.assertTrue(duplicate['duplicate'])
            self.assertEqual(duplicate['command']['status'], 'arrived')

    def test_arrival_position_is_verified(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.telemetry(ws, 'arrived', position={'x': 0.0, 'y': 0.2, 'z': 0.0})
            self.assertEqual(ws.receive_json()['type'], 'error')
            self.assertEqual(self.client.get('/api/state').json()['active_command_id'], 'test-1')
            self.telemetry(ws, 'arrived'); self.wait_command('test-1', 'arrived')

    def test_invalid_numbers_and_unknown_fields_have_json_errors(self):
        for fragment in ('0', '-1', 'NaN', 'Infinity', 'true', '"1.0"'):
            body = '{"command_id":"bad","target":{"x":1,"y":0.2,"z":0},"speed":' + fragment + '}'
            with self.subTest(speed=fragment):
                response = self.client.post('/api/move', content=body, headers={'Content-Type': 'application/json'})
                self.assertEqual(response.status_code, 422)
                self.assertIn('detail', response.json())
        self.assertEqual(self.client.post('/api/move', json={'unknown': 1}).status_code, 422)

    def test_pause_and_resume_wait_for_viewer_telemetry(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.assertEqual(self.client.post('/api/control', json={'action': 'pause'}).status_code, 202)
            self.assertEqual(ws.receive_json(), {'type': 'control', 'action': 'pause'})
            self.assertEqual(self.client.get('/api/commands/test-1').json()['status'], 'accepted')
            self.telemetry(ws, 'paused', position={'x': 0.5, 'y': 0.2, 'z': 0}, elapsed=0.5)
            self.wait_command('test-1', 'paused')
            self.assertEqual(self.client.post('/api/control', json={'action': 'resume'}).status_code, 202)
            self.assertEqual(ws.receive_json()['action'], 'resume')

    def test_stop_is_bound_to_the_requested_command(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            wrong = self.client.post('/api/control', json={'action': 'stop', 'command_id': 'other'})
            self.assertEqual(wrong.status_code, 409)
            self.assertEqual(self.client.post('/api/control', json={'action': 'stop', 'command_id': 'test-1'}).status_code, 202)
            self.assertEqual(ws.receive_json()['action'], 'stop')
            self.telemetry(ws, 'cancelled', position={'x': 0.3, 'y': 0.2, 'z': 0}, elapsed=0.3)
            self.assertEqual(self.wait_command('test-1', 'cancelled')['position']['x'], 0.3)

    def test_disconnect_cancels_incomplete_motion(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
        command = self.wait_command('test-1', 'cancelled')
        self.assertEqual(command['position']['x'], 0)
        self.assertFalse(self.client.get('/api/state').json()['viewer_ready'])

    def test_second_viewer_cannot_take_over(self):
        with self.viewer() as first:
            with self.client.websocket_connect('/ws') as second:
                self.assertEqual(second.receive_json()['type'], 'error')
                with self.assertRaises(WebSocketDisconnect) as error:
                    second.receive_json()
                self.assertEqual(error.exception.code, 4009)
            self.assertEqual(self.move().status_code, 202)
            self.assertEqual(first.receive_json()['type'], 'move')

    def test_reconnect_restores_last_position_without_replaying_command(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.telemetry(ws, 'moving', position={'x': 0.25, 'y': 0.2, 'z': 0}, elapsed=0.25)
            self.wait_command('test-1', 'moving')
        self.wait_command('test-1', 'cancelled')
        with self.client.websocket_connect('/ws') as new:
            hello = new.receive_json()
            self.assertEqual(hello['state']['position']['x'], 0.25)
            self.assertIsNone(hello['state']['active_command_id'])

    def test_route_reset_requires_no_active_motion(self):
        route = self.client.get('/api/state').json()['route']
        with self.viewer() as ws:
            self.assertEqual(self.client.post('/api/route', json=route).status_code, 200)
            self.assertEqual(ws.receive_json()['type'], 'route')
            self.move(); ws.receive_json()
            self.assertEqual(self.client.post('/api/route', json=route).status_code, 409)

    def test_hidden_page_cannot_accept_new_motion(self):
        with self.viewer(visible=False) as ws:
            self.assertEqual(self.move().status_code, 409)
            ws.send_json({'type': 'ready', 'visible': True}); ws.receive_json()
            self.assertEqual(self.move().status_code, 202)
            ws.receive_json()

    def test_stale_telemetry_does_not_change_new_command(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.telemetry(ws, 'arrived'); self.wait_command('test-1', 'arrived')
            self.move('test-2', target={'x': 2.0, 'y': 0.2, 'z': 0}); ws.receive_json()
            self.telemetry(ws, 'moving', position={'x': 999, 'y': 0.2, 'z': 0})
            ws.send_json({'type': 'ready', 'visible': True}); ws.receive_json()
            state = self.client.get('/api/state').json()
            self.assertEqual(state['active_command_id'], 'test-2')
            self.assertEqual(state['position']['x'], 1.0)

    def test_elapsed_time_cannot_go_backward(self):
        with self.viewer() as ws:
            self.move(); ws.receive_json()
            self.telemetry(ws, 'moving', elapsed=0.5); self.wait_command('test-1', 'moving')
            self.telemetry(ws, 'moving', elapsed=0.1)
            self.assertEqual(ws.receive_json()['type'], 'error')
            self.assertEqual(self.client.get('/api/commands/test-1').json()['motion_elapsed_s'], 0.5)

    def test_unknown_command_and_idle_controls(self):
        self.assertEqual(self.client.get('/api/commands/missing').status_code, 404)
        with self.viewer():
            self.assertEqual(self.client.post('/api/control', json={'action': 'stop'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
