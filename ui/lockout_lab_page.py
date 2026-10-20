"""Guided, offline Lockout Lab mapping and scenario page."""

from __future__ import annotations

import copy
import customtkinter as ctk

from lockout_lab import LabError, LabStore, SCENARIOS, add_node, add_route, simulate
from ui import theme as T
from ui.modal import confirm
from ui.widgets import Btn, Dropdown, Field, card, check, style_scrollbar


class LockoutLabPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self._scroll_job = None
        self.store = LabStore(shell.session)
        try:
            self.model = self.store.load()
            self.load_error = None
        except (LabError, OSError, RuntimeError):
            self.model = None
            self.load_error = "Encrypted Lockout Lab data could not be opened. The file and its backup were kept; no new data will be written."
        ctk.CTkLabel(self, text="Lockout Lab", font=T.font(16, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x", padx=26, pady=(12, 0))
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        style_scrollbar(self.body)
        self.body.pack(fill="both", expand=True, padx=26, pady=(10, 12))
        self.body.bind("<Configure>", self._resize_notice, add="+")
        self._build()

    def _resize_notice(self, event=None):
        notice = getattr(self, "_notice", None)
        if notice is not None and notice.winfo_exists():
            width = (event.width if event is not None else self.body.winfo_width()) / T.widget_scale(self.body)
            notice.configure(wraplength=max(280, int(width) - 26))

    def _label(self, parent, text, size=13, color=None, bold=False, **pack):
        label = ctk.CTkLabel(parent, text=text, font=T.font(size, "bold" if bold else "normal"),
                             text_color=color or T.TEXT, anchor="w", justify="left", wraplength=800)
        label.pack(anchor="w", **pack)
        return label

    def _section(self, title, hint):
        frame = card(self.body)
        frame.pack(fill="x", pady=(0, 16))
        self._label(frame, title, 17, bold=True, padx=20, pady=(17, 0))
        self._label(frame, hint, 12, T.TEXT_MUTED, padx=20, pady=(2, 14))
        return frame

    def _build(self):
        for child in self.body.winfo_children():
            child.destroy()
        self._notice = self._label(
            self.body,
            "Names and routes only. Never enter passwords or recovery-code values. Results are modeled estimates, not a live recovery check.",
            12, T.WARNING, pady=(0, 16))
        self._resize_notice()
        if self.load_error:
            box = self._section("Encrypted data needs attention", self.load_error)
            self._label(box, "Keep the encrypted primary and .bak files. Do not create a new map over them.",
                        12, T.TEXT_MUTED, padx=20, pady=(0, 18))
            Btn(box, "Restore verified backup", "secondary", width=200, command=self._recover).pack(anchor="w", padx=20, pady=(0, 18))
            return
        self._mapping()
        self._routes()
        self._scenarios()

    def _mapping(self):
        box = self._section("1  Map what matters", "Add accounts, devices, and recovery methods. Mark a method verified only after you test it yourself.")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 12))
        self.name = Field(row, "Name, e.g. Primary email", width=240)
        self.name.pack(side="left", padx=(0, 8))
        self.kind = Dropdown(row, [("account", "Account"), ("device", "Device"), ("method", "Recovery method")], width=150)
        self.kind.pack(side="left", padx=(0, 8))
        self.role = Dropdown(row, [("none", "No scenario role"), ("phone", "Phone"),
                                   ("primary_email", "Primary email"), ("computer", "Computer")], width=155)
        self.role.pack(side="left", padx=(0, 8))
        Btn(row, "Add", "primary", width=72, command=self._add).pack(side="left")
        if not self.model["nodes"]:
            self._label(box, "Start with your primary email, phone, computer, backup codes, and a critical account.",
                        12, T.TEXT_MUTED, padx=20, pady=(0, 18))
            return
        for node in self.model["nodes"]:
            line = ctk.CTkFrame(box, fg_color=T.SURFACE_2, corner_radius=2)
            line.pack(fill="x", padx=20, pady=(0, 6))
            self._label(line, f"{node['name']}  ·  {node['kind']}  ·  {node['evidence'].replace('_', ' ')}",
                        13, padx=12, pady=8, side="left", fill="x", expand=True)
            actions = ctk.CTkFrame(line, fg_color="transparent")
            actions.pack(side="right", padx=8)
            Btn(actions, "Documented", "ghost", width=95, height=28,
                command=lambda ident=node["id"]: self._evidence(ident, "documented")).pack(side="left")
            Btn(actions, "User-verified", "ghost", width=105, height=28,
                command=lambda ident=node["id"]: self._evidence(ident, "verified")).pack(side="left")
            Btn(actions, "Remove", "danger_ghost", width=72, height=28,
                command=lambda ident=node["id"]: self._remove(ident)).pack(side="left")
        self._label(box, "Removing an item keeps references to it as unknown dependencies until you update those routes.",
                    11, T.TEXT_MUTED, padx=20, pady=(4, 14))

    def _routes(self):
        box = self._section("2  Describe recovery routes", "Each route needs every checked item (AND). Add another route for an alternative (OR).")
        if not self.model["nodes"]:
            return
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 10))
        self._label(row, "Recover", 12, T.TEXT_MUTED)
        self.target = Dropdown(row, [(n["id"], n["name"]) for n in self.model["nodes"]], width=240)
        self.target.pack(side="left", padx=(8, 0))
        checks = ctk.CTkFrame(box, fg_color="transparent")
        checks.pack(fill="x", padx=20)
        self.route_vars = {}
        for index, node in enumerate(self.model["nodes"]):
            var = ctk.BooleanVar(value=False)
            self.route_vars[node["id"]] = var
            check(checks, node["name"], var).grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 18), pady=4)
        Btn(box, "Add route", "secondary", width=110, command=self._add_route).pack(anchor="w", padx=20, pady=(12, 12))
        names = {n["id"]: n["name"] for n in self.model["nodes"]}
        for node in self.model["nodes"]:
            for index, route in enumerate(node["routes"]):
                line = ctk.CTkFrame(box, fg_color=T.SURFACE_2, corner_radius=2)
                line.pack(fill="x", padx=20, pady=(0, 5))
                self._label(line, f"{node['name']} needs " + " + ".join(names.get(ref, "Missing item") for ref in route),
                            12, padx=12, pady=7, side="left", fill="x", expand=True)
                Btn(line, "Remove route", "danger_ghost", width=100, height=28,
                    command=lambda ident=node["id"], i=index: self._remove_route(ident, i)).pack(side="right", padx=8)
        ctk.CTkFrame(box, fg_color="transparent", height=7).pack()

    def _scenarios(self):
        box = self._section("3  Explore a loss", "A route marked available means only that your map contains a path. Confirm real recovery with each provider.")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 12))
        self.scenario = Dropdown(row, [(key, label) for key, (label, _) in SCENARIOS.items()], width=260)
        self.scenario.pack(side="left", padx=(0, 10))
        Btn(row, "Simulate", "primary", width=110, command=self._simulate).pack(side="left")
        self.results = ctk.CTkFrame(box, fg_color="transparent")
        self.results.pack(fill="x", padx=20, pady=(0, 18))

    def _commit(self, change):
        candidate = copy.deepcopy(self.model)
        try:
            change(candidate)
            self.store.save(candidate)
        except (LabError, OSError, RuntimeError) as exc:
            self.shell.notify("Lockout Lab was not saved", str(exc) if isinstance(exc, LabError) else
                              "Encrypted data was kept. Check the data folder and disk space.", "error")
            return
        self.model = candidate
        scroll = self.body._parent_canvas.yview()[0]
        self._build()
        if self._scroll_job is not None:
            self.after_cancel(self._scroll_job)
        self._scroll_job = self.after_idle(lambda: self._restore_scroll(scroll))

    def _restore_scroll(self, fraction):
        self._scroll_job = None
        self.body._parent_canvas.yview_moveto(fraction)

    def destroy(self):
        if self._scroll_job is not None:
            self.after_cancel(self._scroll_job)
            self._scroll_job = None
        super().destroy()

    def _add(self):
        name = self.name.get().strip()
        self._commit(lambda model: add_node(model, name, self.kind.get(), self.role.get()))

    def _evidence(self, ident, evidence):
        def change(model):
            next(n for n in model["nodes"] if n["id"] == ident)["evidence"] = evidence
        self._commit(change)

    def _remove(self, ident):
        self._commit(lambda model: model.update(nodes=[n for n in model["nodes"] if n["id"] != ident]))

    def _add_route(self):
        target = self.target.get()
        selected = [ident for ident, var in self.route_vars.items() if var.get()]
        self._commit(lambda model: add_route(model, target, selected))

    def _remove_route(self, ident, index):
        self._commit(lambda model: next(n for n in model["nodes"] if n["id"] == ident)["routes"].pop(index))

    def _simulate(self):
        for child in self.results.winfo_children():
            child.destroy()
        outcomes = simulate(self.model, self.scenario.get())
        if not outcomes:
            self._label(self.results, "Add an account to see outcomes.", 12, T.TEXT_MUTED)
            return
        for result in outcomes:
            status = {"available": "Modeled route found", "blocked": "Potentially blocked", "unknown": "Unknown"}[result["status"]]
            line = card(self.results, fg_color=T.SURFACE_2)
            line.pack(fill="x", pady=(0, 8))
            self._label(line, f"{result['name']}  ·  {status}", 14, bold=True, padx=12, pady=(10, 1))
            self._label(line, result["reason"], 12, T.TEXT_MUTED, padx=12)
            if result["circular"]:
                self._label(line, "Circular recovery relationship detected.", 12, T.WARNING, padx=12)
            for step in result["steps"]:
                self._label(line, "• " + step, 12, T.TEXT_MUTED, padx=12)
            ctk.CTkFrame(line, height=6, fg_color="transparent").pack()

    def _recover(self):
        if not confirm(self.winfo_toplevel(), "Restore Lockout Lab backup",
                       "Restore the last authenticated Lockout Lab backup? The damaged encrypted file will be preserved. Recent map changes may be lost.",
                       confirm_text="Restore", danger=True):
            return
        try:
            model = self.store.recover_from_backup(confirmed=True)
        except (LabError, OSError, RuntimeError):
            self.shell.notify("Recovery unavailable", "The encrypted files were kept. Check the backup and vault data folder.", "error")
            return
        self.model = model
        self.load_error = None
        self._build()
        self.shell.notify("Lockout Lab restored", "The last authenticated map backup was restored.")
