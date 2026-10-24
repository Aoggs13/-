#!/usr/bin/env python3
"""Build a native Roblox place and a deterministic source bundle, without dependencies."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def build(output=None):
    output = Path(output) if output else ROOT / "dist" / "LavaRush.rbxlx"
    tree = ET.Element("roblox", {"version": "4"})
    ET.SubElement(tree, "External").text = "null"
    ET.SubElement(tree, "External").text = "nil"
    count = 0

    def item(parent, class_name, name, properties=()):
        nonlocal count
        count += 1
        node = ET.SubElement(parent, "Item", {"class": class_name, "referent": f"RBX{count}"})
        props = ET.SubElement(node, "Properties")
        ET.SubElement(props, "string", {"name": "Name"}).text = name
        for kind, key, value in properties:
            ET.SubElement(props, kind, {"name": key}).text = str(value)
        return node

    def source(parent, class_name, name, relative):
        body = (ROOT / relative).read_text(encoding="utf-8")
        # Standalone Luau modules use file-relative requires; Roblox uses Instances.
        body = re.sub(r'require\([\'"]\./Rules[\'"]\)', 'require(script.Parent:WaitForChild("Rules"))', body)
        if re.search(r'require\([\'"]\.', body):
            raise ValueError(f"Unresolved filesystem require in {relative}")
        return item(parent, class_name, name, [("ProtectedString", "Source", body)])

    item(tree, "Workspace", "Workspace", [("float", "Gravity", "196.2")])
    storage = item(tree, "ReplicatedStorage", "ReplicatedStorage")
    shared = item(storage, "Folder", "LavaRush")
    for name in ("Rules", "GameState", "MapPlan"):
        source(shared, "ModuleScript", name, f"src/shared/{name}.luau")
    remotes = item(shared, "Folder", "Remotes")
    for name in ("Action", "Notice"):
        item(remotes, "RemoteEvent", name)
    server = item(tree, "ServerScriptService", "ServerScriptService")
    source(server, "ModuleScript", "ProfileStore", "src/server/ProfileStore.luau")
    source(server, "Script", "LavaRushServer", "src/server/Main.server.luau")
    starter = item(tree, "StarterPlayer", "StarterPlayer", [
        ("float", "CameraMinZoomDistance", "5"),
        ("float", "CameraMaxZoomDistance", "70"),
        ("float", "CharacterWalkSpeed", "18"),
        ("float", "CharacterJumpPower", "50"),
        ("bool", "CharacterUseJumpPower", "true"),
    ])
    starter_scripts = item(starter, "StarterPlayerScripts", "StarterPlayerScripts")
    source(starter_scripts, "LocalScript", "LavaRushClient", "src/client/Main.client.luau")
    ET.indent(tree, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(tree).write(output, encoding="utf-8", xml_declaration=True)
    return output


def bundle(place):
    target = place.parent / "LavaRush.zip"
    sources = [p for p in ROOT.rglob("*") if p.is_file()
               and "dist" not in p.relative_to(ROOT).parts
               and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(sources + [place]):
            relative = str(path.relative_to(ROOT))
            info = ZipInfo("LavaRush/" + relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return target


if __name__ == "__main__":
    place = build()
    archive = bundle(place)
    print(f"Built {place} ({place.stat().st_size:,} bytes)")
    print(f"Bundled {archive} ({archive.stat().st_size:,} bytes)")
