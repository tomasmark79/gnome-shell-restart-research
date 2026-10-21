> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Obnova izolovaného Shellu po přerušení JS callbacku

Tento report popisuje fázi 19 s callbackem bez rozpracované UI změny.
[PANEL-INTERRUPT-REPORT.md](PANEL-INTERRUPT-REPORT.md) přidává následující důkaz
obnovy dvou skutečných rozpracovaných přenosů panelu.

## Výsledek

Oddělený headless GNOME Shell 50.5 přežil nekonečný JS callback. Nativní
watchdog jej po jedné sekundě přerušil, GLib převzal řízení a přes existující
vlastněný protokol proběhla rekonstrukce desktopového UI. Původní Wayland
i XWayland klienti zachovali procesy, sockety, okna a testovací neuložená data.

Klasifikace: **SHELL RELOAD**, nikoli **TRUE RESTART**.
`controlledBlockedJsRecovered=true`, `trueRestartDemonstrated=false`,
`wholeShellReloadDemonstrated=false`. Mutter, Shell proces a GJS kontext
zůstaly stejné. Jde o důkaz obnovy jednoho přesně vymezeného zablokování,
nikoli obecné zotavení libovolně poškozeného Shellu.

## Implementace

`interruption-shell` je nový, samostatný balíček. Používá privátní GJS
z [BOUNDARY-REPORT.md](BOUNDARY-REPORT.md); běžný `stable-shell` a bezpečnostní
VM varianty jej nepřebírají. Linkování ověřeno přes `ldd`:

- Shell: `/nix/store/5r7q6n1kybl9mv892gvzmnv7m0ami9w4-gnome-shell-50.5`
- GJS: `/nix/store/mg2lakhqrm438li6vk6gijjgd183nswk-tgnome-gjs-1.88.1`
- SpiderMonkey: `/nix/store/gl229ccpyhpdhi5fwjz33zqrhfhvvgpx-spidermonkey-140.14.0`

C++ watchdog vzniká až po návratu inicializačního modulového eval, zatímco
dlouhodobou smyčku vlastní nativní Mutter. Vlastní jediné vlákno a jediný
povolený pokus; při zastavení se vlákno spojí před likvidací kontextu.
Neozbrojený watchdog nevyvolává časové přerušení.

Privátní metoda `InterruptUiProbe` naplánuje GLib callback s `while (true)`.
Callback pouze zaznamená vstup a obsahuje kontrolní `catch` a `finally`;
nezahajuje další změnu backendového modelu. Po návratu plánovacího eval se
ozbrojí watchdog. Interrupt hook na JS vlákně požádá ochranu GJS o povolení;
při odmítnutí engine nepřeruší. Při povolení naplánuje nativní idle zdroj
a vrátí `false`.

Po návratu z přerušeného callbacku nativní idle zavolá `ReloadDesktopUi`
přes vlastní D-Bus spojení Shellu. Použije stávající přípravu, commit,
kandidáty a limit oprav; nevytváří druhý neomezený obnovovací cyklus.
Jde o testem výslovně ozbrojený watchdog, nikoli automatický detektor všech
zamrznutí. Druhý pokus je odmítnut před naplánováním další smyčky.

Endpoint vyžaduje samostatnou compile-time variantu, původní headless gate,
trvalý kontext a `TGNOME_ALLOW_INTERRUPTION=1`. Bezpečnostní VM je vyloučena.

## Naměřené výsledky

Autoritativní artefakty:
[result.json](evidence/reports/interruption-shell-1/result.json),
supervisor.json (not exported: `artifacts/interruption-shell-1/supervisor.json`),
in-place.log (not exported: `artifacts/interruption-shell-1/in-place.log`).

Celý příkaz skončil exit 0. Výsledek má `passed=true`; vnější supervisor
potvrdil `workerExitCode=0` a `privateProfileRemoved=true`.

| Identita | Před a po obnově |
| --- | --- |
| Shell PID | 2743446 |
| GJS runtime epoch | `0466f38e-f347-414d-b8b3-bb030a8388b4` |
| Wayland klient | PID 2743766, fd 3, inode 7804720, windowId 10 |
| X11 klient | PID 2743776, fd 3, inode 7793517, windowId 2097156 |
| XWayland | PID 2743778, stejný executable i startTime |

Wayland tick vzrostl z 3 na 409, X11 tick z 1 na 410. Kontrola všech průběžných
záznamů zachovala původní identity a hashe neuloženého textu až do následného
záměrného testu psaní. Nativní virtuální klávesnice pak upravila text obou
původních oken na očekávané nové hashe. Pozdní nové Wayland/X11 klienty také
šlo připojit a zavřít.

