{
  description = "Historical GNOME 50 Shell/GJS restart experiments and isolated regression harnesses";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/8ce73368d1efd4d657e9064d29b144a52046b4e8";
  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
    uuid = "restart-island@tgnome.local";
    testPython = pkgs.python3.withPackages (ps: [ ps.python-dbusmock ps.pygobject3 ]);
    panelShell = pkgs.gnome-shell.overrideAttrs (old: {
      postPatch = (old.postPatch or "") + ''
        # Apply local lifecycle patches with exact context. Keep Nixpkgs'
        # upstream packaging patches under their existing patch policy.
        patch -p1 --fuzz=0 < ${./shell/panel-lifecycle.patch}
        cat ${./shell/panelLifecycle.js} >> js/ui/panel.js
        cat ${./shell/mainLifecycle.js} >> js/ui/main.js
      '';
    });
    runtimeShell = panelShell.overrideAttrs (old: {
      postPatch = (old.postPatch or "") + ''
        patch -p1 --fuzz=0 < ${./shell/native-loop.patch}
        cp ${./shell/runtimeInit.js} js/ui/init.js
        cp ${./shell/tgnome-runtime.h} src/tgnome-runtime.h
        cat ${./shell/runtimeGlobal.c.inc} >> src/shell-global.c
        substituteInPlace js/misc/signalTracker.js js/ui/environment.js \
          js/ui/extensionSystem.js js/ui/layout.js js/ui/main.js \
          --replace-fail "'shutdown'" "'tgnome-ui-reset'"
      '';
    });
    stableShell = runtimeShell.overrideAttrs (old: {
      postPatch = (old.postPatch or "") + ''
        patch -p1 --fuzz=0 < ${./shell/stable-lifetime.patch}
        patch -p1 --fuzz=0 < ${./shell/partial-startup.patch}
        patch -p1 --fuzz=0 < ${./shell/preparation-lifetime.patch}
        patch -p1 --fuzz=0 < ${./shell/construction-lifetime.patch}
        patch -p1 --fuzz=0 < ${./shell/security-lifetime.patch}
        patch -p1 --fuzz=0 < ${./shell/calendar-lifetime.patch}
        cat ${./shell/stableRegistry.js} ${./shell/runtimeInit.js} > js/ui/init.js
        cat ${./shell/stableEnvironment.js} >> js/ui/environment.js
        cat ${./shell/stableSignalTracker.js} >> js/misc/signalTracker.js
        cat ${./shell/stableMain.js} >> js/ui/main.js
        cat ${./shell/stableSecurity.js} >> js/ui/main.js
        cat ${./shell/stableIBus.js} >> js/misc/ibusManager.js
        cat ${./shell/stableInputMethod.js} >> js/misc/inputMethod.js
        cat ${./shell/stableTimeLimits.js} >> js/misc/timeLimitsManager.js
        cat ${./shell/stableLayout.js} >> js/ui/layout.js
        cat ${./shell/stableSystemActions.js} >> js/misc/systemActions.js
        cat ${./shell/stableScreenShield.js} >> js/ui/screenShield.js
        cat ${./shell/stableUnlockDialog.js} >> js/ui/unlockDialog.js
        cat ${./shell/stableLoginManager.js} >> js/misc/loginManager.js
        substituteInPlace js/ui/ibusCandidatePopup.js \
          --replace-fail "panelService.connect(" "connect("
        python3 - <<'PY'
        from pathlib import Path
        main = Path('js/ui/main.js').read_text()
        for boundary in [
            'layoutManager = new Layout.LayoutManager();\n    layoutManager._tgnomeUiOwned = true;',
            "uiGroup = layoutManager.uiGroup;\n    tgnomeUiCheckpoint('after-layout');",
            "panel = new Panel.Panel();\n    tgnomeUiCheckpoint('after-panel');\n    keyboard = new Keyboard.KeyboardManager();",
        ]:
            assert boundary in main, f'Incorrect UI construction boundary: {boundary}'
        PY
      '';
    });
    securityVmShell = stableShell.overrideAttrs (old: {
      NIX_CFLAGS_COMPILE = (old.NIX_CFLAGS_COMPILE or "") + " -DTGNOME_SECURITY_VM=1";
    });
    probe = pkgs.stdenv.mkDerivation {
      pname = "tgnome-client-probe";
      version = "0.1";
      src = pkgs.lib.cleanSourceWith {
        src = ./tests;
        filter = path: type: type == "directory" || baseNameOf path == "probe.c";
      };
      nativeBuildInputs = [ pkgs.pkg-config ];
      buildInputs = [ pkgs.gtk3 pkgs.wayland pkgs.libx11 ];
      buildPhase = "cc -Wall -Wextra -Werror probe.c -o tgnome-client-probe $(pkg-config --cflags --libs gtk+-3.0 wayland-client x11)";
      installPhase = "mkdir -p $out/bin; cp tgnome-client-probe $out/bin/";
    };
    interruptGjs = pkgs.gjs.overrideAttrs (old: {
      pname = "tgnome-gjs";
      postPatch = (old.postPatch or "") + ''
        patch -p1 --fuzz=0 < ${./shell/gjs-interruption.patch}
      '';
    });
    realmGjs = interruptGjs.overrideAttrs (old: {
      pname = "tgnome-realm-gjs";
      postPatch = (old.postPatch or "") + ''
        cat ${./shell/gjsRealm.cpp.inc} >> gjs/context.cpp
      '';
    });
    nativeTypeGjs = interruptGjs.overrideAttrs (old: {
      pname = "tgnome-native-type-gjs";
      postPatch = (old.postPatch or "") + ''
        cat ${./shell/gjsNativeType.cpp.inc} >> gjs/context.cpp
      '';
    });
    rebindGjs = nativeTypeGjs.overrideAttrs (old: {
      pname = "tgnome-type-rebind-gjs";
      nativeBuildInputs = (old.nativeBuildInputs or []) ++ [ pkgs.python3 ];
      postPatch = (old.postPatch or "") + ''
        cp ${./shell/gjsTypeRebindPrivate.inc} gi/tgnomeTypeRebindPrivate.inc
        cp ${./shell/gjsTypeRebindVfunc.inc} gi/tgnomeTypeRebindVfunc.inc
        cp ${./shell/gjsCallbackLifetimes.inc} gi/tgnomeCallbackLifetimes.inc
        python3 ${./shell/buildTypeRebind.py}
      '';
    });
    typeRebindProbe = pkgs.stdenv.mkDerivation {
      pname = "tgnome-type-rebind-probe";
      version = "0.1";
      src = ./tests/type-rebind-probe.cpp;
      dontUnpack = true;
      nativeBuildInputs = [ pkgs.pkg-config ];
      buildInputs = [ rebindGjs pkgs.spidermonkey_140 ];
      buildPhase = ''
        $CXX -g -std=c++17 -Wall -Wextra -Werror -I${./tests} "$src" \
          -o tgnome-type-rebind-probe $(pkg-config --cflags --libs gjs-1.0 mozjs-140)
      '';
      installPhase = ''
        mkdir -p $out/bin
        cp tgnome-type-rebind-probe $out/bin/
      '';
    };
    nativeTypeProbe = pkgs.stdenv.mkDerivation {
      pname = "tgnome-native-type-probe";
      version = "0.1";
      src = ./tests/native-type-probe.cpp;
      dontUnpack = true;
      nativeBuildInputs = [ pkgs.pkg-config pkgs.python3 pkgs.gdb pkgs.valgrind ];
      buildInputs = [ nativeTypeGjs pkgs.spidermonkey_140 ];
      buildPhase = ''
        $CXX -g -std=c++17 -Wall -Wextra -Werror "$src" -o tgnome-native-type-probe \
          $(pkg-config --cflags --libs gjs-1.0 mozjs-140)
      '';
      doCheck = true;
      checkPhase = ''
        python3 ${./tests/native-type-supervisor.py} ./tgnome-native-type-probe native-type-report.json
      '';
      installPhase = ''
        mkdir -p $out/bin $out/share/tgnome
        cp tgnome-native-type-probe $out/bin/
        cp native-type-report.json $out/share/tgnome/
      '';
    };
    realmProbe = pkgs.stdenv.mkDerivation {
      pname = "tgnome-realm-probe";
      version = "0.1";
      src = ./tests/realm-probe.cpp;
      dontUnpack = true;
      nativeBuildInputs = [ pkgs.pkg-config pkgs.python3 ];
      buildInputs = [ realmGjs pkgs.spidermonkey_140 ];
      buildPhase = ''
        $CXX -std=c++17 -Wall -Wextra -Werror "$src" -o tgnome-realm-probe \
          $(pkg-config --cflags --libs gjs-1.0 mozjs-140)
      '';
      doCheck = true;
      checkPhase = ''
        python3 ${./tests/realm-supervisor.py} ./tgnome-realm-probe \
          ${./tests/realm-modules} realm-report.json
      '';
      installPhase = ''
        mkdir -p $out/bin $out/share/tgnome
        cp tgnome-realm-probe $out/bin/
        cp realm-report.json $out/share/tgnome/
      '';
    };
    interruptionShellFor = gjsPackage: (stableShell.override { gjs = gjsPackage; }).overrideAttrs (old: {
      buildInputs = (old.buildInputs or []) ++ [ pkgs.spidermonkey_140 ];
      postPatch = (old.postPatch or "") + ''
        patch -p1 --fuzz=0 < ${./shell/interrupt-shell.patch}
        cp ${./shell/interruptWatchdog.h} src/interruptWatchdog.h
        cp ${./shell/interruptWatchdog.cpp} src/interruptWatchdog.cpp
        cp ${./shell/interruptRuntime.h} src/interruptRuntime.h
        cat ${./shell/interruptGlobal.c.inc} >> src/shell-global.c
        substituteInPlace src/shell-global.h --replace-fail 'G_END_DECLS' \
          'gboolean shell_global_tgnome_backend_scope (ShellGlobal *self, gboolean entering);
        guint shell_global_tgnome_backend_depth (ShellGlobal *self);
        gboolean shell_global_tgnome_arm_watchdog (ShellGlobal *self);
        G_END_DECLS'
      '';
    });
    interruptionShell = interruptionShellFor interruptGjs;
    realmShell = (interruptionShellFor realmGjs).overrideAttrs (old: {
      postPatch = (old.postPatch or "") + ''
        python3 ${./shell/buildPanelRealm.py}
        python3 ${./shell/buildDateMenuRealm.py}
        cat ${./shell/panelRealmGlobal.c.inc} >> src/shell-global.c
        substituteInPlace src/shell-global.h --replace-fail 'G_END_DECLS' \
          'gboolean shell_global_tgnome_prepare_ui_realms (ShellGlobal *self);
        G_END_DECLS'
        cat >> js/ui/main.js <<'JS'
        import * as TgnomeDateMenu from './dateMenu.js';
        export function getPanelRealmStatus() {
            return Panel.getPanelRealmStatus();
        }
        export function getDateMenuRealmStatus() {
            return TgnomeDateMenu.getDateMenuRealmStatus();
        }
        JS
      '';
    });
    typeRebindShell = (runtimeShell.override { gjs = rebindGjs; }).overrideAttrs (old: {
      postPatch = (old.postPatch or "") + ''
        cat ${./shell/fullContextInit.js} ${./shell/runtimeInit.js} > js/ui/init.js
        cat ${./shell/fullContextAtspi.c.inc} >> src/shell-global.c
        python3 ${./shell/buildFullContext.py}
      '';
    });
    interruptProbeFor = gjsPackage: recoverable: pkgs.stdenv.mkDerivation {
      pname = if recoverable then "tgnome-interrupt-probe" else "tgnome-interrupt-baseline";
      version = "0.1";
      src = ./tests/interrupt-probe.cpp;
      dontUnpack = true;
      nativeBuildInputs = [ pkgs.pkg-config pkgs.python3 ];
      buildInputs = [ gjsPackage pkgs.spidermonkey_140 ];
      NIX_CFLAGS_COMPILE = pkgs.lib.optionalString recoverable "-DTGNOME_RECOVERABLE_GJS=1";
      buildPhase = ''
        $CXX -std=c++17 -Wall -Wextra -Werror -pthread "$src" -o tgnome-interrupt-probe \
          $(pkg-config --cflags --libs gjs-1.0 mozjs-140)
      '';
      doCheck = true;
      checkPhase = ''
        python3 ${./tests/interrupt-supervisor.py} ./tgnome-interrupt-probe interrupt-report.json ${if recoverable then "patched" else "baseline"}
      '';
      installPhase = ''
        mkdir -p $out/bin $out/share/tgnome
        cp tgnome-interrupt-probe $out/bin/
        cp interrupt-report.json $out/share/tgnome/
      '';
    };
    interruptProbe = interruptProbeFor interruptGjs true;
    extension = pkgs.runCommand "tgnome-ui-island-0.1" {} ''
      mkdir -p $out/share/gnome-shell/extensions/${uuid}
      cp ${./extension}/* $out/share/gnome-shell/extensions/${uuid}/
    '';
    cli = pkgs.writeShellApplication {
      name = "tgnome";
      runtimeInputs = [ pkgs.python3 pkgs.glib ];
      text = ''exec python3 ${./tgnome.py} "$@"'';
    };
  in {
    packages.${system} = {
      inherit extension probe;
      interrupt-probe = interruptProbe;
      interrupt-baseline = interruptProbeFor pkgs.gjs false;
      interrupt-gjs = interruptGjs;
      realm-gjs = realmGjs;
      realm-probe = realmProbe;
      native-type-gjs = nativeTypeGjs;
      native-type-probe = nativeTypeProbe;
      type-rebind-gjs = rebindGjs;
      type-rebind-probe = typeRebindProbe;
      type-rebind-shell = typeRebindShell;
      full-context-vm = import ./tests/vm-security.nix {
        inherit pkgs probe extension;
        recoveryCli = cli;
        shell = typeRebindShell.overrideAttrs (old: {
          NIX_CFLAGS_COMPILE = (old.NIX_CFLAGS_COMPILE or "") + " -DTGNOME_SECURITY_VM=1";
        });
        patched = true;
        fullContext = true;
      };
      realm-shell = realmShell;
      interruption-shell = interruptionShell;
      shell = pkgs.gnome-shell;
      panel-shell = panelShell;
      runtime-shell = runtimeShell;
      stable-shell = stableShell;
      security-vm = import ./tests/vm-security.nix { inherit pkgs probe; };
      security-reload-vm = import ./tests/vm-security.nix {
        inherit pkgs probe extension;
        shell = securityVmShell;
        patched = true;
      };
      security-preparation-vm = import ./tests/vm-security.nix {
        inherit pkgs probe extension;
        shell = securityVmShell;
        patched = true;
        lockRace = "preparation";
      };
      security-construction-vm = import ./tests/vm-security.nix {
        inherit pkgs probe extension;
        shell = securityVmShell;
        patched = true;
        lockRace = "construction";
      };
      security-gap-vm = import ./tests/vm-security.nix {
        inherit pkgs probe extension;
        shell = securityVmShell;
        patched = true;
        lockRace = "security-gap";
      };
      security-quarantine-vm = import ./tests/vm-security.nix {
        inherit pkgs probe extension;
        recoveryCli = cli;
        shell = securityVmShell;
        patched = true;
        lockRace = "quarantine";
      };
      mutter = pkgs.mutter;
      upstream-sources = pkgs.runCommand "tgnome-upstream-sources" {} ''
        mkdir -p $out
        ln -s ${pkgs.gnome-shell.src} $out/gnome-shell-50.5.tar.xz
        ln -s ${pkgs.mutter.src} $out/mutter-50.5.tar.xz
      '';
      default = cli;
    };
    devShells.${system} = {
    type-rebind = pkgs.mkShell {
      packages = [ pkgs.python3 pkgs.gdb pkgs.valgrind typeRebindProbe ];
    };
    rebind = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus pkgs.gdb typeRebindShell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${typeRebindShell}/bin/gnome-shell";
      TGNOME_ALLOW_PANEL_RELOAD = "1";
      TGNOME_ALLOW_RUNTIME_RESET = "1";
      TGNOME_REBIND_TYPES = "1";
    };
    native-type = pkgs.mkShell {
      packages = [ pkgs.python3 pkgs.gdb pkgs.valgrind nativeTypeProbe ];
    };
    realm = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus realmShell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${realmShell}/bin/gnome-shell";
      TGNOME_ALLOW_PANEL_RELOAD = "1";
      TGNOME_ALLOW_RUNTIME_RESET = "1";
      TGNOME_PERSISTENT_CONTEXT = "1";
      TGNOME_ALLOW_UI_REALMS = "1";
    };
    default = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus pkgs.gnome-shell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${pkgs.gnome-shell}/bin/gnome-shell";
    };
    panel = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus panelShell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${panelShell}/bin/gnome-shell";
      TGNOME_ALLOW_PANEL_RELOAD = "1";
    };
    runtime = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus runtimeShell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${runtimeShell}/bin/gnome-shell";
      TGNOME_ALLOW_PANEL_RELOAD = "1";
      TGNOME_ALLOW_RUNTIME_RESET = "1";
    };
    interruption = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus interruptionShell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${interruptionShell}/bin/gnome-shell";
      TGNOME_ALLOW_PANEL_RELOAD = "1";
      TGNOME_ALLOW_RUNTIME_RESET = "1";
      TGNOME_PERSISTENT_CONTEXT = "1";
      TGNOME_ALLOW_INTERRUPTION = "1";
    };
    stable = pkgs.mkShell {
      packages = [ testPython pkgs.glib pkgs.dbus stableShell
        pkgs.gsettings-desktop-schemas pkgs.mesa pkgs.xwayland probe ];
      TGNOME_EXTENSION = "${extension}/share/gnome-shell/extensions/${uuid}";
      TGNOME_PROBE = "${probe}/bin/tgnome-client-probe";
      TGNOME_SHELL = "${stableShell}/bin/gnome-shell";
      TGNOME_ALLOW_PANEL_RELOAD = "1";
      TGNOME_ALLOW_RUNTIME_RESET = "1";
      TGNOME_PERSISTENT_CONTEXT = "1";
    };
    };
    checks.${system} = {
      package = cli;
      interruption = interruptProbe;
      realm = realmProbe;
      interruption-baseline = interruptProbeFor pkgs.gjs false;
      supervisor = pkgs.runCommand "tgnome-private-supervisor-test" {
        nativeBuildInputs = [ pkgs.python3 ];
      } ''
        mkdir tests
        cp ${./tgnome.py} tgnome.py
        cp ${./tests/isolated.py} tests/isolated.py
        cp ${./tests/test_supervisor.py} tests/test_supervisor.py
        python3 -m unittest discover -s tests -p test_supervisor.py -v
        touch $out
      '';
      gc-observer = pkgs.runCommand "tgnome-gc-observer-controls" {
        nativeBuildInputs = [ pkgs.gjs ];
      } ''
        gjs -m ${./tests/gc-control.js}
        touch $out
      '';
      safety = pkgs.runCommand "tgnome-safety-tests" {
        nativeBuildInputs = [ pkgs.python3 ];
      } ''
        cp ${./tgnome.py} tgnome.py
        cp ${./tests/test_safety.py} test_safety.py
        python3 -m unittest -v test_safety
        touch $out
      '';
    };
  };
}
