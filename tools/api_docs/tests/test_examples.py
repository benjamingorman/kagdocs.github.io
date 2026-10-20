"""Positive discovery and rejection boundaries for the syntax-tree matcher."""

import hashlib
import json
import unittest
from pathlib import Path

from kagdocs.examples import Catalogue, ExampleIndex, base_type
from kagdocs.model import parse_decl
from kagdocs.syntax import ParsedSource


def api():
    return [
        parse_decl("CMap", "class"),
        parse_decl("Tile", "class"),
        parse_decl("SColor", "class"),
        parse_decl("Vec2f", "class"),
        parse_decl("CMap@ getMap()", "function"),
        parse_decl("uint tilemapwidth", "property", "CMap"),
        parse_decl("uint tilemapheight", "property", "CMap"),
        parse_decl("Tile getTile(uint offset)", "method", "CMap"),
        parse_decl("uint type", "property", "Tile"),
        parse_decl("float x", "property", "Vec2f"),
        parse_decl("<constructor>(int r, int g, int b)", "method", "SColor"),
        parse_decl("void setRed(uint r)", "method", "SColor"),
        parse_decl("int Maths::Abs(int value)", "function"),
        parse_decl("float Maths::Abs(float value)", "function"),
        parse_decl("Maths::float Pi", "property"),
        parse_decl("void use(const string&in text, CMap@ map)", "function"),
        parse_decl("void store(?&in value)", "function"),
        parse_decl("void onInit(CMap@ this)", "hook"),
    ]


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.symbols = api()

    def index(self, text, extra=(), symbols=None):
        source = ParsedSource.parse(text)
        self.assertEqual(source.errors(), [], text)
        files = [{"path": "Base/test.as", "tokens": source.tokens(), "syntax": source}, *extra]
        return ExampleIndex(symbols or self.symbols, files)

    def examples(self, index, qualified):
        return [
            e for s in self.symbols if s.qualified == qualified for e in index.examples[s.key()]
        ]

    def test_typed_local_property_read_write_and_direct_return_chain(self):
        index = self.index("""void onRestart(CRules@ this) {
 CMap@ map = getMap();
 const u32 GRID_SIZE = map.tilemapwidth * map.tilemapheight;
 map.tilemapwidth = 8;
 uint t = getMap().getTile(0).type;
}""")
        self.assertEqual(self.examples(index, "CMap::tilemapwidth")[0].call_first, 3)
        self.assertTrue(self.examples(index, "CMap::tilemapheight"))
        self.assertTrue(self.examples(index, "Tile::type"))
        self.assertTrue(self.examples(index, "CMap::getTile"))

    def test_auto_parentheses_handle_cast_and_array_elements(self):
        index = self.index("""void f(CMap@[] maps, array<CMap@> others) {
 auto@ map = getMap();
 uint a = (map).tilemapwidth;
 uint b = maps[0].tilemapheight;
 uint c = cast<CMap>(others[0]).getTile(0).type;
}""")
        for name in ("CMap::tilemapwidth", "CMap::tilemapheight", "Tile::type"):
            self.assertTrue(self.examples(index, name), name)

    def test_constructor_style_locals(self):
        index = self.index("void f() { SColor color(255, 0, 0); color.setRed(1); }")
        constructor = self.examples(index, "SColor::SColor")[0]
        self.assertEqual(constructor.token, "SColor")
        self.assertTrue(self.examples(index, "SColor::setRed"))

    def test_unknown_and_nested_shadowing_never_borrow_outer_type(self):
        index = self.index("""void f(CMap@ map) {
 { Unknown map; uint a = map.tilemapwidth; }
 for (Unknown map; false;) { uint b = map.tilemapwidth; }
 unknown.getTile(0);
}
void g() { map.getTile(0); }""")
        self.assertFalse(self.examples(index, "CMap::tilemapwidth"))
        self.assertFalse(self.examples(index, "CMap::getTile"))

    def test_script_class_name_and_function_shadow_native_names(self):
        index = self.index("""class CMap { uint tilemapwidth; }
 CMap@ getMap() { return null; }
 void f(CMap@ map) { uint a = map.tilemapwidth; uint b = getMap().tilemapwidth; }""")
        self.assertFalse(any(index.examples.values()))

    def test_native_calls_inside_script_classes_and_class_member_shadowing(self):
        index = self.index("""class Helper {
 CMap@ map;
 void getMap() {}
 void f() { uint a = map.tilemapwidth; getMap(); }
}""")
        self.assertTrue(self.examples(index, "CMap::tilemapwidth"))
        self.assertFalse(self.examples(index, "getMap"))

    def test_overload_unknown_tie_is_omitted_and_typed_argument_is_exact(self):
        index = self.index("void f() { Maths::Abs(unknown); float v; Maths::Abs(v); }")
        overloads = [s for s in self.symbols if s.qualified == "Maths::Abs"]
        self.assertFalse(index.examples[overloads[0].key()])
        self.assertEqual(len(index.examples[overloads[1].key()]), 1)

    def test_const_references_aliases_and_generic_reference_parameter(self):
        self.assertEqual(base_type("constarray<CMap@>&in"), "CMap[]")
        self.assertEqual(base_type("constu32&in"), "uint")
        index = self.index("void f(CMap@ map) { string text; use(text, map); store(map); }")
        self.assertTrue(self.examples(index, "use"))
        self.assertTrue(self.examples(index, "store"))

    def test_namespaced_property_and_hook_definition(self):
        index = self.index("void onInit(CMap@ this) { float v = Maths::Pi; }")
        self.assertTrue(self.examples(index, "Maths::Pi"))
        self.assertTrue(self.examples(index, "onInit"))

    def test_foreach_bindings_shadow_and_do_not_escape(self):
        index = self.index("""void f(CMap@ map, array<Unknown> values) {
 foreach (Unknown map : values) { uint a = map.tilemapwidth; }
 uint b = map.tilemapwidth;
}""")
        self.assertEqual(self.examples(index, "CMap::tilemapwidth")[0].call_first, 3)

    def test_boolean_negation_is_not_inferred_as_its_operand_type(self):
        index = self.index("void f() { Maths::Abs(!1); }")
        self.assertFalse(any(index.examples.values()))

    def test_named_arguments_are_not_treated_as_positional(self):
        index = self.index("void f() { Maths::Abs(value: 1); }")
        self.assertFalse(any(index.examples.values()))

    def test_explicit_namespace_is_not_shadowed_by_a_local_name(self):
        index = self.index(
            "void f() { Unknown Abs; Maths::Abs(1); Unknown Pi; float v = Maths::Pi; }"
        )
        self.assertTrue(self.examples(index, "Maths::Abs"))
        self.assertTrue(self.examples(index, "Maths::Pi"))

    def test_conditional_bindings_do_not_leak_between_branches(self):
        index = self.index("""void f() {
 #ifdef SERVER
 CMap@ map = getMap();
 #else
 uint a = map.tilemapwidth;
 #endif
 uint b = map.tilemapwidth;
}""")
        self.assertFalse(self.examples(index, "CMap::tilemapwidth"))
        index = self.index("""void f() {
 #ifdef SERVER
 CMap@ map = getMap();
 uint a = map.tilemapwidth;
 #endif
}""")
        self.assertTrue(self.examples(index, "CMap::tilemapwidth"))

    def test_comments_strings_unicode_and_multiline_coordinates(self):
        text = """void f() {
 // Maths::Abs(1);
 string s = "Maths::Abs(1)";
 /* café */ Maths::Abs(
 1);
}"""
        index = self.index(text)
        example = self.examples(index, "Maths::Abs")[0]
        self.assertEqual((example.call_first, example.call_last), (4, 5))
        self.assertEqual(
            text.splitlines()[3][example.column : example.column + len(example.token)], "Abs"
        )
        self.assertEqual("".join(t[1] for t in ParsedSource.parse(text).tokens()), text)

    def test_damaged_function_is_excluded_but_other_functions_survive(self):
        text = "void bad() { CMap@ map; broken !!!; map.getTile(0); }\nvoid good() { getMap(); }"
        source = ParsedSource.parse(text)
        self.assertTrue(source.errors())
        index = ExampleIndex(
            self.symbols, [{"path": "Base/bad.as", "tokens": source.tokens(), "syntax": source}]
        )
        self.assertFalse(self.examples(index, "CMap::getTile"))
        self.assertTrue(self.examples(index, "getMap"))
        self.assertEqual(index.diagnostics["parse_errors"][0]["path"], "Base/bad.as")

    def test_selection_is_sorted_capped_and_base_only(self):
        files = [
            {
                "path": path,
                "tokens": ParsedSource.parse("void f() { getMap(); getMap(); }").tokens(),
            }
            for path in ("Base/z.as", "Base/c.as", "Other/a.as", "Base/a.as", "Base/b.as")
        ]
        index = ExampleIndex(self.symbols, files, context_lines=0)
        self.assertEqual(
            [e.path for e in self.examples(index, "getMap")],
            ["Base/a.as", "Base/b.as", "Base/c.as"],
        )
        with self.assertRaisesRegex(ValueError, "non-negative"):
            ExampleIndex(self.symbols, [], -1)

    def test_arithmetic_string_and_vec_operators_select_one_overload(self):
        index = self.index(
            "void f(Vec2f targetPos, Vec2f mypos) { Maths::Abs(targetPos.x - mypos.x); Maths::Abs(1.0f / 3.0f); }"
        )
        overloads = [s for s in self.symbols if s.qualified == "Maths::Abs"]
        self.assertFalse(index.examples[overloads[0].key()])
        self.assertTrue(index.examples[overloads[1].key()])
        symbols = self.symbols + [
            parse_decl("bool isTileSolid(uint16 tile)", "method", "CMap"),
            parse_decl("bool isTileSolid(const Tile&in tile)", "method", "CMap"),
            parse_decl("bool isTileSolid(Vec2f posWorldspace)", "method", "CMap"),
            parse_decl("<constructor>(float, float)", "method", "Vec2f"),
            parse_decl("Vec2f opAdd(const Vec2f&in)", "method", "Vec2f"),
            parse_decl("Vec2f opMul(float)", "method", "Vec2f"),
            parse_decl("CSprite", "class"),
            parse_decl("CSprite@ getSprite()", "method", "CBlob"),
            parse_decl("CSpriteLayer@ getSpriteLayer(int index)", "method", "CSprite"),
            parse_decl("CSpriteLayer@ getSpriteLayer(const string&in name)", "method", "CSprite"),
            parse_decl("bool isTileCastle(uint16 tile)", "method", "CMap"),
        ]
        # CBlob is not in the shared fixture; the sprite receiver only needs the return type.
        symbols.append(parse_decl("CBlob", "class"))
        text = """void f(CMap@ map, Vec2f pos, CBlob@ blob) {
 map.isTileSolid(pos + Vec2f(0, -3));
 blob.getSprite().getSpriteLayer("bubble" + "x");
 TileType t = getMap().getTile(0).type;
 map.isTileCastle(t);
 Vec2f delta = pos + Vec2f(1.0f, 2.0f);
}"""
        index = self.index(text, symbols=symbols)
        solid = next(
            s for s in symbols if s.source_declaration.startswith("bool isTileSolid(Vec2f")
        )
        self.assertTrue(index.examples[solid.key()])
        self.assertFalse(
            any(
                index.examples[s.key()]
                for s in symbols
                if s.source_declaration.startswith("bool isTileSolid") and s is not solid
            )
        )
        layer = next(s for s in symbols if "getSpriteLayer(const string" in s.source_declaration)
        self.assertTrue(index.examples[layer.key()])
        self.assertFalse(
            any(
                index.examples[s.key()]
                for s in symbols
                if s.source_declaration.startswith("CSpriteLayer@ getSpriteLayer(int")
            )
        )
        castle = next(s for s in symbols if s.name == "isTileCastle")
        self.assertTrue(index.examples[castle.key()])
        added = next(s for s in symbols if s.name == "opAdd")
        self.assertEqual(index.examples[added.key()][0].token, "+")

    def test_enum_constants_and_numeric_conversions_beat_generic_overloads(self):
        symbols = [
            parse_decl("CBlob", "class"),
            parse_decl("Vec2f", "class"),
            parse_decl("Tile", "class"),
            parse_decl("CMap", "class"),
            parse_decl("tile_empty", "enum-value", "CMap::TileEnum"),
            parse_decl("tile_empty", "enum-value", "Other::TileEnum"),
            parse_decl("void server_SetTile(Vec2f pos, const Tile&in tile)", "method", "CMap"),
            parse_decl("void server_SetTile(Vec2f pos, const uint16 type)", "method", "CMap"),
            parse_decl("outline", "enum-value", "RenderStyle::Style"),
            parse_decl("layer_posthud", "enum-value", "Render::ScriptLayer"),
            parse_decl("void RenderForHUD(Style style)", "method", "CBlob"),
            parse_decl("void RenderForHUD(Vec2f offset, Style style)", "method", "CBlob"),
            parse_decl(
                "int Render::addScript(ScriptLayer layer, const string&in name, const string&in func, float z)",
                "function",
            ),
            parse_decl("void set(const string&in, ?&in)", "method", "CBlob"),
            parse_decl("void set(const string&in, int64&in)", "method", "CBlob"),
            parse_decl("void set(const string&in, double&in)", "method", "CBlob"),
        ]
        catalogue = Catalogue(symbols)
        self.assertEqual(catalogue.enums["CMap::tile_empty"], "CMap::TileEnum")
        self.assertNotIn("tile_empty", catalogue.enums)
        index = self.index(
            """void f(CMap@ map, Vec2f pos, CBlob@ blob) {
 map.server_SetTile(pos, CMap::tile_empty);
 blob.RenderForHUD(RenderStyle::outline);
 Render::addScript(Render::layer_posthud, "WheelMenu.as", "render", 0.0f);
 blob.set("n", 1);
 blob.set("x", 1.0f);
 blob.set("blob", blob);
 blob.set("missing", unknown);
}""",
            symbols=symbols,
        )
        integer = next(s for s in symbols if "uint16" in s.source_declaration)
        self.assertTrue(index.examples[integer.key()])
        self.assertFalse(
            index.examples[
                next(s for s in symbols if "const Tile&in" in s.source_declaration).key()
            ]
        )
        by_decl = {
            s.source_declaration: index.examples[s.key()] for s in symbols if s.name == "set"
        }
        self.assertTrue(by_decl["void set(const string&in, int64&in)"])
        self.assertTrue(by_decl["void set(const string&in, double&in)"])
        self.assertTrue(by_decl["void set(const string&in, ?&in)"])
        hud = next(s for s in symbols if s.source_declaration == "void RenderForHUD(Style style)")
        self.assertTrue(index.examples[hud.key()])
        self.assertFalse(
            index.examples[
                next(s for s in symbols if "Vec2f offset, Style" in s.source_declaration).key()
            ]
        )
        self.assertTrue(index.examples[next(s for s in symbols if s.name == "addScript").key()])

    def test_script_class_initializer_and_untyped_this_field(self):
        index = self.index("""class Unknown { }
 void f() { Unknown map = getMap(); uint a = map.tilemapwidth; }
 class Holder { CMap@ map; void g() { uint b = this.map.tilemapheight; } }""")
        self.assertFalse(self.examples(index, "CMap::tilemapwidth"))
        self.assertTrue(self.examples(index, "CMap::tilemapheight"))


class GrammarTests(unittest.TestCase):
    def test_kag_extensions_and_multiline_comparisons(self):
        text = """class Info { Info() {}; };
 void f() {
 auto a = array<Vec2f>();
 auto b = int[][](1, int[](0));
 if (not enabled && value < LIMIT
     && other < 0
     && third < 1) {}
 auto c = array<
 Vec2f
 >();
 float v = float(1);
}"""
        self.assertEqual(ParsedSource.parse(text).errors(), [])

    def test_upstream_sources_match_recorded_hashes(self):
        root = Path(__file__).resolve().parents[1] / "vendor/tree-sitter-angelscript"
        provenance = json.loads((root / "provenance.json").read_text())
        for filename, digest in provenance["sha256"].items():
            self.assertEqual(
                hashlib.sha256((root / filename).read_bytes()).hexdigest(), digest, filename
            )


if __name__ == "__main__":
    unittest.main()
