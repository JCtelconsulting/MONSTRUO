#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib
import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parents[1]
CODE_ROOT = PROJECT_ROOT / "plataforma" / "legacy" / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))


class TestAdminChatDisabledByDefault(unittest.TestCase):
    def test_admin_chat_endpoint_is_404_when_flag_not_set(self) -> None:
        os.environ.pop("ADMIN_CHAT_ENABLED", None)

        main = importlib.import_module("app.main")
        main = importlib.reload(main)

        # Evita ejecutar startup pesado (DB/jobs) durante este test de ruteo.
        main.app.router.on_startup = []

        # Asegurar que NO exista ruta POST /api/admin/chat registrada
        for r in main.app.router.routes:
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", set()) or set()
            self.assertFalse(
                path == "/api/admin/chat" and "POST" in methods,
                "admin_chat no debe estar expuesto cuando ADMIN_CHAT_ENABLED no está seteado",
            )

        # (Smoke) El request no debe comportarse como endpoint real.
        client = TestClient(main.app)
        resp = client.post("/api/admin/chat", json={"message": "ping"})
        self.assertIn(resp.status_code, (404, 405))


class TestInstallApkShellSafety(unittest.TestCase):
    def test_bancos_router_does_not_use_os_system(self) -> None:
        bancos_py = PROJECT_ROOT / "plataforma" / "legacy" / "code" / "app" / "api" / "routers" / "bancos.py"
        source = bancos_py.read_text(encoding="utf-8")
        self.assertNotIn("os.system(", source)

    def test_install_apk_does_not_use_shell_true(self) -> None:
        bancos_py = PROJECT_ROOT / "plataforma" / "legacy" / "code" / "app" / "api" / "routers" / "bancos.py"
        source = bancos_py.read_text(encoding="utf-8")
        tree = ast.parse(source)

        class Visitor(ast.NodeVisitor):
            unsafe = False

            def visit_Call(self, node: ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "run":
                    is_subprocess_run = (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                    )
                    if is_subprocess_run:
                        for kw in node.keywords:
                            if (
                                kw.arg == "shell"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True
                            ):
                                self.unsafe = True
                self.generic_visit(node)

        v = Visitor()
        v.visit(tree)

        self.assertFalse(v.unsafe, "install-apk no debe usar subprocess.run(..., shell=True)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
