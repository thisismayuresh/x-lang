"""Tests for System.io.Network.http: the awaitable fetch() and HttpException."""

from __future__ import annotations

import contextlib
import io
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from xlang.cli import main
from xlang.config import FEATURE_DEFAULTS, XConfig
from xlang.interpreter import Interpreter
from xlang.module_loader import ModuleLoader
from xlang.runtime import RuntimeErrorX


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type="text/plain", headers=None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        import json as jsonlib

        if self.path == "/hello":
            self._send(200, "world")
        elif self.path == "/json":
            self._send(
                200,
                jsonlib.dumps({"a": 1, "nested": {"b": True}}),
                "application/json",
            )
        elif self.path == "/redirect":
            self._send(302, "", headers={"Location": "/hello"})
        elif self.path.startswith("/status/"):
            code = int(self.path.rsplit("/", 1)[1])
            self._send(code, f"error body for {code}")
        elif self.path == "/slow":
            time.sleep(3)
            self._send(200, "slow")
        elif self.path == "/ua":
            self._send(200, self.headers.get("User-Agent", "<none>"))
        elif self.path.startswith("/echo?"):
            self._send(200, self.path.split("?", 1)[1])
        else:
            self._send(404, "not found")

    def do_POST(self):
        import json as jsonlib

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        payload = {
            "method": self.command,
            "body": body,
            "userAgent": self.headers.get("User-Agent"),
            "contentType": self.headers.get("Content-Type"),
            "authorization": self.headers.get("Authorization"),
        }
        self._send(200, jsonlib.dumps(payload), "application/json")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


class HttpTestBase(unittest.TestCase):
    server: ThreadingHTTPServer
    base_url: str

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}"
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    def run_source(self, source: str, config: XConfig | None = None) -> list[str]:
        config = config or XConfig()
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            entry = project_root / "main.x"
            entry.write_text(source.replace("BASEURL", self.base_url), encoding="utf-8")
            loader = ModuleLoader(project_root, config=config, recover_errors=True)
            program = loader.load_program(entry)
            if loader.errors:
                raise AssertionError(
                    "loader errors: "
                    + "; ".join(error.message for error in loader.errors)
                )
            output: list[str] = []
            Interpreter(config=config, output=output.append).interpret(program)
            return output

    def run_source_error(
        self, source: str, config: XConfig | None = None
    ) -> RuntimeErrorX:
        config = config or XConfig()
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            entry = project_root / "main.x"
            entry.write_text(source.replace("BASEURL", self.base_url), encoding="utf-8")
            loader = ModuleLoader(project_root, config=config, recover_errors=False)
            program = loader.load_program(entry)
            with self.assertRaises(RuntimeErrorX) as caught:
                Interpreter(config=config, output=lambda text: None).interpret(program)
            return caught.exception


class HttpImportTests(HttpTestBase):
    def test_leaf_import_binds_fetch(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/hello");\n'
            '    print(response.status + " " + response.body);\n'
            "}\n"
        )
        self.assertEqual(output, ["200 world"])

    def test_module_import_binds_http_namespace(self):
        output = self.run_source(
            "import System.io.Network.http\n"
            "async function main() {\n"
            '    let response = await http.fetch("BASEURL/hello");\n'
            '    print(response.status + " " + response.body);\n'
            "}\n"
        )
        self.assertEqual(output, ["200 world"])

    def test_leaf_import_can_be_aliased(self):
        output = self.run_source(
            "import System.io.Network.http.fetch as httpGet\n"
            "async function main() {\n"
            '    let response = await httpGet("BASEURL/hello");\n'
            "    print(response.ok);\n"
            "}\n"
        )
        self.assertEqual(output, ["true"])

    def test_network_feature_disabled_blocks_import(self):
        config = XConfig(features={**FEATURE_DEFAULTS, "network": False})
        with self.assertRaises(RuntimeErrorX) as caught:
            self.run_source(
                "import System.io.Network.http.fetch\n"
                "any function main() {\n"
                "    print(1);\n"
                "}\n",
                config=config,
            )
        self.assertIn("feature 'network' is disabled", str(caught.exception))


