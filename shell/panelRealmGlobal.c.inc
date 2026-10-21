
/* Available only in realm-shell. No host session or non-headless activation. */
extern gboolean gjs_context_tgnome_install_ui_loader (GjsContext *context);

gboolean
shell_global_tgnome_prepare_ui_realms (ShellGlobal *self)
{
  if (!self->backend || !meta_backend_is_headless (self->backend) ||
      g_strcmp0 (g_getenv ("TGNOME_ALLOW_UI_REALMS"), "1") != 0)
    return FALSE;
  return gjs_context_tgnome_install_ui_loader (self->js_context);
}
