import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build_llms_txt.py"
spec = importlib.util.spec_from_file_location("build_llms_txt", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def make_agent(root: Path, name: str, yaml: str, adapter: bool = True) -> None:
    directory = root / name
    (directory / "adapters").mkdir(parents=True)
    (directory / "agent.yaml").write_text(yaml, encoding="utf-8")
    if adapter:
        (directory / "adapters" / "mcp_server.py").write_text("", encoding="utf-8")


class BuildLlmsTxtTest(unittest.TestCase):
    def test_lists_agents_with_adapter_and_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_agent(root, "b-agent", 'name: "b-agent"\ndescription: "Does B."\n')
            make_agent(root, "a-agent", "name: a-agent\ndescription: Does A.\n")
            make_agent(root, "_AGENT_TEMPLATE", 'description: "template"\n')
            make_agent(root, "no-adapter", 'description: "skip"\n', adapter=False)
            make_agent(root, "folded", "description: >\n  long text\n")
            self.assertEqual(
                [d for d, _, _ in build.agents(root)], ["a-agent", "b-agent"]
            )
            text = build.render(root)
            self.assertIn("/tree/main/a-agent): Does A.", text)
            self.assertLess(text.index("a-agent"), text.index("b-agent"))

    def test_nested_description_keys_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_agent(root, "x", 'description: "top"\ntools:\n  description: "nested"\n')
            self.assertEqual(build.agents(root)[0][2], "top")

    def test_committed_llms_txt_is_current(self):
        self.assertEqual(build.main(["--check"]), 0, "run scripts/build_llms_txt.py")


if __name__ == "__main__":
    unittest.main()
