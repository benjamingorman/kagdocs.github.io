"""Behavioral checks for Manual ingestion, examples, and authored Markdown."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from kagdocs.catalogue import load_vanilla
from kagdocs.content import load_content, scaffold
from kagdocs.examples import ExampleIndex
from kagdocs.inputs import lex, read_installation
from kagdocs.model import parse_decl
from kagdocs.paths import repository_root
from kagdocs.render import api_entries, render, source_name


def file(path, text):
    return {"path": path, "tokens": lex(text)}


def fixture():
    return [
        file(
            "Manual/interface/Objects.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\nCBlob\n\tfloat getHealth()\n\tvoid setPosition(Vec2f pos)\nstring\n\t<constructor>()\n",
        ),
        file(
            "Manual/interface/Objects/CBlob.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\n-- CLASS 'CBlob' --\nfloat health\nfloat getHealth()\n",
        ),
        file(
            "Manual/interface/Functions.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\nint Maths::Abs(int v)\nfloat Maths::Abs(float v)\nvoid print(const string &in text, bool debug = false)\n",
        ),
        file(
            "Manual/interface/Variables.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\nMaths::float Pi\n",
        ),
        file(
            "Manual/interface/Enums.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\nCBlob::State\n\tIdle\n",
        ),
        file(
            "Manual/interface/Hooks.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\nvoid onInit(CBlob@ this)\n",
        ),
        file(
            "Manual/interface/TypeDefs.txt",
            "--- SCRIPT INTERFACE FOR BUILD 4762 ---\nint8\nint8\nfloat\n",
        ),
    ]


class ParserTests(unittest.TestCase):
    def test_merge_preserves_declarations_and_provenance(self):
        symbols = load_vanilla(fixture())
        health = [s for s in symbols if s.qualified == "CBlob::getHealth"]
        self.assertEqual(len(health), 1)
        self.assertEqual(health[0].source, "Manual/interface/Objects/CBlob.txt")
        self.assertEqual(health[0].line, 4)
        self.assertTrue(any(s.qualified == "CBlob::health" for s in symbols))
        self.assertTrue(any(s.qualified == "CBlob::State::Idle" for s in symbols))
        constructor = next(s for s in symbols if s.kind == "constructor")
        self.assertEqual(constructor.declaration, "string()")
        self.assertEqual(constructor.source_declaration, "<constructor>()")
        pi = next(s for s in symbols if s.qualified == "Maths::Pi")
        self.assertEqual(pi.source_declaration, "Maths::float Pi")
        overloads = next(
            e for e in api_entries(symbols) if e.signatures[0].qualified == "Maths::Abs"
        )
        self.assertEqual(len(overloads.signatures), 2)
        self.assertIn("debug = false", next(s.declaration for s in symbols if s.name == "print"))
        self.assertEqual(len([s for s in symbols if s.kind == "typedef"]), 2)

    def test_lexer_is_lossless_and_ignores_fake_calls(self):
        text = '/* Maths::Abs(-1); */\nvoid test() { string s = "Maths::Abs(2)"; // not a call\nMaths::Abs(\n  -1\n); }\n'
        self.assertEqual("".join(t[1] for t in lex(text)), text)
        symbols = [parse_decl("int Maths::Abs(int v)", "function")]
        examples = ExampleIndex(symbols, [file("Base/test.as", text)]).examples[symbols[0].key()]
        self.assertEqual(len(examples), 1)
        self.assertEqual((examples[0].call_first, examples[0].call_last), (3, 5))

    def test_receiver_shadowing_and_unknown_receivers(self):
        symbols = [parse_decl("CBlob", "class"), parse_decl("float getHealth()", "method", "CBlob")]
        text = "void test(CBlob@ blob) {\n blob.getHealth();\n { Vec2f blob; blob.getHealth(); }\n unknown.getHealth();\n}\n"
        index = ExampleIndex(symbols, [file("Base/test.as", text)])
        self.assertEqual([e.call_first for e in index.examples[symbols[1].key()]], [2])

    def test_unresolved_overload_has_no_example(self):
        symbols = [
            parse_decl("int Maths::Abs(int v)", "function"),
            parse_decl("float Maths::Abs(float v)", "function"),
        ]
        index = ExampleIndex(
            symbols, [file("Base/unknown.as", "void test() { Maths::Abs(unknown); }")]
        )
        self.assertFalse(any(index.examples.values()))
        index = ExampleIndex(
            symbols, [file("Base/known.as", "void test() { float value; Maths::Abs(value); }")]
        )
        self.assertFalse(index.examples[symbols[0].key()])
        self.assertEqual(len(index.examples[symbols[1].key()]), 1)

    def test_invalid_installation_and_mixed_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "KAG_DIR"):
                read_installation(root)
            (root / "Base").mkdir()
            (root / "Manual/interface/Objects").mkdir(parents=True)
            for f in fixture():
                path = root / f["path"]
                path.write_text("".join(t[1] for t in f["tokens"]), encoding="utf-8")
            self.assertEqual(read_installation(root)["build"], 4762)
            (root / "Manual/interface/Functions.txt").write_text(
                "--- SCRIPT INTERFACE FOR BUILD 4000 ---\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                read_installation(root)


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.symbols = load_vanilla(fixture())

    def test_scaffold_preserves_authored_content_and_renders_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = scaffold(root, self.symbols, "Maths::Abs")
            self.assertEqual(len(created), 1)
            path = created[0]
            with path.open("a") as stream:
                stream.write("\nA **magnitude**.\n\n```cpp\nMaths::Abs(-1);\n```\n")
            before = path.read_bytes()
            self.assertEqual(scaffold(root, self.symbols, "Maths::Abs"), [])
            self.assertEqual(path.read_bytes(), before)
            prose, _, _ = load_content(root, self.symbols)
            self.assertIn("<strong>magnitude</strong>", prose[("function", "Maths::Abs")])
            self.assertIn("language-cpp", prose[("function", "Maths::Abs")])

    def test_duplicate_unknown_and_stale_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = scaffold(root, self.symbols, "Maths::Abs")[0]
            duplicate = path.with_name("duplicate.md")
            duplicate.write_bytes(path.read_bytes())
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_content(root, self.symbols)
            duplicate.unlink()
            path.write_text("---\nkind: function\nsymbol: Maths::Abs\nsignatures: []\n---\n")
            with self.assertRaisesRegex(ValueError, "stale signatures"):
                load_content(root, self.symbols)
            path.write_text("---\nkind: function\nsymbol: Missing\nsignatures: []\n---\n")
            with self.assertRaisesRegex(ValueError, "unknown API"):
                load_content(root, self.symbols)

    def test_pilot_has_prose_for_every_authored_family(self):
        for path in (repository_root() / "docs/api/namespaces/Maths").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.split("---", 2)[2].strip(), path)
            meta = yaml.safe_load(text.split("---")[1])
            self.assertTrue(meta["symbol"].startswith("Maths"))
        for path in (repository_root() / "docs/guides").glob("*.md"):
            self.assertNotIn("{: .", path.read_text(encoding="utf-8"))

    def test_render_links_only_used_sources_and_includes_guides(self):
        guides = [{"slug": "tcp", "title": "TCPR", "order": 1, "html": "<p>Guide text</p>"}]
        files = fixture() + [
            file("Base/used.as", "void test() { CBlob@ blob; blob.getHealth(); }"),
            file("Base/unused.as", "// no engine calls"),
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "kagdocs.render.load_content",
                return_value=({}, {("GLOBALS", "Maths"): "<p>Namespace introduction</p>"}, guides),
            ),
        ):
            output = Path(tmp)
            report = render({"files": files, "build": 4762}, output)
            self.assertTrue((output / "source" / source_name("Base/used.as")).is_file())
            self.assertFalse((output / "source" / source_name("Base/unused.as")).exists())
            self.assertEqual(report["total"], len(self.symbols))
            self.assertEqual(report["guides"], 1)
            manifest = json.loads((output / "sections.json").read_text())
            guide = next(s for s in manifest if s["category"] == "GUIDES")
            self.assertEqual(guide["anchors"], ["guide-tcp-article"])
            self.assertIn("Guide text", (output / guide["file"]).read_text())
            maths = next(s for s in manifest if s["name"] == "Maths")
            self.assertIn("Namespace introduction", (output / maths["file"]).read_text())
            index = (output / "index.html").read_text()
            self.assertNotIn("progressbar", index)
            self.assertIn('<link rel="icon" href="favicon.ico" type="image/x-icon">', index)
            self.assertTrue((output / "favicon.ico").is_file())
            source = (output / "source" / source_name("Base/used.as")).read_text()
            self.assertIn('<link rel="icon" href="../favicon.ico" type="image/x-icon">', source)
            self.assertTrue((output / ".nojekyll").exists())
            if __import__("os").name != "nt":
                self.assertEqual(output.stat().st_mode & 0o777, 0o755)

    def test_all_scaffolds_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold(root, self.symbols, "*")
            prose, _, _ = load_content(root, self.symbols)
            self.assertEqual(len(prose), len({(s.kind, s.qualified) for s in self.symbols}))


if __name__ == "__main__":
    unittest.main()
