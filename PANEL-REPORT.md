> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Obnova skutečného panelu GNOME 50.5

**SHELL RELOAD — pouze panelový kontejner, jeho layout, gesta a správce menu.**
Celý Shell, GJS kontext, indikátory a Mutter přežívají. Skutečný restart celého
Shellu se zachováním původních klientských spojení dosud implementován není.
Hlavní cíl tedy zůstává otevřený.

## Nová hranice vlastnictví

Předchozí etapa obnovovala jen vlastní indikátor rozšíření. Nyní lokální Nix
override mění skutečné upstream soubory `js/ui/panel.js` a `js/ui/main.js`
v připnutém Shellu 50.5. Celý balík GNOME Shell byl lokálně sestaven.
Mutter zůstává původní 50.5. NixOS konfigurace ani živá relace se nemění.

Panel nově podporuje odložené připojení kontejneru bez konstrukce indikátorů.
Transakce pořídí snapshot role, objektu, boxu, pozice a viditelnosti každého
indikátoru. Připraví nový nativní `Panel` se třemi boxy a gestem. Starý panel
odregistruje menu a signály, uvolní kontejnery indikátorů a nový panel je
převezme. Až po úspěšném připojení do layoutu a správce focus skupin se starý
panel zničí. Exportovaná proměnná `Main.panel` pak ukazuje na nový panel.
Operace je synchronní bez vložené hlavní smyčky.

Původní indikátory včetně DateMenu, Quick Settings a jejich backendových
objektů se nekonstruují znovu. To je zásadní omezení, ale také konkrétní
dlouhodobá hranice: například `DateMenu` v upstream 50.5 registruje přímé
signály na `Main.sessionMode` a vlastním `WallClock`. Obnova těchto objektů
potřebuje další audit a teardown; tento patch jej nenahrazuje.

Upstream `_addToPanelBox()` používá opakovaně přidávané přímé signal handlery.
Patch je mění na signály vázané přes `connectObject()` na životnost panelu
a před novou registrací odpojuje jeho předchozí vazby na daném indikátoru.
Před transferem se také odstraní vazby menu-manageru a panelový příznak
`_openChangedConnected`, aby nový panel skutečně převzal správu menu.

Při částečně neúspěšném převzetí transakce uvolní vazby nového panelu,
zničí jeho kontejner a jednou připojí všechny původní indikátory zpět ke starému
panelu. Nepoužívá restart procesu ani retry smyčku. Kdyby selhal i samotný
návrat, chyba se propaguje; úplná odolnost vůči libovolné chybě GJS zaručena není.

## Přesně změněné soubory

| Soubor | Změna |
| --- | --- |
| `shell/panel-lifecycle.patch` | Odložená konstrukce panelu a spravované signály indikátorů |
| `shell/panelLifecycle.js` | Snapshot, transfer, rollback a měření zničených panelů; připojuje se do upstream modulu panelu |
| `shell/mainLifecycle.js` | Funkce `Main.reloadPanel()` a stav obnovy; připojuje se do upstream hlavního modulu |
| `flake.nix` | Balík `panel-shell` přes `overrideAttrs` a samostatný dev shell `panel` |
| `extension/extension.js` | Úzké D-Bus API pro patch a diagnostiku; žádný Eval |
| `tgnome.py` | Operace `reload-panel`; původní `reload-shell` je stále nepodporovaná |
| `tests/isolated.py` | Výměna skutečného panelu, menu, rollback a porovnání klientů |
| `README.md`, `REPORT.md`, `PANEL-REPORT.md` | Použití, důkazy a oddělení výsledků obou etap |

## Bezpečnost a podporovaný rozsah

Operace vyžaduje zděděné `TGNOME_ALLOW_PANEL_RELOAD=1` v procesu patchovaného
Shellu. Odmítne modal dialogy či otevřená menu, overview a jiný session mode
než `user`. Před transferem odmítne také děti panelových boxů mimo `statusArea`
a neznámá menu. Tyto kontroly nejsou zárukou kompatibility s libovolným
rozšířením; rozšíření mohou držet vlastní reference na starý panel.
Testováno je pouze vlastní řídicí rozšíření.

D-Bus používá existující uživatelské jméno Shellu a pevně definované metody.
Testovací změny overview a zkoušení menu vyžadují také izolované testovací
prostředí `TGNOME_TEST_FAILURES=1`. Skript nedohledává hostitelskou D-Bus
relaci. Patch nezpřístupňuje obecné spouštění JavaScriptu ani systémovou službu.

## Reprodukce a návrat

```sh
nix build .#panel-shell --no-link
nix develop .#panel -c python3 tests/isolated.py --output artifacts/panel-local
nix develop -c python3 tests/isolated.py --output artifacts/stock-local
nix flake check
```

