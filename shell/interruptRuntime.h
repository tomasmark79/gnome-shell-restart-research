/* Included only by the separate headless interruption Shell variant. */
#include "interruptWatchdog.h"

static char *tgnome_interrupt_reply;
static char *tgnome_interrupt_error;
static gboolean tgnome_interrupt_available;
static gboolean tgnome_interrupt_admitted;
static gboolean tgnome_interrupt_handoff_held;
static gboolean tgnome_interrupt_handoff_expired;
static guint tgnome_interrupt_handoff_timeout;
static guint tgnome_interrupt_handoff_releases;
static guint tgnome_interrupt_settle_source;
static guint tgnome_backend_emit_source;

static gboolean
tgnome_backend_emit (gpointer data)
{
  GCancellable *cancellable = g_cancellable_get_current ();
  (void) data;
  tgnome_backend_emit_source = 0;
  if (!cancellable)
    {
      g_warning ("TGNOME backend signal fixture has no native emitter");
      return G_SOURCE_REMOVE;
    }
  g_object_ref (cancellable);
  g_cancellable_pop_current (cancellable);
  g_cancellable_cancel (cancellable);
  g_object_unref (cancellable);
  return G_SOURCE_REMOVE;
}

static void
tgnome_interrupt_reloaded (GObject *source, GAsyncResult *result, gpointer data)
{
  GError *error = NULL;
  GVariant *reply = g_dbus_connection_call_finish (G_DBUS_CONNECTION (source), result, &error);
  (void) data;
  if (reply)
    {
      g_variant_get (reply, "(s)", &tgnome_interrupt_reply);
      g_variant_unref (reply);
    }
  else
    {
      tgnome_interrupt_error = g_strdup (error->message);
      g_warning ("TGNOME watchdog UI recovery request failed: %s", error->message);
      g_clear_error (&error);
    }
}

static gboolean
tgnome_interrupt_settle (gpointer data)
{
  GError *error = NULL;
  int result;
  (void) data;
  tgnome_interrupt_settle_source = 0;
  if (!gjs_context_eval (_shell_global_get_gjs_context (shell_global_get ()),
        "delete global._tgnomePanelTransferCheckpoint;"
        "global._tgnomeRecoverInterruptedPanelTransfer();",
        -1, "<tgnome-interrupt-operation-recovery>", &result, &error))
    {
      tgnome_interrupt_error = g_strdup (error->message);
      tgnome_ui_quarantined = TRUE;
      tgnome_ui_quarantines++;
      tgnome_probe_state = "interrupt-operation-recovery-failed";
      g_warning ("TGNOME interrupted operation recovery failed: %s", error->message);
      g_clear_error (&error);
      return G_SOURCE_REMOVE;
    }
  g_message ("TGNOME watchdog native loop resumed; requesting owned UI recovery");
  g_dbus_connection_call (tgnome_probe_bus,
    g_dbus_connection_get_unique_name (tgnome_probe_bus),
    "/org/gnome/Shell/Extensions/Tgnome", "org.gnome.Shell.Extensions.Tgnome",
    "ReloadDesktopUi", NULL, G_VARIANT_TYPE ("(s)"), G_DBUS_CALL_FLAGS_NONE,
    15000, NULL, tgnome_interrupt_reloaded, NULL);
  return G_SOURCE_REMOVE;
}

static gboolean
tgnome_interrupt_handoff_deadline (gpointer data)
{
  tgnome_interrupt_handoff_timeout = 0;
  tgnome_interrupt_handoff_held = FALSE;
  tgnome_interrupt_handoff_expired = TRUE;
  tgnome_interrupt_handoff_releases++;
  return tgnome_interrupt_settle (data);
}

