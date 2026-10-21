# Licensing and upstream sources

Original contributions to this repository are licensed under GNU GPL version 2
or, at your option, any later version (GPL-2.0-or-later). See LICENSE.
Copyright 2026 Tomáš Mark and contributors.

This is a patch collection and test harness, not a full copy of GNOME Shell or
GJS. Nix fetches the original source archives declared by the locked nixpkgs.
Upstream copyright and license notices remain in those sources; this notice
does not replace or relicense them.

- GNOME Shell 50.5: [upstream source](https://gitlab.gnome.org/GNOME/gnome-shell/-/tree/50.5),
  [COPYING](https://github.com/GNOME/gnome-shell/blob/50.5/COPYING).
  Shell patch contexts and the adapted startup module derive from this project.
- GJS 1.88.1: [upstream source](https://gitlab.gnome.org/GNOME/gjs/-/tree/1.88.1),
  [COPYING](https://github.com/GNOME/gjs/blob/1.88.1/COPYING).
  GJS is dual-licensed MIT/LGPL-2.0-or-later, with individual file notices.
  Modified context/object/function sources include notices for litl, LLC and
  Philip Chimento. Preserve these notices in modified builds and distributions.

The `.patch` files include upstream context. Python transformation scripts and
`.inc` fragments modify or extend the corresponding upstream files; their
placement is described in RESEARCH-GUIDE.md and flake.nix. Changes in this
initial experimental patch collection were developed in October 2026.
Bundled dependencies retain their own licenses. No GNOME endorsement is implied.
