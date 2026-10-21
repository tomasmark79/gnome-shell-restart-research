> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Výměna celého GJS kontextu — laboratorní etapa

**RESEARCH PROTOTYPE. Bezpečný opakovatelný restart celého Shellu není hotový.**

Varianta `runtime-shell` odděluje životnost GJS od nativní smyčky Mutteru.
Pokusy prokázaly finalizaci původního GJS, vznik nového UI a přežití původních
spojení klientů. Zároveň odhalily prostředky přežívající generaci, kvůli kterým
test správně neuznává splnění hlavního cíle.

## Implementace

Upstream `init.js` spouští Mutterovu smyčku z GJS hooku. Nový build pouze
naplánuje start UI a vrátí se do `main.c`; smyčka pak běží v C mimo zásobník
GJS. Kontrolní headless běhy prošly původními testy klientů, panelu a rollbacku.

Nativní endpoint `/org/gnome/Shell/TgnomeRuntime` na původním bus owneru dovolí
číst stav a naplánovat jediný `ResetProbe`. Vzniká pouze s explicitním
`--headless`, `TGNOME_ALLOW_RUNTIME_RESET=1` a bez vlastního `GNOME_SHELL_JS`.
Brána vyžaduje také přípravu UI. Veřejný příkaz `reload-shell` zůstává
nepodporovaný. Opakovaný laboratorní pokus se odmítne bez další výměny.

Příprava dokončí asynchronní zápis historie časových limitů za života UI,
odregistruje zachycené klávesové zkratky a vypne řídicí rozšíření. Zvláštní
signál `tgnome-ui-reset` uklidí UI, ale nevyvolá skutečný nativní shutdown:
ten totiž odpojuje i mapování oken v `ShellWindowTracker`.

Layout přesune původní nativní skupiny oken/feedbacku zpět na stage a zničí
svůj `uiGroup`. Zbytek evidovaných GLib zdrojů vytvořených JS se zruší ještě
před výměnou kontextu. Nativní zdroje compositoru se neruší. Následuje uvolnění
GJS a vytvoření nového; finalizaci měří weak notify, novou generaci náhodný
`runtimeEpoch`. Nové UI při obnově nespouští přihlašovací overview.

Test po prvním ověření PID připne jedinečné D-Bus jméno. Díky tomu po jeho
zániku nemůže kontrolní dotaz omylem aktivovat jiné provedení Shellu.

## Překážky a opravy

