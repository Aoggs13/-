# Free Fire — Hardened IPA v2 (минималды өзгертулер)

v1 бұзылған болатын: `llvm-install-name-tool` `LC_CODE_SIGNATURE`-ны стрипип жіберген, eSign dylib-ты қайта қолтаңбалай алмай қалған → ойын крэш.

v2 — байт деңгейде LC_ID_DYLIB атын ғана қайта жазу, қолтаңба структурасы орнында, өлшем бит-дәл сақталған.

## Не өзгертілген
- `Monite.dylib` ішіндегі `LC_ID_DYLIB`: `/Library/MobileSubstrate/DynamicLibraries/Monite.dylib` → `@executable_path/Frameworks/Monite.dylib` (padded nulls)
- `SignedByEsign` маркер файлы жойылды

## Не өзгермеген
- Файл атауы `Monite.dylib` (өзгертпедім)
- `FreeFire` негізгі binary — бит-дәл оригинал
- `LC_CODE_SIGNATURE` командасы мен структурасы орнында (eSign стандартты түрде қайта қолтаңбалайды)
- Monite функционалы (heartbeat native restore + меню)

## SHA256
```
ea7d17bc9cdb75bc3ac218f30b5e9f8dfcdbd2bb5d6d946edb5979443e59153b
```

## Жүктеу
Бір файл — release-тен:
```
https://github.com/Aoggs13/-/releases/download/hardened-v1/FreeFire_Hardened.ipa
```

## Орнату
eSign арқылы орнат. AltStore / Sideloadly / TrollStore де жарайды.
