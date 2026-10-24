"""Checks the shipped native place, not a second fake implementation of its game rules."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build", ROOT / "tools/build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PlaceExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.place = builder.build(Path(self.temp.name) / "LavaRush.rbxlx")
        self.tree = ET.parse(self.place)

    def named(self, class_name, name):
        matches = [node for node in self.tree.iter("Item")
                   if node.get("class") == class_name
                   and node.findtext("Properties/string[@name='Name']") == name]
        self.assertEqual(len(matches), 1, (class_name, name))
        return matches[0]

    def test_services_and_remote_contract(self):
        self.assertEqual(self.tree.getroot().get("version"), "4")
        for service in ("Workspace", "ReplicatedStorage", "ServerScriptService", "StarterPlayer"):
            self.named(service, service)
        remotes = self.named("Folder", "Remotes")
        self.assertEqual({item.findtext("Properties/string[@name='Name']") for item in remotes.findall("Item")}, {"Action", "Notice"})
        self.assertEqual({item.get("class") for item in remotes.findall("Item")}, {"RemoteEvent"})

    def test_embeds_all_current_sources_and_resolves_roblox_imports(self):
        locations = {
            "Rules": ("ModuleScript", "src/shared/Rules.luau"),
            "GameState": ("ModuleScript", "src/shared/GameState.luau"),
            "MapPlan": ("ModuleScript", "src/shared/MapPlan.luau"),
            "ProfileStore": ("ModuleScript", "src/server/ProfileStore.luau"),
            "LavaRushServer": ("Script", "src/server/Main.server.luau"),
            "LavaRushClient": ("LocalScript", "src/client/Main.client.luau"),
        }
        for name, (kind, path) in locations.items():
            embedded = self.named(kind, name).findtext("Properties/ProtectedString[@name='Source']")
            expected = (ROOT / path).read_text().replace('require("./Rules")', 'require(script.Parent:WaitForChild("Rules"))')
            self.assertEqual(embedded, expected)
            self.assertNotIn('require("./', embedded)
        server = self.named("ServerScriptService", "ServerScriptService")
        self.assertIn(self.named("ModuleScript", "ProfileStore"), server.findall("Item"))
        starter = self.named("StarterPlayerScripts", "StarterPlayerScripts")
        self.assertIn(self.named("LocalScript", "LavaRushClient"), starter.findall("Item"))

    def test_repeatable_build_and_distributed_place(self):
        before = self.place.read_bytes()
        builder.build(self.place)
        self.assertEqual(before, self.place.read_bytes())
        self.assertEqual(before, (ROOT / "dist/LavaRush.rbxlx").read_bytes())
        with ZipFile(ROOT / "dist/LavaRush.zip") as archive:
            self.assertEqual(archive.read("LavaRush/dist/LavaRush.rbxlx"), before)
            self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
