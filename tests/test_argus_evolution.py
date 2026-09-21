"""
ARGUS Evolution Unit Tests
Verifies:
1. Multi-state loop detection (A -> B -> A -> B)
2. Static freeze detection (A -> A -> A)
3. Privacy redaction (API keys, tokens, emails, phones, passwords)
"""
import unittest
from PIL import Image

import sys, pathlib
argus_scripts = pathlib.Path(r"C:\Users\Korhan\Desktop\AG Korhan\ScreeShot\g\g yenii\.agents\skills\argus\scripts")
sys.path.insert(0, str(argus_scripts))

from fallback_handler import CircuitBreaker, redact_sensitive_text


class TestArgusEvolution(unittest.TestCase):
    def setUp(self):
        self.breaker = CircuitBreaker(max_consecutive_unchanged=3)

    def test_static_freeze_breaker(self):
        """Verify 3 consecutive identical screens trip circuit breaker."""
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        can1, _ = self.breaker.check_and_update(img, "click")
        self.assertTrue(can1)
        can2, _ = self.breaker.check_and_update(img, "click")
        self.assertTrue(can2)
        can3, msg = self.breaker.check_and_update(img, "click")
        self.assertFalse(can3)
        self.assertIn("CIRCUIT_BREAKER_TRIGGERED", msg)

    def test_ping_pong_loop_breaker(self):
        """Verify alternating screen cycle A -> B -> A -> B trips cycle breaker."""
        # Image A has left-to-right gradient (dHash differs from B)
        img_a = Image.new("L", (100, 100), color=0)
        for x in range(50):
            for y in range(100):
                img_a.putpixel((x, y), 255)

        # Image B has top-to-bottom gradient
        img_b = Image.new("L", (100, 100), color=0)
        for x in range(100):
            for y in range(50):
                img_b.putpixel((x, y), 255)

        can1, _ = self.breaker.check_and_update(img_a, "step1")
        self.assertTrue(can1)
        can2, _ = self.breaker.check_and_update(img_b, "step2")
        self.assertTrue(can2)
        can3, _ = self.breaker.check_and_update(img_a, "step3")
        self.assertTrue(can3)
        # 4th action completes A -> B -> A -> B
        can4, msg = self.breaker.check_and_update(img_b, "step4")
        self.assertFalse(can4)
        self.assertIn("PING_PONG_CYCLE_DETECTED", msg)

    def test_privacy_redaction(self):
        """Verify sensitive credentials, tokens, emails, and passwords are fully scrubbed."""
        raw = (
            "Authorization: Bearer abc123def456ghi789jkl012mno345 "
            "Google API key: AIzaSyD9xYZ1234567890abcdef1234567890 "
            "Contact: user.test@example.com or +1 555-123-4567. "
            "Login password: SecretPassword123!"
        )
        redacted = redact_sensitive_text(raw)
        self.assertNotIn("Bearer abc123def456ghi789jkl012mno345", redacted)
        self.assertIn("[TOKEN_REDACTED]", redacted)
        self.assertNotIn("AIzaSyD9xYZ1234567890abcdef1234567890", redacted)
        self.assertIn("[API_KEY_REDACTED]", redacted)
        self.assertNotIn("user.test@example.com", redacted)
        self.assertIn("[EMAIL_REDACTED]", redacted)
        self.assertNotIn("555-123-4567", redacted)
        self.assertIn("[PHONE_REDACTED]", redacted)
        self.assertNotIn("SecretPassword123!", redacted)
        self.assertIn("[PASSWORD_REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
