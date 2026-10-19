"""Inject action navigation for tests of individual menu workflows.

Actual five-item root/submenu navigation is tested separately, using the public
menu and native Questionary key binding tests.
"""
from omop_exporter.menu import run_menu
from omop_exporter.menu_ui import render_plain


def dispatch_menu(workspace, read, write, **kwargs):
    def navigator(items):
        render_plain(items, write)
        return read("Action: ").strip()
    return run_menu(workspace, read=read, write=write, navigator=navigator, **kwargs)
