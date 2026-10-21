> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Logind zámek při chybějícím ScreenShieldu

## Výsledek

VM nyní přijme skutečný logind požadavek na zámek i v řízené mezeře mezi
zničením starého ScreenShieldu a vytvořením nového. Nezávislý backendový odběr
uchová požadavek a nastaví `LockedHint`. Trvalá clona chrání obraz a vstup
přes vypršení konstrukce a jeden nápravný pokus. Náhradní ScreenShield pak
převezme zámek; chybné heslo odmítne PAM a správné odemkne stejnou relaci.

Původní Wayland i XWayland klient zachovaly spojení, okno a hash neuloženého
textu během 400 klávesových událostí přes nápravu. Klasifikace je stále
**SHELL RELOAD**: GJS, Mutter i Shell proces zůstávají stejné.

## Implementace

`stableLoginManager.js` připojuje právě jeden trvalý `Lock` odběr k aktuální
logind session proxy. Jeho registrace má backendový životní cyklus a přežije
odpojení UI odběratelů. Callback neodkazuje na žádný ScreenShield; předá
požadavek trvalé bezpečnostní hranici a asynchronně potvrdí `SetLockedHint`.
Stávající UI odběr zůstává přechodný a při teardownu se odpojí.

Nový řízený checkpoint `security-gap` čeká před konstrukcí ScreenShieldu.
Nativní diagnostická maska prokazuje současně jeho nepřítomnost, aktivní
checkpoint a chránící clonu. Před logind požadavkem byla maska 125, po jeho
přijetí 127. Po převzetí zámku novým UI byla 3 a trvalý odběr zaznamenal
přesně jeden požadavek. Nové bity 32 a 64 znamenají nepřítomný ScreenShield
a čekání v tomto checkpointu; nižší bity popisuje LOCK-RACE-REPORT.md.

Test dále ověřuje vypršení pěti sekund, právě jeden nápravný pokus, nativní
commit a skutečné GDM/PAM odemčení. UI-owned Eval není během checkpointu
dostupné; pozorování používá nativní endpoint a skutečný logind.

## Nalezená další chyba

První běh správně zachoval zámek, ale neprošel diagnostikou: starý kalendář
uvolnil `Gio.DBusProxy` během jeho asynchronní inicializace. Následné
`init_finish` a připojování signálů vstupovaly do již zrušeného proxy.

`calendar-lifetime.patch` proto používá `Gio.Cancellable`, označuje zrušený
zdroj a odloží `run_dispose` až po dokončení inicializačního callbacku.
Po zrušení již nepřipojí nové signály. Běžné dokončené proxy se uvolňují
přímo; opakované zničení je idempotentní. Diagnostická kontrola nebyla oslabena.

## Konečné důkazy

| Scénář | Výstup | Doba driveru | Vybrané staré UI objekty uvolněné GC |
| --- | --- | --- | --- |
| Bez ScreenShieldu | `/nix/store/y0hlw3vfdhsjixg8a13939v7vglcw0dp-vm-test-run-tgnome-security-security-gap` | 40,40 s | 29 |
| Regrese s existujícím ScreenShieldem | `/nix/store/vnynsx2d62927pjk065zz7dx8xfcjns4-vm-test-run-tgnome-security-construction` | 41,84 s | 39 |

Oba mají `passed=true`, prázdnou sledovanou diagnostiku, správné nezávislé
retenční kontroly a řádné ukončení VM. V novém scénáři zůstaly Shell PID 981
a logind session ID `1`. Původní klienti:

| Klient | PID | Socket inode | Komunikační čítač před → po |
| --- | --- | --- | --- |
| Wayland | 1583 | 14086 | 9 → 96 |
| XWayland | 1683 | 14958 | 4 → 92 |

Také FD, identita okna a hash textu zůstaly shodné. Černá clona, odmítnuté
heslo a odemčený desktop byly vizuálně zkontrolovány na skutečných snímcích VM.
Nativní stav zaznamenal dva externí pokusy, tři kandidáty, dva commity,
jeden timeout a jeden automatický nápravný pokus.

VM balíček je `/nix/store/ddql3r59v8hk42srylhagknl90777k0n-gnome-shell-50.5`,
derivace `/nix/store/wk47pg3f9qhmkjphl1zhq0dn0pf6qzpi-gnome-shell-50.5.drv`.
Kompilace s `--cores 0` skutečně použila `-j16`.

Headless regrese `artifacts/security-gap-headless-regression` prošla řízenou
chybou po panelu, jedním opakováním a sledováním 65,009 s. Má `passed=true`,
`workerExitCode=0`, odstraněný soukromý profil a nulovou sledovanou diagnostiku.
Použila `/nix/store/kp53hywlhg0pm7sin37dld44yrns960n-gnome-shell-50.5`.
`nix flake check --cores 0` také prošel.

## Reprodukce

```sh
nix build --cores 0 --print-build-logs .#security-gap-vm --out-link result-security-gap-vm
cat result-security-gap-vm/evidence/tgnome-evidence/result.json
nix build --cores 0 --print-build-logs .#security-construction-vm --out-link result-security-construction-vm
nix flake check --cores 0
```

Změny jsou v `shell/stableLoginManager.js`, `shell/stableSecurity.js`,
`shell/stableMain.js`, `shell/security-lifetime.patch`,
`shell/calendar-lifetime.patch`, `shell/tgnome-runtime.h`,
`tests/vm-security.py` a `flake.nix`.

## Zbývající hranice

Trvalý odběr pokrývá logind session `Lock`. Ostatní vstupy, například
ScreenSaver D-Bus API a požadavek před uspáním při nepřítomném UI, potřebují
vlastní ověření. Zbývá VM karanténa s čekajícím zámkem, další autentizační
metody, změny monitorů a obecná selhání konstruktorů. Stejný GJS kontext
zatím neumíme obnovit po synchronním zablokování a pád kompozitoru stále
ztrácí Wayland server. Fyzická hostitelská relace se netestovala.