Watchdog: `delivered=1`, `denied=0`, `nativeResumptions=1`. Kontrolní příznaky
potvrdily vstup do smyčky a přeskočení `catch` i `finally`. Druhý požadavek
na přerušení byl odmítnut bez změny výsledného stavu watchdogu.

První rekonstrukci vyvolal watchdog; další dvě byly běžné vlastněné požadavky.
Finální stav má tři commity, žádné chyby konstrukce, žádný retry a žádnou
karanténu. Po třech generacích se sebralo 39 sledovaných objektů včetně
nezávislých kontrol; tři úmyslně držené kontrolní objekty zůstaly živé.
Sledované registry a inventář stage se shodovaly s výchozím stavem.

Pozorování opožděných callbacků trvalo 65,0078 s. Log obsahuje právě jednu
očekávanou diagnostiku `TGNOME explicit interruption at native boundary`;
další diagnostické problémy: 0. Test tuto konkrétní zprávu samostatně vyžaduje,
neignoruje obecně JS chyby. Snímek desktopu (not exported: `artifacts/interruption-shell-1/desktop-after.png`)
byl vizuálně zkontrolován: obnovený panel a obě původní okna jsou vykreslené.

Samostatná [regrese s neozbrojeným watchdogem](evidence/reports/interruption-unarmed-regression/result.json)
také prošla, včetně vnějšího exit 0 a odstranění profilu. Injektovaná chyba
po konstrukci panelu vyvolala jeden běžný opravný pokus; tři UI commity byly
dokončeny a diagnostické problémy byly 0. Stav watchdogu před i po zůstal
`delivered=0`, `denied=0`, `nativeResumptions=0`, bez fixture a požadavku obnovy.
Tato regrese neměla prodloužený soak; 65sekundové pozorování patří výše
popsanému běhu s přerušením.

## Reprodukce a oddělení od hostitele

```sh
nix build --cores 0 -L .#interruption-shell --out-link result-interruption-shell
nix develop .#interruption --cores 0 -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --track-time --interrupt-js \
  --soak-seconds 65 --output artifacts/interruption-local
nix flake check --cores 0
```

Kompilace použila `-j16`, bez compiler warnings. `nix flake check` po
implementaci prošlo včetně nové varianty supervisorového testu.
První dvě sestavení odhalila chybný počet řádků a poté nesprávné pozice hunků
Meson patche. Opravený patch se aplikuje s `--fuzz=0`; třetí sestavení prošlo.

Test používá vlastní D-Bus, logind mock, XDG profil, headless výstup, klienty
a procesní skupiny. Neprovádí NixOS aktivaci ani instalaci do hostitelské relace.
Hostitelský Shell při kontrole stále měl PID 1350942 a původní executable.
Návrat nevyžaduje systémový zásah: test odstranil svůj profil; volitelný odkaz
lze odstranit příkazem `rm result-interruption-shell`.

Změněné soubory: `flake.nix`, `shell/interrupt-shell.patch`,
`shell/interruptWatchdog.h`, `shell/interruptWatchdog.cpp`,
`shell/interruptRuntime.h`, `shell/tgnome-runtime.h`, `tests/isolated.py`
a dokumentace.

## Co chybí k původnímu cíli

- Obnova libovolného zablokování: watchdog je výslovně ozbrojený fixture,
  nikoli obecný hlídač dostupnosti. Promise jobs, modulové vstupy a nepodporované
  vnoření ochrana odmítá; nemá pro ně bezpečnou obnovu.
- Konzistence po přerušení rozpracované UI/backend operace. Přeskočené `finally`
  může zanechat změněný lifetime čítač nebo trvalý model. Testovaný callback
  takovou operaci neobsahuje a nic o její obnově neprokazuje.
- Bezpečnost při současném zamknutí: kombinace přerušení JS, nezávislé ochranné
  clony a skutečné PAM autentizace nebyla v této fázi testována.
- Úplné vytvoření nového GJS runtime, restart procesu, nativní C deadlock
  a pád kompozitoru. Pro zachování spojení při restartu celého procesu je
  nadále třeba silnější architektonická hranice.

Další krok má ověřit přerušení rozpracované operace s evidovaným vlastnictvím
a zotavením jejího stavu, následně automatickou detekci ve známém povoleném
vstupu. Rozšíření watchdogu na všechny callbacky by dosavadní důkaz zobecnilo
bez potřebného podkladu.
