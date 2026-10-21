{ pkgs, probe, shell ? pkgs.gnome-shell, extension ? null, recoveryCli ? null,
  patched ? false, lockRace ? "none", fullContext ? false }:

# Explicit, expensive VM target. This is never imported into the host system.
# First establish real GDM/PAM/logind behavior before testing patched UI lifetime.
pkgs.testers.runNixOSTest {
  name = if fullContext then "tgnome-full-context" else if lockRace != "none" then "tgnome-security-${lockRace}"
    else if patched then "tgnome-security-reload" else "tgnome-security-baseline";
  globalTimeout = 600;

  nodes.machine = { ... }: {
    services.displayManager.gdm.enable = true;
    services.displayManager.autoLogin = {
      enable = true;
      user = "alice";
    };
    services.desktopManager.gnome.enable = true;
    users.users.alice = {
      isNormalUser = true;
      uid = 1000;
      password = "tgnome-vm-password";
    };
    # GNOME's upstream NixOS fixture uses the same VM-only Eval interface.
    systemd.user.services."org.gnome.Shell@".serviceConfig.ExecStart = [
      ""
      "${shell}/bin/gnome-shell --unsafe-mode"
    ];
    systemd.user.services."org.gnome.Shell@".environment = pkgs.lib.optionalAttrs patched {
      TGNOME_ALLOW_RUNTIME_RESET = "1";
      TGNOME_TEST_FAILURES = "1";
    } // pkgs.lib.optionalAttrs (patched && !fullContext) {
      TGNOME_PERSISTENT_CONTEXT = "1";
    } // pkgs.lib.optionalAttrs fullContext {
      TGNOME_REBIND_TYPES = "1";
    };
    environment.systemPackages = [ probe pkgs.glib pkgs.python3 ]
      ++ pkgs.lib.optional patched extension
      ++ pkgs.lib.optional (recoveryCli != null) recoveryCli;
    environment.etc."tgnome-vm-race".text = lockRace;
    # /etc entries are normally symlinks. The native VM gate deliberately
    # requires a root-owned regular file, materialized only inside this guest.
    system.activationScripts.tgnome-fixture = ''
      install -m 0444 ${pkgs.writeText "tgnome-vm-fixture" (
        if patched then "security-reload-v1\n" else "security-baseline\n"
      )} /etc/tgnome-vm-fixture
    '';
    services.gnome.gnome-initial-setup.enable = false;
    programs.dconf.profiles.user.databases = [{
      settings = {
        "org/gnome/shell".welcome-dialog-last-shown-version = "50.5";
        "org/gnome/desktop/session".idle-delay = pkgs.lib.gvariant.mkUint32 0;
      };
    }];
    virtualisation = {
      memorySize = 4096;
      cores = 4;
      diskSize = 8192;
      qemu.options = pkgs.lib.optional patched
        "-smbios type=1,manufacturer=Tgnome,product=TgnomeSecurityFixture";
    };
    system.stateVersion = "26.05";
  };

  testScript = builtins.readFile (if fullContext then ./vm-full-context.py else ./vm-security.py);
}
