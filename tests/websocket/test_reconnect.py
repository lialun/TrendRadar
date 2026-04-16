# coding=utf-8

import unittest

from trendradar.websocket.core.reconnect import ReconnectController


class ReconnectControllerTest(unittest.TestCase):
    def test_last_delay_preserves_capped_retry_interval(self):
        controller = ReconnectController(initial_delay=1.0, max_delay=4.0, backoff_factor=2.0)

        self.assertEqual(1.0, controller.on_connect_failure("a"))
        self.assertEqual(1.0, controller.last_delay)
        self.assertEqual(2.0, controller.on_connect_failure("b"))
        self.assertEqual(2.0, controller.last_delay)
        self.assertEqual(4.0, controller.on_connect_failure("c"))
        self.assertEqual(4.0, controller.last_delay)
        self.assertEqual(4.0, controller.current_delay)
