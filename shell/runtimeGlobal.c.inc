
/* Experimental only: preserve ShellGlobal and Mutter, replace its GJS member.
 * Finalization is measured through a weak notify, not inferred from a new
 * pointer address (allocators may reuse addresses).
 */
void _shell_global_reset_gjs_probe (ShellGlobal *self,
                                   GWeakNotify notify,
                                   gpointer data);

void
_shell_global_reset_gjs_probe (ShellGlobal *self,
                             GWeakNotify  notify,
                             gpointer     data)
{
  const char *search_path[] = { "resource:///org/gnome/shell", NULL };

  g_object_weak_ref (G_OBJECT (self->js_context), notify, data);
  g_clear_object (&self->js_context);
  self->js_context = g_object_new (GJS_TYPE_CONTEXT,
                                  "search-path", search_path,
                                  NULL);
}
