import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from fang import __version__
from tests.helpers import REPO_ROOT, calc_project


class MCPTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fang-mcp-")
        calc_project(self.root)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "fang", "mcp", self.root],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=dict(os.environ, PYTHONPATH=REPO_ROOT),
        )

    def tearDown(self):
        try:
            if self.process.poll() is None:
                self.process.kill()
            self.process.communicate(timeout=10)
        except Exception:
            pass
        shutil.rmtree(self.root, ignore_errors=True)

    def exchange(self, requests):
        for request in requests:
            self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        self.process.stdin.close()
        responses = []
        for line in self.process.stdout:
            line = line.strip()
            if line:
                responses.append(json.loads(line))
        self.process.wait(timeout=120)
        return {response.get("id"): response for response in responses}

    def test_protocol_handshake_and_tools(self):
        responses = self.exchange(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "ping"},
                {"jsonrpc": "2.0", "id": 4, "method": "nope"},
            ]
        )
        init = responses[1]["result"]
        self.assertEqual(init["serverInfo"]["name"], "fang")
        self.assertEqual(init["protocolVersion"], "2024-11-05")
        self.assertIn("instructions", init)
        tools = [tool["name"] for tool in responses[2]["result"]["tools"]]
        self.assertIn("fang_check_diff", tools)
        self.assertIn("fang_mutation_score", tools)
        self.assertEqual(responses[3]["result"], {})
        self.assertEqual(responses[4]["error"]["code"], -32601)
        self.assertEqual(self.process.returncode, 0)
        self.assertEqual(self.process.stderr.read().strip(), "")

    def test_doctor_and_score(self):
        responses = self.exchange(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "fang_doctor", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "fang_mutation_score",
                        "arguments": {"all": True, "sample": 2, "jobs": 1},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "not_a_tool", "arguments": {}},
                },
            ]
        )
        doctor = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(doctor["fang"], __version__)
        self.assertIn("runner", doctor)
        score = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertIn("score", score)
        self.assertEqual(score["mutants"]["considered"], 2)
        self.assertEqual(responses[4]["result"]["isError"], True)


if __name__ == "__main__":
    unittest.main()
