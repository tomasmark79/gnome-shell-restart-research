> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Zámek přicházející během obnovy UI

## Ověřený výsledek

Dva nové NixOS VM scénáře prošly skutečným logind zámkem během přípravy
a během čekající konstrukce UI. Druhý zahrnuje vypršení konstrukce, jeden
nápravný pokus a 400 klávesových událostí přes tuto hranici. Původní Wayland
i XWayland klient zachovaly spojení, okno a hash neuloženého textu.
Poté skutečný PAM odmítl chybné heslo a správné heslo odemklo tutéž relaci.

Klasifikace zůstává **SHELL RELOAD**. Jde o stejné GJS, Mutter a Shell proces.
Testované případy předpokládají, že požadavek na zámek přijal živý ScreenShield;
to potvrzuje `LockedHint=yes` ještě během konstrukce. Nepokrývají každý okamžik
doručení zámku, neodpovídající JS ani pád procesu.

## Nalezené chyby a opravy

1. Odemčený dialog ponechal reference na správce pozadí. Soukromá halda ukázala
   trvalý Background s `_layoutManager` a cestami do starého ScreenshotUI
   a MessageTray. Zničení UnlockDialog nyní uvolní i jeho BackgroundManager
   instance a tím reference na cachovaný zdroj pozadí.
2. Zrušený ScreenShield ponechal native idle watch; aktivita uživatele pak
   vstupovala do zničených Lightbox objektů. Teardown tento watch odstraní.
   Uvolňuje také oba modální graby před zrušením evidence modálního zásobníku.
3. Proud kláves přes nápravný pokus odhalil stav `mode=unlock-dialog`, ale
   `locked=false` a `active=false`. Samotný režim relace neprokazuje zámek.
   VM varianta proto drží požadavek na zámek mimo jednotlivé kandidáty UI.
   Zrušené ScreenShield instance nesmějí pokračovat v odemykacích callbackách
   a výchozí `_isLocked=false` nového kandidáta neznamená ověřené odemčení.
4. Během destrukce a konstrukce chrání VM samostatná černá St.Widget clona
   přímo na stage s vlastním native vstupním grabem. Přežije zničení uiGroup
   a zůstává nad nově přidanými skupinami. Před potvrzením konstrukce musí nový
   ScreenShield převzít požadovaný zámek; teprve po nativním potvrzení se clona
   uvolní. Zamčené UI nedostane zpět `ActionMode.NORMAL`.

Tato ochrana se aktivuje pouze ve zvláštní ověřené VM variantě. Běžný stable
balíček zachovává headless omezení a clonu nevytváří.

## Přesný rozsah scénářů

`security-preparation-vm` po prvním reloadu zadrží další přípravu na tři sekundy.
Logind během nativního stavu `ui-preparing` zamkne relaci. Finální kontrola
před mutací vrátí chybu `UI changed before preparation commit` a ponechá původní
UI i zámek. Rezervace spotřebuje laboratorní slot, ale nevytvoří další kandidát.
Po autentizaci uspěje poslední explicitní požadavek. Výsledek: tři rezervace,
dva commity, jedno selhání přípravy, žádné automatické opakování ani timeout.

`security-construction-vm` zadrží druhou konstrukci na Main startup checkpointu.
Před vypršením pěti sekund doručí logind zámek a ověří `LockedHint=yes`.
Pořídí skutečný snímek clony a posílá 400 znaků `x` s rozestupem 15 ms přes
timeout a automatický nápravný pokus. Před proudem je nativní stav
`same-context-ui-starting`, po něm `ui-ready`. Klientské hashe zůstávají stejné.
Výsledek: dva externí pokusy, tři kandidáti, dva commity, jeden timeout,
jedno selhání a právě jedno automatické opakování.

Nativní diagnostická maska `securityBoundaryBits` má bity: 1 inicializovaná
hranice, 2 požadovaný zámek, 4 viditelná clona, 8 držený grab a 16 clona
nejvýše na stage. Před proudem kláves byla 31; po převzetí zámku novým UI
byla 3. Po skutečném odemčení zůstává pouze bit inicializace.
Jde o vývojovou diagnostiku, nikoli veřejnou stabilní API smlouvu.

Kontrola chybného hesla nyní vyžaduje nový PAM failure až za čerstvým journal
kurzorem a čeká na znovu aktivní vstup. Dřívější chyba nebo probíhající ověření
tak nestačí. Veřejné a nativní reload RPC jsou při zámku nadále odmítnuté.
Přirozeně přibývající GTypes autentizace se nepletou do čítačů transakce.

