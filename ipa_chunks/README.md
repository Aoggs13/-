# Free Fire — Hardened IPA (chunked)

Файл 951 MB — GitHub single-file лимиті 100 MB, сондықтан 11 бөлшекке бөлінген.

## Не өзгертілген
- `Monite.dylib` → `GameCore.dylib` атауы
- `LC_ID_DYLIB`: `/Library/MobileSubstrate/DynamicLibraries/Monite.dylib` → `@executable_path/Frameworks/GameCore.dylib`
- Main binary `LC_LOAD_WEAK_DYLIB` сілтемесі жаңа атауға жаңартылды
- `SignedByEsign` маркер файлы өшірілді
- `LC_CODE_SIGNATURE` алынды (eSign қайта қолтаңбалайды)

## Біріктіру

**macOS / Linux / iOS (a-Shell, iSH):**
```bash
cat FreeFire_Hardened.ipa.part*.bin > FreeFire_Hardened.ipa
sha256sum -c FreeFire_Hardened.ipa.sha256   # сәйкестікті тексер
```

**Windows (PowerShell):**
```powershell
cmd /c "copy /b FreeFire_Hardened.ipa.part00.bin+FreeFire_Hardened.ipa.part01.bin+FreeFire_Hardened.ipa.part02.bin+FreeFire_Hardened.ipa.part03.bin+FreeFire_Hardened.ipa.part04.bin+FreeFire_Hardened.ipa.part05.bin+FreeFire_Hardened.ipa.part06.bin+FreeFire_Hardened.ipa.part07.bin+FreeFire_Hardened.ipa.part08.bin+FreeFire_Hardened.ipa.part09.bin+FreeFire_Hardened.ipa.part10.bin FreeFire_Hardened.ipa"
```

## Орнату
eSign / AltStore / Sideloadly / TrollStore арқылы `FreeFire_Hardened.ipa`-ны орнат.

## Патч нұсқасы (альтернатива)
Егер өзіңнің оригинал IPA-ң болса, толық файлды жүктеп алмай-ақ `patched_only/` ішіндегі екі файлды алмастыруға болады:
1. Оригинал IPA-ны ашу (zip ретінде)
2. `Payload/FreeFire.app/Frameworks/Monite.dylib` → өшір
3. `patched_only/GameCore.dylib` → `Payload/FreeFire.app/Frameworks/` ішіне көшір
4. `Payload/FreeFire.app/FreeFire` → `patched_only/FreeFire` мен ауыстыр
5. `Payload/FreeFire.app/SignedByEsign` → өшір
6. Қайта zip жасап `.ipa` кеңейтімі қой