První integrační příkaz spustí pouze vlastní headless Shell s virtuálním
monitorem, dočasnými XDG adresáři a soukromým D-Bus. Druhý testuje původní Shell.
Není potřeba přestavovat ani aktivovat NixOS nebo se odhlašovat. Testovací
procesy skript ukončí a dočasná konfigurace zanikne. Pro vrácení na původní
vývojovou variantu stačí používat `nix develop` místo `nix develop .#panel`.
Žádná systémová aktivace se nevrací, protože neproběhla.

Příkaz `nix run . -- reload-panel` má význam pouze s explicitně nastaveným
session bus adresovaným na tento patchovaný vývojový Shell. Do fyzické relace
nebyl nainstalován ani zkoušen. Na původním Shellu vrátí užitečnou chybu.

## Důkazy a limity

První úplný test `artifacts/panel-2/result.json` prošel: deset původních
panelových actorů bylo zničeno, existoval jeden aktuální panel, jedna jeho
focus skupina a sedm spravovaných menu. Všechny původní indikátory přežily.
Po každé výměně se podařilo otevřít a zavřít kalendář i Quick Settings,
bez zbylého modal grabu. Totéž fungovalo po vložené chybě a návratu.

Shell PID `1646803` přežil. Wayland klient PID `1647155` měl stále FD 3,
socket inode `5786012` a surface ID 10; jeho protokolový tick postoupil 3 → 24.
XWayland klient PID `1647162` měl stále FD 3, inode `5786016` a XID `2097156`;
tick postoupil 1 → 22. XWayland server PID `1647164` a jeho start time
`13529492` zůstaly stejné. Okna, geometrie, monitor, workspace a focus se shodovaly.
Klienti neobsahují reconnect a měření používá roundtrip původního nativního
display, nikoli pouze existenci PID.

Po tomto testu se kontrola chyby zpřísnila na selhání po skutečném převzetí
prvního indikátoru a přibylo měření celkového počtu focus skupin. Také tento
konečný běh prošel. Strojově čitelná evidence a logy jsou v
[artifacts/panel-final/result.json](evidence/reports/panel-final/result.json).

| Objekt | Konečný běh před / po |
| --- | --- |
| Patchovaný Shell | PID `1658547` beze změny |
| Wayland klient | PID `1658907`, FD 3, inode `5808633`, surface ID 10; tick 3 → 24 |
| XWayland klient | PID `1658915`, FD 3, inode `5809732`, XID `2097156`; tick 1 → 22 |
| XWayland server | PID `1658917`, start time `13543271` beze změny |
| Panel | Generace 10, deset starých actorů zničeno, jeden aktuální kontejner |
| Focus a menu | Jedna focus skupina panelu, celkem stále šest focus skupin a sedm menu |
| Rollback | Původní indikátory zachovány; kalendář i Quick Settings funkční, modalCount 0 |

Sestavený a testovaný Shell je
`/nix/store/p3ih4fgpgf1sb9gasfn5i6vxc89kvi14-gnome-shell-50.5`.
Kontrolní běh [artifacts/stock-final/result.json](evidence/reports/stock-final/result.json)
také prošel nad původním binárním Shellem a ověřil odmítnutí `ReloadPanel`
bez patche. `nix flake check` prošel včetně tří bezpečnostních unittestů.
Po skončení nezůstal žádný ze sledovaných testovacích procesů; hostitelský
Shell PID `1350942` nadále existoval. Živá relace nebyla restartována.

První pokus `artifacts/panel-1` správně odmítl výměnu, protože headless Shell
startoval do overview. Test teď toto odmítnutí výslovně ověřuje, overview
v izolované relaci zavře a teprve potom měří výměnu. Při sestavování dev shellů
se opravila také chyba duplicitního dynamického atributu Nixu. Očekávané
D-Bus výjimky při záměrně odmítnuté operaci a vložené chybě jsou v logu.

Tento výsledek nepředstavuje restart GJS kontextu, nové načtení zdrojových
ES modulů, obnovu celého UI, obnovu po pádu procesu ani session recovery.
Nemůže opravit zablokovanou hlavní smyčku. Fyzický desktop, více monitorů,
zamknutí obrazovky a libovolná další rozšíření nebyly testovány.

Další krok k původnímu cíli: zavést plný teardown vybraného skutečného
indikátoru včetně backendových signálů a opakovaně ho vytvořit za stejné
kontroly klientských spojení. Potom lze hranici rozšířit na panelové služby
a další subsystémy UI. Trvalá správa oken, vstupu, screen locku a compositoru
musí zůstat mimo obnovovanou část.