class HttpResponseTests(HttpTestBase):
    def test_get_response_fields(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/hello");\n'
            "    print(response.status);\n"
            "    print(response.statusText);\n"
            "    print(response.ok);\n"
            '    print(response.text());\n'
            '    print(response.header("content-TYPE"));\n'
            '    print(response.header("missing") == null);\n'
            "}\n"
        )
        self.assertEqual(
            output,
            ["200", "OK", "true", "world", "text/plain", "true"],
        )

    def test_json_helper_parses_nested_objects(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/json");\n'
            "    let data = response.json();\n"
            "    print(data.a);\n"
            "    print(data.nested.b);\n"
            "}\n"
        )
        self.assertEqual(output, ["1", "true"])

    def test_custom_and_default_user_agent(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let custom = await fetch("BASEURL/ua", {userAgent: "Curlish/9.9"});\n'
            "    print(custom.body);\n"
            '    let automatic = await fetch("BASEURL/ua");\n'
            '    print(automatic.body.startsWith("X/"));\n'
            "}\n"
        )
        self.assertEqual(output, ["Curlish/9.9", "true"])

    def test_headers_user_agent_wins_over_user_agent_option(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/ua", {\n'
            '        userAgent: "OptionAgent/1.0",\n'
            '        headers: {"User-Agent": "HeaderAgent/2.0"}\n'
            "    });\n"
            "    print(response.body);\n"
            "}\n"
        )
        self.assertEqual(output, ["HeaderAgent/2.0"])

    def test_post_sends_json_body_with_implicit_content_type(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/anything", {\n'
            '        method: "POST",\n'
            '        headers: {"Authorization": "Bearer token"},\n'
            '        body: {name: "Ada"}\n'
            "    });\n"
            "    let echo = response.json();\n"
            "    print(echo.method);\n"
            '    print(echo.body.contains("Ada"));\n'
            '    print(echo.contentType.startsWith("application/json"));\n'
            '    print(echo.authorization);\n'
            "}\n"
        )
        self.assertEqual(output, ["POST", "true", "true", "Bearer token"])

    def test_query_option_appends_parameters(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/echo", {\n'
            '        query: {"q": "two words", "page": 2}\n'
            "    });\n"
            "    print(response.body);\n"
            "}\n"
        )
        self.assertEqual(output, ["q=two+words&page=2"])

    def test_body_bytes_and_headers_object(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/hello");\n'
            "    print(response.bodyBytes.length);\n"
            '    print(response.header("Content-Type"));\n'
            "}\n"
        )
        self.assertEqual(output, ["5", "text/plain"])

    def test_follows_redirects_by_default(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/redirect");\n'
            "    print(response.status);\n"
            '    print(response.url.endsWith("/hello"));\n'
            '    print(response.text());\n'
            "}\n"
        )
        self.assertEqual(output, ["200", "true", "world"])

    def test_redirects_can_be_disabled(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/redirect", {\n'
            "        followRedirects: false\n"
            "    });\n"
            "    print(response.status);\n"
            '    print(response.header("location"));\n'
            "}\n"
        )
        self.assertEqual(output, ["302", "/hello"])


