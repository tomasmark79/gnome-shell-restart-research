
/* Private introspected bridge; appended only by interruption-shell. The
 * watchdog reads GJS's native counter without reentering blocked JS. */
#include "interruptWatchdog.h"

gboolean
shell_global_tgnome_arm_watchdog (ShellGlobal *self)
{
  if (!self->backend || !meta_backend_is_headless (self->backend) ||
      g_strcmp0 (g_getenv ("TGNOME_ALLOW_INTERRUPTION"), "1") != 0)
    return FALSE;
  return tgnome_watchdog_arm ();
}

gboolean
shell_global_tgnome_backend_scope (ShellGlobal *self,
                                   gboolean entering)
{
  if (g_strcmp0 (g_getenv ("TGNOME_ALLOW_INTERRUPTION"), "1") != 0)
    return TRUE;
  if (!self->backend || !meta_backend_is_headless (self->backend))
    return FALSE;
  return gjs_context_tgnome_protect_scope (self->js_context, entering);
}

guint
shell_global_tgnome_backend_depth (ShellGlobal *self)
{
  return gjs_context_tgnome_protected_depth (self->js_context);
}