static gboolean
tgnome_interrupt_resumed (gpointer data)
{
  if (g_strcmp0 (g_getenv ("TGNOME_TEST_HANDOFF"), "1") == 0)
    {
      tgnome_interrupt_handoff_held = TRUE;
      tgnome_interrupt_handoff_timeout = g_timeout_add (
        8000, tgnome_interrupt_handoff_deadline, NULL);
      g_message ("TGNOME interruption handoff held before operation settlement");
      return G_SOURCE_REMOVE;
    }
  return tgnome_interrupt_settle (data);
}

static gboolean
tgnome_interrupt_method (const char *method, GDBusMethodInvocation *invocation)
{
  GError *error = NULL;
  int flags = 0;
  GjsContext *context = _shell_global_get_gjs_context (shell_global_get ());
  if (!g_str_equal (method, "InterruptUiProbe") && !g_str_equal (method, "InterruptUiStatus") &&
      !g_str_equal (method, "InterruptHandoffStatus") && !g_str_equal (method, "ReleaseInterruptHandoff"))
    return FALSE;
  if (!tgnome_interrupt_available || tgnome_security_vm ||
      g_strcmp0 (g_getenv ("TGNOME_ALLOW_INTERRUPTION"), "1") != 0 ||
      g_strcmp0 (g_getenv ("TGNOME_PERSISTENT_CONTEXT"), "1") != 0)
    {
      g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
        G_IO_ERROR_NOT_SUPPORTED, "Interruption requires the separate headless experiment");
      return TRUE;
    }
  if (g_str_equal (method, "InterruptHandoffStatus"))
    {
      g_autofree char *status = g_strdup_printf (
        "{\"held\":%s,\"expired\":%s,\"releases\":%u}",
        tgnome_interrupt_handoff_held ? "true" : "false",
        tgnome_interrupt_handoff_expired ? "true" : "false",
        tgnome_interrupt_handoff_releases);
      g_dbus_method_invocation_return_value (invocation, g_variant_new ("(s)", status));
      return TRUE;
    }
  if (g_str_equal (method, "ReleaseInterruptHandoff"))
    {
      if (!tgnome_interrupt_handoff_held)
        goto refused;
      g_clear_handle_id (&tgnome_interrupt_handoff_timeout, g_source_remove);
      tgnome_interrupt_handoff_held = FALSE;
      tgnome_interrupt_handoff_releases++;
      tgnome_interrupt_settle_source = g_idle_add_full (
        G_PRIORITY_DEFAULT_IDLE, tgnome_interrupt_settle, NULL, NULL);
      g_dbus_method_invocation_return_value (invocation,
        g_variant_new ("(s)", "{\"released\":true}"));
      return TRUE;
    }
  if (g_str_equal (method, "InterruptUiProbe"))
    {
      const char *operation = g_getenv ("TGNOME_INTERRUPT_OPERATION");
      if (operation && !g_str_equal (operation, "callback") &&
          !g_str_equal (operation, "panel-detached") && !g_str_equal (operation, "panel-adopting") &&
          !g_str_equal (operation, "backend-finite") &&
          !g_str_equal (operation, "backend-delayed") &&
          !g_str_equal (operation, "backend-source") &&
          !g_str_equal (operation, "backend-signal") &&
          !g_str_equal (operation, "backend-cancellable") &&
          !g_str_equal (operation, "backend-async") &&
          !g_str_equal (operation, "backend-chain"))
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_INVALID_ARGUMENT, "Unsupported interruption operation");
          return TRUE;
        }
      if (tgnome_interrupt_admitted || tgnome_ui_active || tgnome_ui_quarantined || tgnome_probe_attempts != 0)
        goto refused;
      tgnome_interrupt_admitted = TRUE;
      if (!gjs_context_eval (context,
          "global._tgnomeInterruptFixture = {entered:false, caught:false, finalized:false};"
          "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 50, () => {"
          " const operation = imports.gi.GLib.getenv('TGNOME_INTERRUPT_OPERATION') ?? 'callback';"
          " const spin = () => {"
          "  if (!global.tgnome_arm_watchdog()) throw new Error('Watchdog arm refused');"
          "  global._tgnomeInterruptFixture.entered = true;"
          "  try { while (true) {} }"
          "  catch (_) { global._tgnomeInterruptFixture.caught = true; }"
          "  finally { global._tgnomeInterruptFixture.finalized = true; }"
          " };"
          " if (operation === 'callback') spin();"
          " else if (operation === 'backend-finite') {"
          "  const proof = global._tgnomeInterruptFixture.backendProof = {completed:false};"
          "  global._tgnomeWithBackendLifetime(() => global._tgnomeWithBackendLifetime(() => {"
          "   if (!global.tgnome_arm_watchdog()) throw new Error('Watchdog arm refused');"
          "   global._tgnomeInterruptFixture.entered = true;"
          "   proof.enteredNativeDepth = global.tgnome_backend_depth();"
          "   proof.enteredJsDepth = global._tgnomeBackendScopeDepth;"
          "   try { const until = Date.now() + 1700; while (Date.now() < until) {} }"
          "   finally { global._tgnomeInterruptFixture.finalized = true; }"
          "  }));"
          "  proof.lateSignalId = global.stage.connect('notify::reactive', () => {});"
          "  proof.completed = true;"
          " }"
          " else if (operation.startsWith('backend-')) {"
          "  const proof = global._tgnomeInterruptFixture.backendProof = {completed:false, returnObjectCollected:false};"
          "  global._tgnomeBackendReturnFinalizer = new FinalizationRegistry(() => { proof.returnObjectCollected = true; });"
          "  const callback = () => {"
          "   if (!global.tgnome_arm_watchdog()) throw new Error('Watchdog arm refused');"
          "   global._tgnomeInterruptFixture.entered = true;"
          "   proof.enteredNativeDepth = global.tgnome_backend_depth();"
          "   proof.enteredJsDepth = global._tgnomeBackendScopeDepth;"
          "   try { const until = Date.now() + 1700; while (Date.now() < until) {} }"
          "   finally { global._tgnomeInterruptFixture.finalized = true; }"
          "   if (operation === 'backend-chain') {"
          "    imports.gi.Gio.DBus.session.call(imports.gi.Gio.DBus.session.get_unique_name(),"
          "     '/org/gnome/Shell/TgnomeRuntime', 'org.freedesktop.DBus.Peer', 'Ping',"
          "     null, null, imports.gi.Gio.DBusCallFlags.NONE, 3000, null, (connection, result) => {"
          "      proof.followupCallFinished = connection.call_finish(result).n_children() === 0;"
          "      proof.followupNativeDepth = global.tgnome_backend_depth();"
          "      proof.followupJsDepth = global._tgnomeBackendScopeDepth;"
          "      proof.followupDone = true;"
          "     });"
          "   }"
          "   proof.callbackReturned = true;"
          "   const returned = {backendCallbackReturn:true};"
          "   global._tgnomeBackendReturnFinalizer.register(returned, 0);"
          "   return returned;"
          "  };"
          "  global._tgnomeWithBackendLifetime(() => {"
          "   if (operation === 'backend-delayed') imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, callback);"
          "   else if (operation === 'backend-async' || operation === 'backend-chain') {"
          "    imports.gi.Gio.DBus.session.call(imports.gi.Gio.DBus.session.get_unique_name(),"
          "     '/org/gnome/Shell/TgnomeRuntime', 'org.freedesktop.DBus.Peer', 'Ping',"
          "     null, null, imports.gi.Gio.DBusCallFlags.NONE, 3000, null, (connection, result) => {"
          "      proof.asyncCallFinished = connection.call_finish(result).n_children() === 0;"
          "      return callback();"
          "    });"
          "   }"
          "   else if (operation === 'backend-source') {"
          "    const source = imports.gi.GLib.timeout_source_new(1);"
          "    try { source.set_callback(null); throw new Error('Invalid callback was accepted'); }"
          "    catch (error) {"
          "     if (!String(error).includes('Expected function for callback argument func, got null')) throw error;"
          "     proof.invalidCallbackRejected = true;"
          "    }"
          "    source.set_callback(() => { callback(); return imports.gi.GLib.SOURCE_REMOVE; });"
          "    source.attach(null);"
          "   } else {"
          "    global._tgnomeBackendCancellable = new imports.gi.Gio.Cancellable();"
          "    global._tgnomeBackendCancellable.push_current();"
          "    proof.backendSignalId = operation === 'backend-cancellable'"
          "     ? global._tgnomeBackendCancellable.connect(callback)"
          "     : imports.gi.GObject.Object.prototype.connect.call(global._tgnomeBackendCancellable, 'cancelled', callback);"
          "   }"
          "  });"
          "  imports.gi.GLib.timeout_add(imports.gi.GLib.PRIORITY_DEFAULT, 10, () => {"
          "   if (!proof.callbackReturned) return imports.gi.GLib.SOURCE_CONTINUE;"
          "   if (operation === 'backend-chain' && !proof.followupDone) return imports.gi.GLib.SOURCE_CONTINUE;"
          "   if (proof.backendSignalId) {"
          "    if (operation === 'backend-cancellable') global._tgnomeBackendCancellable.disconnect(proof.backendSignalId);"
          "    else imports.gi.GObject.Object.prototype.disconnect.call(global._tgnomeBackendCancellable, proof.backendSignalId);"
          "    delete global._tgnomeBackendCancellable;"
          "   }"
          "   proof.lateSignalId = global.stage.connect('notify::reactive', () => {});"
          "   proof.completed = true; return imports.gi.GLib.SOURCE_REMOVE;"
          "  });"
          " }"
          " else {"
          "  global._tgnomePanelTransferCheckpoint = phase => {"
          "   if (operation === `panel-${phase}` && !global._tgnomeInterruptFixture.entered) spin();"
          "  };"
          "  global._tgnomeRunPanelTransfer();"
          " }"
          "});",
          -1, "<tgnome-interrupt-fixture>", &flags, &error))
        {
          g_dbus_method_invocation_return_gerror (invocation, error);
          g_clear_error (&error);
          return TRUE;
        }
      if (g_strcmp0 (operation, "backend-signal") == 0 ||
          g_strcmp0 (operation, "backend-cancellable") == 0)
        tgnome_backend_emit_source = g_timeout_add (100, tgnome_backend_emit, NULL);
      g_dbus_method_invocation_return_value (invocation,
        g_variant_new ("(s)", "{\"scheduled\":true}"));
    }
  else
    {
      g_autofree char *watchdog = tgnome_watchdog_status ();
      g_autofree char *status = NULL;
      if (!gjs_context_eval (context,
          "(() => { const f = global._tgnomeInterruptFixture; return f ? "
          "((f.entered ? 1 : 0) | (f.caught ? 2 : 0) | (f.finalized ? 4 : 0)) : 0; })();",
          -1, "<tgnome-interrupt-status>", &flags, &error))
        {
          g_dbus_method_invocation_return_gerror (invocation, error);
          g_clear_error (&error);
          return TRUE;
        }
      /* The reply is a JSON object produced by our own extension; errors are
       * deliberately represented by a boolean, never interpolated unescaped. */
      status = g_strdup_printf ("{\"watchdog\":%s,\"fixtureFlags\":%d,"
        "\"recoveryFailed\":%s,\"recoveryReply\":%s}", watchdog, flags,
        tgnome_interrupt_error ? "true" : "false",
        tgnome_interrupt_reply ? tgnome_interrupt_reply : "null");
      g_dbus_method_invocation_return_value (invocation, g_variant_new ("(s)", status));
    }
  return TRUE;
refused:
  g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
    G_IO_ERROR_BUSY, "Interruption fixture is busy or its one-shot limit is reached");
  return TRUE;
}
