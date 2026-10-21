"""Apply changes restricted to the complete-context Shell build."""
from pathlib import Path


def replace(path, old, new):
    source = Path(path).read_text()
    assert source.count(old) == 1, (path, old, source.count(old))
    Path(path).chmod(Path(path).stat().st_mode | 0o200)
    Path(path).write_text(source.replace(old, new))


replace('js/ui/init.js', '            let removed = 0;',
        '            tgnomeReleaseNativeWork();\n            let removed = 0;')
replace('src/tgnome-runtime.h', 'static gboolean tgnome_probe_allowed;',
        '''extern char *gjs_tgnome_callback_lifetimes (void);
extern unsigned gjs_tgnome_rebind_bridge_count (void);
static gboolean tgnome_probe_allowed;''')
replace('src/tgnome-runtime.h',
        '  g_autofree char *new_types = tgnome_new_object_types ();',
        '''  g_autofree char *callbacks = gjs_tgnome_callback_lifetimes ();
  g_autofree char *new_types = tgnome_new_object_types ();''')
replace('src/tgnome-runtime.h',
        '"{\\\"pid\\\":%d,\\\"publishedUiGeneration\\\":%d,\\\"attempts\\\":%u,\\\"contextsFinalized\\\":%u,"',
        '"{\\\"callbacks\\\":%s,\\\"vfuncBridges\\\":%u,\\\"pid\\\":%d,\\\"publishedUiGeneration\\\":%d,\\\"attempts\\\":%u,\\\"contextsFinalized\\\":%u,"')
replace('src/tgnome-runtime.h', '                          (int) getpid (), published_generation,',
        '                          callbacks, gjs_tgnome_rebind_bridge_count (), (int) getpid (), published_generation,')
replace('src/tgnome-runtime.h', '(in_place ? 3u : 1u)', '3u')
replace('src/tgnome-runtime.h', 'tgnome_runtime_reset_idle (gpointer data)\n{',
        '''tgnome_runtime_reset_idle (gpointer data)
{
  // A nested main-loop iteration may still be on a GJS evaluation stack.
  // Destruction must happen only from Mutter's outer native dispatch loop.
  if (g_main_depth () > 1)
    {
      g_timeout_add_full (G_PRIORITY_LOW, 10, tgnome_runtime_reset_idle, NULL, NULL);
      return G_SOURCE_REMOVE;
    }''')
# Unlike stable UI recovery, whole-context Status must never enter JS or spin
# its nested main loop. The complete-context build has no UI security curtain.
source = Path('src/tgnome-runtime.h').read_text()
begin = source.index('  if (tgnome_security_vm)', source.index('tgnome_runtime_status (void)'))
end = source.index('  return g_strdup_printf', begin)
assert '_tgnomeGetSecurityBoundary' in source[begin:end]
Path('src/tgnome-runtime.h').write_text(source[:begin] + source[end:])
replace('js/ui/focusCaretTracker.js',
        '        this._atspiListener = Atspi.EventListener.new(this._onChanged.bind(this));',
        '''        (global._tgnomeFocusTrackers ??= new Set()).add(this);
        this._atspiListener = global.tgnome_get_focus_listener();
        this._tgnomeListenerSignal = this._atspiListener.connect(
            'tgnome-focus-event', (_listener, event) => this._onChanged(event));''')
replace('src/shell-global.h', 'G_END_DECLS',
        'GObject *shell_global_tgnome_get_focus_listener (ShellGlobal *global);\n\nG_END_DECLS')
replace('src/meson.build', 'gnome_shell_deps = [',
        "gnome_shell_deps = [\n  dependency('atspi-2'),")
replace('js/misc/ibusManager.js',
        '''            GLib.child_watch_add(
                GLib.PRIORITY_DEFAULT,
                pid,
                () => GLib.spawn_close_pid(pid)
            );''',
        '''            imports._gi.tgnome_watch_child(GLib.PRIORITY_DEFAULT, pid);''')