class HttpErrorTests(HttpTestBase):
    def test_http_error_status_returns_response_by_default(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/status/404");\n'
            "    print(response.status);\n"
            "    print(response.ok);\n"
            '    print(response.text());\n'
            "}\n"
        )
        self.assertEqual(output, ["404", "false", "error body for 404"])

    def test_throw_on_error_raises_http_exception_with_body_excerpt(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            "    try {\n"
            '        let response = await fetch("BASEURL/status/500", {\n'
            "            throwOnError: true\n"
            "        });\n"
            '        print("unreachable " + response.status);\n'
            "    } catch (HttpException error) {\n"
            '        print("caught: " + error.message);\n'
            "    } finally {\n"
            '        print("finally ran");\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(len(output), 2)
        self.assertTrue(output[0].startswith("caught: GET "))
        self.assertIn("HTTP 500 Internal Server Error", output[0])
        self.assertIn("error body for 500", output[0])
        self.assertEqual(output[1], "finally ran")

    def test_connection_refused_is_caught_as_io_exception(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            "    try {\n"
            '        let response = await fetch("http://127.0.0.1:1/x", {\n'
            "            timeout: 2\n"
            "        });\n"
            '        print("unreachable");\n'
            "    } catch (IOException error) {\n"
            '        print("io: " + error.message);\n'
            "    } finally {\n"
            '        print("finally ran");\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(len(output), 2)
        self.assertIn("connection refused", output[0])
        self.assertEqual(output[1], "finally ran")

    def test_catch_exception_root_catches_http_exception(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            "    try {\n"
            '        await fetch("ftp://example.com/file");\n'
            "    } catch (Exception error) {\n"
            '        print(error.name + ": " + error.message);\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(len(output), 1)
        self.assertTrue(output[0].startswith("HttpException: "))
        self.assertIn("only supports http and https", output[0])

    def test_timeout_raises_http_exception(self):
        output = self.run_source(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            "    try {\n"
            '        await fetch("BASEURL/slow", {timeout: 0.3});\n'
            '        print("unreachable");\n'
            "    } catch (HttpException error) {\n"
            '        print(error.message);\n'
            "    } finally {\n"
            '        print("finally ran");\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(len(output), 2)
        self.assertIn("timed out after 0.3 seconds", output[0])
        self.assertEqual(output[1], "finally ran")

    def test_manual_throw_and_catch_of_http_exception(self):
        output = self.run_source(
            "any function main() {\n"
            "    try {\n"
            '        throw HttpException("manual failure", "inner");\n'
            "    } catch (HttpException error) {\n"
            '        print(error.name + ": " + error.message);\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(output, ["HttpException: manual failure"])

    def test_unknown_option_reports_the_valid_options(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    await fetch("BASEURL/hello", {timeOut: 5});\n'
            "}\n"
        )
        self.assertEqual(error.exception_name, "HttpException")
        self.assertIn("Unknown fetch option 'timeOut'", str(error))
        self.assertIn("Valid options:", str(error))

    def test_unsupported_scheme_is_rejected(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    await fetch("ftp://example.com/x");\n'
            "}\n"
        )
        self.assertIn("only supports http and https", str(error))

    def test_unsupported_method_is_rejected(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    await fetch("BASEURL/hello", {method: "BREW"});\n'
            "}\n"
        )
        self.assertIn("Unsupported HTTP method 'BREW'", str(error))

    def test_negative_timeout_is_rejected(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    await fetch("BASEURL/hello", {timeout: -1});\n'
            "}\n"
        )
        self.assertIn("timeout cannot be negative", str(error))

    def test_fetch_without_arguments_fails_at_the_call_site(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            "    await fetch();\n"
            "}\n"
        )
        self.assertIn("expects a url and an optional options object", str(error))

    def test_json_helper_on_a_non_json_body_raises_http_exception(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/hello");\n'
            "    response.json();\n"
            "}\n"
        )
        self.assertEqual(error.exception_name, "HttpException")
        self.assertIn("not valid JSON", str(error))

    def test_response_helpers_validate_arguments(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "async function main() {\n"
            '    let response = await fetch("BASEURL/hello");\n'
            "    response.text(1);\n"
            "}\n"
        )
        self.assertIn("response.text() takes no arguments", str(error))

    def test_discarded_fetch_result_reports_missing_await(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "any function main() {\n"
            '    fetch("BASEURL/hello");\n'
            "}\n"
        )
        self.assertIn("did you forget 'await' before fetch(...)", str(error))

    def test_unawaited_fetch_member_reports_missing_await(self):
        error = self.run_source_error(
            "import System.io.Network.http.fetch\n"
            "any function main() {\n"
            '    let response = fetch("BASEURL/hello");\n'
            "    print(response.status);\n"
            "}\n"
        )
        self.assertIn("Cannot read 'status' from an asynchronous result", str(error))
        self.assertIn("did you forget 'await'", str(error))


class HttpCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            return_code = main(arguments)
        return return_code, output.getvalue(), errors.getvalue()

    def test_cli_runs_a_fetch_program(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            entry = Path(temporary_directory) / "main.x"
            entry.write_text(
                "import System.io.Network.http.fetch\n"
                "async function main() {\n"
                "    try {\n"
                '        await fetch("http://127.0.0.1:1/x", {timeout: 1});\n'
                '        print("unreachable");\n'
                "    } catch (HttpException error) {\n"
                '        print("cli caught: " + error.message);\n'
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            return_code, output, _ = self.run_cli(
                ["run", "--no-config", str(entry)]
            )

        self.assertEqual(return_code, 0)
        self.assertIn("cli caught: Cannot reach '127.0.0.1:1'", output)

    def test_cli_checks_a_fetch_program(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            entry = Path(temporary_directory) / "main.x"
            entry.write_text(
                "import System.io.Network.http.fetch\n"
                "async function main() {\n"
                '    let response = await fetch("https://example.com");\n'
                "    print(response.status);\n"
                "}\n",
                encoding="utf-8",
            )
            return_code, output, _ = self.run_cli(
                ["check", "--no-config", str(entry)]
            )

        self.assertEqual(return_code, 0)
        self.assertIn("types are valid", output)


if __name__ == "__main__":
    unittest.main()