- První skutečné odstranění GJS proběhlo, ale nový import selhal na již
  registrovaném `Gjs_TransientSignalHolder`. Kontrolu potvrzuje
  [GJS 1.88.1, GObject.js](https://github.com/GNOME/gjs/blob/1.88.1/modules/core/overrides/GObject.js#L287).
  `--unique-gtypes` přidává názvy generací pouze pro další výzkum. Registrace
  tím nezanikají: růst měřených GObjektových typů je nadále důvodem FAIL.
- Původní teardown zničil UI před asynchronním zápisem, jehož nested loop
  pustil callbacky do zničených widgetů. Příprava nyní dokončí zápis předem
  a druhý nested loop přeskočí.
- Nová generace původně znovu registrovala ponechané klávesové zkratky.
  Registry JS generace nyní předem odregistruje vlastní `add_keybinding()`;
  v připraveném pokusu jich bylo 37. Fyzické zadávání kláves testováno není.
- Delší běh odhalil opožděné GLib callbacky do zaniklého kontextu.
  Instrumentace sleduje JS timer/idle API a `GLib.Source.attach()` a ruší
  jejich zbytek po teardownu. Úplný audit všech asynchronních rozhraní GIO
  ani dalších knihoven zatím prokázán není.

Pracovní buildy/starty také odhalily a opravily kontext/počty řádků patchů,
rozdílný typ statusu `gjs_context_eval()` a modulového eval API, nečitelnou
vlastnost `search-path` a ztrátu přijímače `this` v obalení funkcí GLib.
Tyto neúspěchy nejsou uváděny jako průchozí ověření.

## Dosavadní evidence

| Adresář v `artifacts/` | Výsledek |
| --- | --- |
| `native-loop-baseline`, `native-loop-final` | Průchozí původní integrační testy s nativní smyčkou |
| `runtime-reset-1` | Finalizace GJS, selhání nového importu na duplicitním typu; klienti přežili |
| `runtime-reset-types` | Nový GJS i panel; FAIL kvůli overview, ponechaným prostředkům a diagnostice |
| `native-prepared-baseline` | Průchozí kontrola přípravy a správy zkratek |
| `runtime-prepared` | Shodný desktop a funkční menu po 65 sekundách, ale callbacky a růst GTypů stále znamenají FAIL |
| `runtime-sources`, `native-sources-baseline` | Pracovní instrumentace selhala při startu; přijímač GLib wrapperů byl následně opraven |

V běhu `runtime-prepared` se epoch změnil z
`92e66541-a6a1-4291-9504-b8437b18f98a` na
`0d9bb6e4-6794-4c9f-b1f4-1f7a6e6fa3e2`, s jednou potvrzenou finalizací.
Okna, geometrie, workspace, focus a overview se shodovaly. Původní klienti
pokračovali v roundtripech bez reconnectu:

- Wayland PID `1713055`, FD 3, inode `5918080`, surface ID 10, po resetu tick 357.
- XWayland klient PID `1713062`, FD 3, inode `5910488`, XID `2097156`, tick 355.

Počet měřených typů vzrostl 359 → 718 a diagnostika obsahovala čtyři vadné
callbacky. Přetrvání spojení tedy není vydáváno za bezpečný restart.

## Konečný běh této etapy

[artifacts/runtime-baseline-final/result.json](evidence/reports/runtime-baseline-final/result.json)
prošel. [artifacts/runtime-sources-final/result.json](evidence/reports/runtime-sources-final/result.json)
po doplnění evidence GLib zdrojů nadále skončil **FAIL**. Jde o skutečně
neúspěšnou integrační bránu, nikoli očekávaný neúspěch přeznačený na úspěch.

| Měření | Hodnota |
| --- | --- |
| Shell | PID `1734961`, zůstal stejný |
| Kontext | Starý epoch `1dc1d034-4555-4348-b9f7-c411a5b7684c`, nový `8519a00e-428e-43c6-809a-cd15c4916134`; jedna finalizace |
| Wayland | PID `1735315`, FD 3, inode `5957411`, surface ID 10 beze změny; tick po resetu 357 |
| XWayland klient | PID `1735335`, FD 3, inode `5960458`, XID `2097156` beze změny; tick po resetu 355 |
| Stav UI | Shodná okna, geometrie, focus, workspace, overview; dokončený startup, funkční testovaná menu |
| Doba pozorování | 65 sekund po obnovení UI |
| Prostředky | 37 zkratek předem uvolněno; GObjektové typy 359 → 718 |
| Diagnostika | Stále čtyři problematické události po resetu; cleanup všech callbacků není prokázán |
| Další požadavek na reset | Odmítnut; native stav a počet typů před/po odmítnutí shodný |

Testovaný balík je `/nix/store/m9l6dsy29k6ki5v3k8gyqh2srg11m7w2-gnome-shell-50.5`.
Po úklidu nebyl přítomen žádný ze sledovaných procesů obou testů. Hostitelský
Shell PID `1350942` stále existoval. Dodatečná kontrola prostředí všech procesů
uživatele nenašla žádný zbylý proces se soukromým `tgnome` runtime adresářem.
`nix flake check` prošel včetně pěti
bezpečnostních unittestů. Proces Shellu/Mutteru nebyl během resetu nahrazen;
měnil se jeho GJS kontext. Fyzická relace ani zachování neuložených dat
v libovolných aplikacích nebyly testovány. Zablokovanou JS smyčku tento
jednovláknový mechanismus neumí přerušit.

## Reprodukce a návrat

```sh
nix build .#runtime-shell --no-link
nix develop .#runtime -c python3 tests/isolated.py --output artifacts/runtime-baseline-local
nix develop .#runtime -c python3 tests/isolated.py --reset-runtime --unique-gtypes --soak-seconds 65 --output artifacts/runtime-reset-local
nix flake check
```

Resetový experiment může skončit nenulově. `result.json` odděluje
`baselinePassed`, `testedUiChecksPassed`, `requiredBehaviorDemonstrated`, počty
typů, native stav, epoch a klienty. `reset.log` zachycuje diagnostiku resetu;
závěrečný úklid vlastních procesů je navíc v `shell.log`.

Jde výhradně o soukromý headless test. Systémová aktivace ani fyzická relace
se nemění. Návrat k původní variantě pro test je `nix develop`, k panelové
variantě `nix develop .#panel`. Obnova relace či neuložených dat není implementována.

## Soubory a další krok

Nové soubory jsou `shell/native-loop.patch`, `shell/tgnome-runtime.h`,
`shell/runtimeGlobal.c.inc` a `shell/runtimeInit.js`. Změny ve `flake.nix`
přidávají samostatný balík/dev shell `runtime`. Controller v
`extension/extension.js` připravuje reset a reportuje epoch/startup.
`tgnome.py`, `tests/isolated.py` a `tests/test_safety.py` přidávají připnutí
bus ownera, nativní experiment, delší pozorování a bezpečnostní kontroly.

Další návrhový krok je porovnat trvalý GJS kontext s úplným životním cyklem
UI instancí proti změně registrace tříd v GJS. Jednorázové unikátní GTypy
neřeší opakovatelnost ani konečnou životnost prostředků. Samotné předání
Wayland socketu nebo změna názvu procesu tyto prostředky nepřenese.
