#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TKS_UI = PROJECT_ROOT / "code/static/modulos/tks/js/tks_ui.js"
TKS_MAIN = PROJECT_ROOT / "code/static/modulos/tks/js/tks_main.js"


class FrontendSecurityRegressionTests(unittest.TestCase):
    def test_customer_id_is_escaped_in_payment_button_handler(self) -> None:
        ui = TKS_UI.read_text(encoding="utf-8")
        self.assertIn("customerIdJs = escapeJsSingleQuoted(data.customer_id)", ui)
        self.assertNotIn("generatePaymentLink('${data.customer_id}'", ui)

    def test_generate_payment_link_does_not_use_global_event(self) -> None:
        main = TKS_MAIN.read_text(encoding="utf-8")
        self.assertIn("generatePaymentLink(customerId, amount, triggerEl = null)", main)
        self.assertNotIn("const btn = event.target.closest('button');", main)
        self.assertIn("triggerEl.closest('button')", main)


if __name__ == "__main__":
    unittest.main(verbosity=2)