## Konečné výsledky

| Scénář | Výstup Nix testu | Doba skriptu | Vybrané staré objekty uvolněné GC |
| --- | --- | --- | --- |
| Příprava | `/nix/store/zqmmv4cglsapahqkx0qzki6ridg37k5r-vm-test-run-tgnome-security-preparation` | 37,98 s | 26 |
| Konstrukce | `/nix/store/zffyypdw8n7baivx9dylisf52nfz9i1v-vm-test-run-tgnome-security-construction` | 42,13 s | 39 |

Oba mají `passed=true`, čistou sledovanou diagnostiku, úspěšné nezávislé retenční
kontroly a řádný konec driveru včetně ukončení VM. Shell PID zůstal 981
u přípravy a 983 u konstrukce; logind session ID zůstalo `1`.

| Scénář / klient | Původní PID | Socket inode | Komunikační čítač před → po |
| --- | --- | --- | --- |
| Příprava / Wayland | 1582 | 14063 | 9 → 78 |
| Příprava / XWayland | 1676 | 14146 | 4 → 73 |
| Konstrukce / Wayland | 1611 | 15700 | 9 → 102 |
| Konstrukce / XWayland | 1680 | 13847 | 4 → 98 |

FD, identita okna a hash textu se také nezměnily. Snímky černé clony během
konstrukce, odmítnutého hesla a odemčeného desktopu byly vizuálně zkontrolovány.
Jeden snímek a jeden proud vstupu nepředstavují důkaz všech možných časování.

VM balíček je `/nix/store/7kb68fkpknq47gbdghwb087g3v3f2nfq-gnome-shell-50.5`,
derivace `/nix/store/7nnbw54a4zck8l90ls4gzih9lz2dvfsr-gnome-shell-50.5.drv`.
Kompilace s `--cores 0` skutečně použila `-j16`.

Headless regrese `artifacts/security-curtain-headless-regression` také prošla:
řízený startup timeout, jedno opakování, tři commity a sledování 65,007 s,
bez problémů diagnostiky, s `workerExitCode=0` a odstraněným soukromým profilem.
Použila `/nix/store/nh98i34bkh93zg144vypvl2mlg1vpx9j-gnome-shell-50.5`,
`securityVm=false`, `securityBoundaryBits=0`. `nix flake check --cores 0` prošel.

## Reprodukce

```sh
nix build --cores 0 --print-build-logs .#security-preparation-vm --out-link result-security-preparation-vm
nix build --cores 0 --print-build-logs .#security-construction-vm --out-link result-security-construction-vm
cat result-security-construction-vm/evidence/tgnome-evidence/result.json
nix flake check --cores 0
```

Reporty a guest journal jsou v `evidence/tgnome-evidence/`, PNG přímo v kořeni
výstupu testu. Diagnostický neúspěšný běh s haldou zůstává v
`artifacts/security-preparation-heap/`; jeho `passed=false` je správně zachované.

Implementace: `shell/stableSecurity.js`, `shell/stableScreenShield.js`,
`shell/stableUnlockDialog.js`, `shell/stableMain.js`, `shell/tgnome-runtime.h`,
`tests/vm-security.py`, `tests/vm-security.nix` a cíle ve `flake.nix`.
Při vývoji byly opraveny i testovací předpoklady o rezervaci slotu, expanzi
shellového příkazu v guestu a nedostupnosti UI-owned Eval během checkpointu.
První sestavení clony potřebovalo doplnit explicitní import Clutter.

## Co stále chybí

Následný [DURABLE-LOCK-REPORT.md](DURABLE-LOCK-REPORT.md) již ověřuje logind
požadavek v mezeře bez ScreenShieldu a přidává nezávislý backendový odběr.
Níže zůstává původní rozsah a doporučení této předchozí fáze.

Přijetí logind Lock při nepřítomném ScreenShieldu ještě nemá nezávislý trvalý
odběr. Zbývá ověřit tuto mezeru, zámek přes vyčerpání nápravy a karanténu,
další způsoby autentizace, monitorové změny a obecné callbacky během chyb.
Clona i stav žijí ve stejném GJS, takže neřeší jeho synchronní zablokování
nebo pád kompozitoru. Hostitelská fyzická relace se netestovala; aktivace
NixOS ani restart hostitelských služeb neproběhly.
