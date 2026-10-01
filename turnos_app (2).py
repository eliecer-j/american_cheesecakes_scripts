"""
Gestión de turnos semanales (Flet, desktop) con SQLite.
Personas y sucursales editables · turnos · descansos · modo claro/oscuro.

Instalar y ejecutar:
    pip install flet==0.28.3
    python turnos_app.py

La base de datos (turnos.db) se crea sola junto al script, con datos de ejemplo.
"""
import os
import random
import sqlite3
from datetime import date, timedelta

import flet as ft

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turnos.db")

DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
SHIFTS = {
    "Mañana": ("06:00–14:00", ft.Icons.WB_SUNNY_OUTLINED),
    "Tarde": ("14:00–22:00", ft.Icons.WB_TWILIGHT),
    "Noche": ("22:00–06:00", ft.Icons.NIGHTLIGHT_OUTLINED),
    "Descanso": ("Libre", ft.Icons.BEDTIME_OUTLINED),
}
WORK_SHIFTS = ["Mañana", "Tarde", "Noche"]
REST_COLOR = "#8A929C"
# Compatibilidad: algunos colores del tema cambian de nombre entre versiones de Flet
def _pick_color(*names):
    for n in names:
        c = getattr(ft.Colors, n, None)
        if c is not None:
            return c
    return ft.Colors.SURFACE


PAGE_BG = _pick_color("SURFACE_CONTAINER_LOW", "SURFACE_CONTAINER", "SURFACE_CONTAINER_HIGHEST")
BRANCH_PALETTE = [
    "#2F6FED", "#12A37F", "#E59A1D", "#8B5CF6", "#E5534B", "#14A9C2",
    "#7FA81B", "#DB4F8E", "#5865F2", "#D9772B", "#3E9B8F", "#A16B4A",
]
AVATAR_COLORS = ["#2F6FED", "#12A37F", "#E59A1D", "#8B5CF6", "#E5534B", "#14A9C2", "#DB4F8E", "#7FA81B"]

SEED_PEOPLE = [
    "Ana Torres", "Luis Pérez", "María Gómez", "Carlos Ruiz", "Sofía Díaz",
    "Jorge Castro", "Lucía Vega", "Pedro Silva", "Valeria Mora", "Diego Rojas",
    "Camila Núñez", "Andrés Soto", "Paula Ibarra", "Martín Ortiz", "Elena Paz",
    "Raúl Medina", "Natalia Cruz", "Hugo Salas", "Daniela León", "Tomás Rey",
]
SEED_BRANCHES = [
    "Centro", "Norte", "Sur", "Este", "Oeste", "Plaza Mayor",
    "Aeropuerto", "Universidad", "Terminal", "Puerto", "Mercado",
]


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ======================= Base de datos =======================
class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._seed_once()

    def _create_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS branches (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL
            );
            -- Una fila por persona y día: no puede estar en dos sucursales el
            -- mismo día (PRIMARY KEY), pero sí cambiar de una a otra entre días.
            CREATE TABLE IF NOT EXISTS assignments (
                week_start TEXT    NOT NULL,
                person_id  INTEGER NOT NULL REFERENCES people(id)   ON DELETE CASCADE,
                day        INTEGER NOT NULL CHECK (day BETWEEN 0 AND 6),
                branch_id  INTEGER REFERENCES branches(id) ON DELETE CASCADE,
                shift      TEXT    NOT NULL CHECK (shift IN ('Mañana','Tarde','Noche','Descanso')),
                PRIMARY KEY (week_start, person_id, day),
                CHECK ((shift = 'Descanso' AND branch_id IS NULL)
                    OR (shift <> 'Descanso' AND branch_id IS NOT NULL))
            );
            CREATE INDEX IF NOT EXISTS idx_assign_branch
                ON assignments (week_start, branch_id, day);
            """
        )
        self.conn.commit()

    def _seed_once(self):
        # user_version evita volver a sembrar si el usuario vacía las tablas
        if self.conn.execute("PRAGMA user_version").fetchone()[0] != 0:
            return
        with self.conn:
            self.conn.executemany("INSERT OR IGNORE INTO people (name) VALUES (?)",
                                  [(n,) for n in SEED_PEOPLE])
            self.conn.executemany(
                "INSERT OR IGNORE INTO branches (name, color) VALUES (?, ?)",
                [(n, BRANCH_PALETTE[i % len(BRANCH_PALETTE)]) for i, n in enumerate(SEED_BRANCHES)],
            )
            self.conn.execute("PRAGMA user_version = 1")
        self.autogenerate(monday_of(date.today()).isoformat())

    # ---- personas ----
    def people(self):
        return [(r["id"], r["name"]) for r in self.conn.execute("SELECT id, name FROM people ORDER BY name")]

    def add_person(self, name):
        with self.conn:
            self.conn.execute("INSERT INTO people (name) VALUES (?)", (name,))

    def rename_person(self, pid, name):
        with self.conn:
            self.conn.execute("UPDATE people SET name=? WHERE id=?", (name, pid))

    def delete_person(self, pid):
        with self.conn:
            self.conn.execute("DELETE FROM people WHERE id=?", (pid,))

    # ---- sucursales ----
    def branches(self):
        return [(r["id"], r["name"], r["color"])
                for r in self.conn.execute("SELECT id, name, color FROM branches ORDER BY name")]

    def add_branch(self, name, color):
        with self.conn:
            self.conn.execute("INSERT INTO branches (name, color) VALUES (?, ?)", (name, color))

    def update_branch(self, bid, name, color):
        with self.conn:
            self.conn.execute("UPDATE branches SET name=?, color=? WHERE id=?", (name, color, bid))

    def delete_branch(self, bid):
        with self.conn:
            self.conn.execute("DELETE FROM branches WHERE id=?", (bid,))

    # ---- turnos ----
    def week(self, week_start):
        """{(person_id, day): (branch_id | None, shift)}"""
        rows = self.conn.execute(
            "SELECT person_id, day, branch_id, shift FROM assignments WHERE week_start=?",
            (week_start,))
        return {(r["person_id"], r["day"]): (r["branch_id"], r["shift"]) for r in rows}

    def set_assignment(self, week_start, pid, day, branch_id, shift):
        with self.conn:
            if shift is None:
                self.conn.execute(
                    "DELETE FROM assignments WHERE week_start=? AND person_id=? AND day=?",
                    (week_start, pid, day))
            else:
                self.conn.execute(
                    "INSERT OR REPLACE INTO assignments VALUES (?,?,?,?,?)",
                    (week_start, pid, day, None if shift == "Descanso" else branch_id, shift))

    def clear_week(self, week_start):
        with self.conn:
            self.conn.execute("DELETE FROM assignments WHERE week_start=?", (week_start,))

    def autogenerate(self, week_start):
        rnd = random.Random()
        branch_ids = [b[0] for b in self.branches()]
        rows = []
        if branch_ids:
            for pid, _ in self.people():
                rest_days = rnd.sample(range(7), 2)
                home = rnd.choice(branch_ids)
                for d in range(7):
                    if d in rest_days:
                        rows.append((week_start, pid, d, None, "Descanso"))
                    else:
                        b = home if rnd.random() < 0.55 else rnd.choice(branch_ids)
                        rows.append((week_start, pid, d, b, rnd.choice(WORK_SHIFTS)))
        with self.conn:
            self.conn.execute("DELETE FROM assignments WHERE week_start=?", (week_start,))
            self.conn.executemany("INSERT INTO assignments VALUES (?,?,?,?,?)", rows)

    def copy_week(self, src, dst):
        with self.conn:
            self.conn.execute("DELETE FROM assignments WHERE week_start=?", (dst,))
            self.conn.execute(
                "INSERT INTO assignments (week_start, person_id, day, branch_id, shift) "
                "SELECT ?, person_id, day, branch_id, shift FROM assignments WHERE week_start=?",
                (dst, src))


# ======================= Interfaz =======================
def main(page: ft.Page):
    db = Database(DB_PATH)
    data = {}

    def reload():
        data["people"] = db.people()
        data["branches"] = db.branches()
        data["branch"] = {b[0]: (b[1], b[2]) for b in data["branches"]}
        data["branch_id"] = {b[1]: b[0] for b in data["branches"]}

    reload()
    state = {"section": 0, "offset": 0, "view": "persona", "highlight": None}

    # ---------- tema ----------
    page.title = "Turnos"
    page.padding = 0
    page.spacing = 0
    page.theme = ft.Theme(color_scheme_seed="#0F766E", use_material3=True)
    page.dark_theme = ft.Theme(color_scheme_seed="#0F766E", use_material3=True)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 1380
    page.window.height = 880
    page.window.min_width = 1180
    page.window.min_height = 700

    MUTED = ft.Colors.ON_SURFACE_VARIANT
    LINE = ft.Colors.with_opacity(0.55, ft.Colors.OUTLINE_VARIANT)

    def monday():
        return monday_of(date.today()) + timedelta(weeks=state["offset"])

    def week_key():
        return monday().isoformat()

    # ---------- helpers de UI ----------
    def toast(msg):
        page.open(ft.SnackBar(ft.Text(msg), behavior=ft.SnackBarBehavior.FLOATING, width=380))

    def confirm(title, text, on_yes, label="Eliminar", danger=True):
        def yes(e):
            page.close(dlg)
            on_yes()

        style = ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR) if danger else None
        dlg = ft.AlertDialog(
            modal=True,
            shape=ft.RoundedRectangleBorder(radius=14),
            title=ft.Text(title),
            content=ft.Container(ft.Text(text, color=MUTED), width=380),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: page.close(dlg)),
                     ft.FilledButton(label, on_click=yes, style=style)],
        )
        page.open(dlg)

    def surface(content, expand=False, padding=0, radius=14):
        return ft.Container(
            content=content, expand=expand, padding=padding, border_radius=radius,
            bgcolor=ft.Colors.SURFACE, border=ft.border.all(1, LINE),
        )

    def hover_scale(e):
        e.control.scale = 1.025 if e.data == "true" else 1
        e.control.update()

    def avatar(pid, name, size=34):
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
        color = AVATAR_COLORS[pid % len(AVATAR_COLORS)]
        return ft.Container(
            width=size, height=size, border_radius=size / 2, alignment=ft.alignment.center,
            bgcolor=ft.Colors.with_opacity(0.16, color),
            content=ft.Text(initials, size=size * 0.38, weight=ft.FontWeight.W_700, color=color),
        )

    def week_label():
        s = monday()
        e = s + timedelta(days=6)
        if s.month == e.month:
            return f"{s.day}–{e.day} {MONTHS[e.month - 1]} {e.year}"
        return f"{s.day} {MONTHS[s.month - 1]} – {e.day} {MONTHS[e.month - 1]} {e.year}"

    def page_title(title, subtitle, *actions):
        return ft.Row(
            [ft.Column([ft.Text(title, size=26, weight=ft.FontWeight.W_700),
                        ft.Text(subtitle, size=13, color=MUTED)], spacing=2),
             ft.Container(expand=True), *actions],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ---------- editor de celda ----------
    def open_cell_editor(pid, pname, day):
        if not data["branches"]:
            toast("Crea una sucursal antes de asignar turnos.")
            return
        branch_id, shift = db.week(week_key()).get((pid, day), (None, None))
        day_date = monday() + timedelta(days=day)

        dd_shift = ft.Dropdown(
            label="Turno", value=shift or "Sin asignar", border_radius=10,
            options=[ft.dropdown.Option(s) for s in [*SHIFTS, "Sin asignar"]],
        )
        dd_branch = ft.Dropdown(
            label="Sucursal", border_radius=10,
            value=data["branch"][branch_id][0] if branch_id in data["branch"] else data["branches"][0][1],
            options=[ft.dropdown.Option(b[1]) for b in data["branches"]],
            disabled=dd_shift.value in ("Descanso", "Sin asignar"),
        )
        hours = ft.Text("", size=12, color=MUTED)

        def refresh(_=None):
            dd_branch.disabled = dd_shift.value in ("Descanso", "Sin asignar")
            hours.value = SHIFTS[dd_shift.value][0] if dd_shift.value in SHIFTS else ""
            if _ is not None:
                dd_branch.update()
                hours.update()

        dd_shift.on_change = refresh
        refresh()

        def save(e):
            if dd_shift.value == "Sin asignar":
                db.set_assignment(week_key(), pid, day, None, None)
            else:
                db.set_assignment(week_key(), pid, day, data["branch_id"][dd_branch.value], dd_shift.value)
            page.close(dlg)
            show()

        dlg = ft.AlertDialog(
            modal=True, shape=ft.RoundedRectangleBorder(radius=14),
            title=ft.Row([avatar(pid, pname, 36),
                          ft.Column([ft.Text(pname, size=17, weight=ft.FontWeight.W_600),
                                     ft.Text(f"{DAYS[day]} {day_date.day} {MONTHS[day_date.month - 1]}",
                                             size=12, color=MUTED)], spacing=0)], spacing=12),
            content=ft.Container(ft.Column([dd_shift, hours, dd_branch], tight=True, spacing=12), width=340),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: page.close(dlg)),
                     ft.FilledButton("Guardar", on_click=save)],
        )
        page.open(dlg)

    # ---------- celdas del horario ----------
    def person_cell(pid, pname, day, sch):
        branch_id, shift = sch.get((pid, day), (None, None))
        base = dict(expand=1, height=58, border_radius=10, animate_scale=ft.Animation(110, ft.AnimationCurve.EASE_OUT),
                    on_hover=hover_scale, on_click=lambda e: open_cell_editor(pid, pname, day))
        if shift is None:
            return ft.Container(
                **base, tooltip="Asignar turno", alignment=ft.alignment.center,
                border=ft.border.all(1, LINE),
                content=ft.Icon(ft.Icons.ADD, size=16, color=ft.Colors.with_opacity(0.5, MUTED)),
            )
        rest = shift == "Descanso"
        bname, bcolor = data["branch"].get(branch_id, ("—", REST_COLOR))
        color = REST_COLOR if rest else bcolor
        dim = state["highlight"] is not None and (rest or branch_id != state["highlight"])
        hours, icon = SHIFTS[shift]
        return ft.Container(
            **base, padding=ft.padding.symmetric(vertical=8, horizontal=8),
            opacity=0.35 if dim else 1,
            bgcolor=ft.Colors.with_opacity(0.10 if rest else 0.15, color),
            tooltip=f"{'Descanso' if rest else bname} · {shift} ({hours})",
            content=ft.Row(
                [ft.Container(width=4, border_radius=4, bgcolor=color),
                 ft.Column(
                     [ft.Text("Descanso" if rest else bname, size=12, weight=ft.FontWeight.W_600,
                              max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                              color=MUTED if rest else None),
                      ft.Row([ft.Icon(icon, size=12, color=color),
                              ft.Text("Libre" if rest else shift, size=11, color=MUTED)],
                             spacing=4)],
                     spacing=2, expand=True, alignment=ft.MainAxisAlignment.CENTER)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
        )

    def branch_cell(bid, bcolor, bname, day, sch):
        names = dict(data["people"])
        by_shift = {s: [] for s in WORK_SHIFTS}
        for pid, _ in data["people"]:
            b, s = sch.get((pid, day), (None, None))
            if b == bid:
                by_shift[s].append(names[pid])
        total = sum(len(v) for v in by_shift.values())
        gaps = [s for s, v in by_shift.items() if not v]
        tip = "\n".join(f"{s}: {', '.join(v) if v else 'sin cobertura'}" for s, v in by_shift.items())
        chips = []
        for s in WORK_SHIFTS:
            n = len(by_shift[s])
            chips.append(ft.Container(
                padding=ft.padding.symmetric(horizontal=6, vertical=1), border_radius=6,
                bgcolor=ft.Colors.with_opacity(0.18, bcolor) if n else ft.Colors.with_opacity(0.14, ft.Colors.ERROR),
                content=ft.Text(f"{s[0]}{n}", size=11, weight=ft.FontWeight.W_600,
                                color=None if n else ft.Colors.ERROR)))
        return ft.Container(
            expand=1, height=58, border_radius=10, padding=8, tooltip=tip,
            bgcolor=ft.Colors.with_opacity(0.08, bcolor),
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, ft.Colors.ERROR) if gaps else ft.Colors.with_opacity(0.0, bcolor)),
            content=ft.Column(
                [ft.Text(f"{total} personas" if total != 1 else "1 persona", size=12, weight=ft.FontWeight.W_600),
                 ft.Row(chips, spacing=4)],
                spacing=4, alignment=ft.MainAxisAlignment.CENTER),
        )

    # ---------- sección: Turnos ----------
    def build_schedule():
        sch = db.week(week_key())
        today_idx = date.today().weekday() if state["offset"] == 0 else None
        people, branches = data["people"], data["branches"]

        def head_row(first, extra_width=0, extra_label=""):
            start = monday()
            cells = [ft.Container(ft.Text(first, size=12, color=MUTED, weight=ft.FontWeight.W_600), width=190)]
            for i, d in enumerate(DAYS):
                is_today = i == today_idx
                cells.append(ft.Container(
                    expand=1, alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=4),
                    border_radius=8,
                    bgcolor=_pick_color('PRIMARY_CONTAINER', 'PRIMARY') if is_today else None,
                    content=ft.Text(f"{d} {(start + timedelta(days=i)).day}", size=12,
                                    weight=ft.FontWeight.W_700 if is_today else ft.FontWeight.W_600,
                                    color=_pick_color('ON_PRIMARY_CONTAINER', 'ON_PRIMARY') if is_today else MUTED)))
            if extra_width:
                cells.append(ft.Container(ft.Text(extra_label, size=12, color=MUTED, weight=ft.FontWeight.W_600),
                                          width=extra_width, alignment=ft.alignment.center))
            return ft.Row(cells, spacing=6)

        rows = []
        if state["view"] == "persona":
            header = head_row("Persona", 76, "Descansos")
            for pid, pname in people:
                assigned = [sch[(pid, d)][1] for d in range(7) if (pid, d) in sch]
                rests = assigned.count("Descanso")
                alert = len(assigned) == 7 and rests == 0
                badge = ft.Container(
                    width=76, alignment=ft.alignment.center,
                    content=ft.Container(
                        padding=ft.padding.symmetric(horizontal=10, vertical=3), border_radius=12,
                        bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.ERROR if alert else REST_COLOR),
                        tooltip="Sin día de descanso" if alert else None,
                        content=ft.Text(f"{rests}", size=12, weight=ft.FontWeight.W_700,
                                        color=ft.Colors.ERROR if alert else MUTED)))
                rows.append(ft.Row(
                    [ft.Container(ft.Row([avatar(pid, pname, 30),
                                          ft.Text(pname, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)],
                                         spacing=10), width=190)]
                    + [person_cell(pid, pname, d, sch) for d in range(7)] + [badge], spacing=6))
        else:
            header = head_row("Sucursal")
            for bid, bname, bcolor in branches:
                rows.append(ft.Row(
                    [ft.Container(ft.Row([ft.Container(width=10, height=10, border_radius=3, bgcolor=bcolor),
                                          ft.Text(bname, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)],
                                         spacing=10), width=190)]
                    + [branch_cell(bid, bcolor, bname, d, sch) for d in range(7)], spacing=6))

        if not rows:
            rows = [ft.Container(padding=40, alignment=ft.alignment.center, content=ft.Column(
                [ft.Icon(ft.Icons.INBOX_OUTLINED, size=36, color=MUTED),
                 ft.Text("No hay personas o sucursales todavía.", color=MUTED),
                 ft.Text("Agrégalas en las secciones Personas y Sucursales.", size=12, color=MUTED)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER))]

        # leyenda = filtro: clic para resaltar una sucursal
        def toggle_highlight(bid):
            state["highlight"] = None if state["highlight"] == bid else bid
            show()

        legend = ft.Row(
            [ft.Container(
                padding=ft.padding.symmetric(horizontal=10, vertical=4), border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.18, c) if state["highlight"] == b else None,
                border=ft.border.all(1, c if state["highlight"] == b else LINE),
                on_click=lambda e, b=b: toggle_highlight(b),
                content=ft.Row([ft.Container(width=8, height=8, border_radius=4, bgcolor=c),
                                ft.Text(n, size=11)], spacing=6))
             for b, n, c in branches],
            wrap=True, spacing=6, run_spacing=6,
        ) if state["view"] == "persona" else ft.Container()

        pending = len(people) * 7 - len(sch)
        no_rest = sum(1 for pid, _ in people
                      if all((pid, d) in sch and sch[(pid, d)][1] != "Descanso" for d in range(7)))
        status = ft.Row([
            ft.Row([ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=16, color=MUTED), ft.Text(f"{len(people)} personas", size=12, color=MUTED)], spacing=6),
            ft.Row([ft.Icon(ft.Icons.STORE_OUTLINED, size=16, color=MUTED), ft.Text(f"{len(branches)} sucursales", size=12, color=MUTED)], spacing=6),
            ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=16, color=ft.Colors.ERROR if no_rest else MUTED),
                    ft.Text(f"{no_rest} sin descanso", size=12, color=ft.Colors.ERROR if no_rest else MUTED)], spacing=6),
            ft.Row([ft.Icon(ft.Icons.EVENT_BUSY_OUTLINED, size=16, color=MUTED),
                    ft.Text(f"{pending} celdas sin asignar", size=12, color=MUTED)], spacing=6),
        ], spacing=22)

        # --- acciones de semana ---
        def do_copy():
            db.copy_week((monday() - timedelta(weeks=1)).isoformat(), week_key())
            show()
            toast("Semana copiada desde la anterior.")

        def do_auto():
            db.autogenerate(week_key())
            show()
            toast("Semana generada con datos de ejemplo.")

        def do_clear():
            db.clear_week(week_key())
            show()
            toast("Semana vaciada.")

        menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT, tooltip="Acciones de la semana",
            items=[
                ft.PopupMenuItem(text="Copiar semana anterior", icon=ft.Icons.CONTENT_COPY_OUTLINED,
                                 on_click=lambda e: confirm("Copiar semana anterior",
                                                            "Se reemplazarán los turnos de esta semana.",
                                                            do_copy, "Copiar", danger=False)),
                ft.PopupMenuItem(text="Generar datos de ejemplo", icon=ft.Icons.AUTO_AWESOME_OUTLINED,
                                 on_click=lambda e: confirm("Generar datos de ejemplo",
                                                            "Se reemplazarán los turnos de esta semana.",
                                                            do_auto, "Generar", danger=False)),
                ft.PopupMenuItem(text="Vaciar semana", icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                                 on_click=lambda e: confirm("Vaciar semana",
                                                            "Se quitarán todos los turnos de esta semana.",
                                                            do_clear, "Vaciar")),
            ])

        def go(delta):
            state["offset"] += delta
            show()

        def go_today(e):
            state["offset"] = 0
            show()

        def on_view(e):
            state["view"] = next(iter(e.control.selected))
            show()

        week_nav = ft.Container(
            border_radius=22, bgcolor=ft.Colors.SURFACE, border=ft.border.all(1, LINE),
            content=ft.Row([
                ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=20, tooltip="Semana anterior", on_click=lambda e: go(-1)),
                ft.Container(ft.Text(week_label(), size=14, weight=ft.FontWeight.W_600,
                                     text_align=ft.TextAlign.CENTER), width=170, alignment=ft.alignment.center),
                ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=20, tooltip="Semana siguiente", on_click=lambda e: go(1)),
            ], spacing=0))

        view_toggle = ft.SegmentedButton(
            selected={state["view"]}, allow_multiple_selection=False, on_change=on_view, show_selected_icon=False,
            segments=[ft.Segment(value="persona", label=ft.Text("Personas"), icon=ft.Icon(ft.Icons.PERSON_OUTLINE)),
                      ft.Segment(value="sucursal", label=ft.Text("Sucursales"), icon=ft.Icon(ft.Icons.STORE_OUTLINED))])

        top = page_title(
            "Turnos", "Haz clic en una celda para asignar sucursal y turno.",
            ft.TextButton("Hoy", on_click=go_today, visible=state["offset"] != 0),
            week_nav, view_toggle, menu)

        grid = surface(
            ft.Column([
                header,
                ft.Divider(height=1, color=LINE),
                ft.Column(rows, scroll=ft.ScrollMode.AUTO, expand=True, spacing=6),
                legend,
            ], spacing=10, expand=True),
            expand=True, padding=ft.padding.only(left=16, right=16, top=12, bottom=14))

        return ft.Column([top, status, grid], expand=True, spacing=16)

    # ---------- sección: Personas ----------
    def person_dialog(pid=None, current=""):
        tf = ft.TextField(label="Nombre completo", value=current, autofocus=True, border_radius=10)

        def save(e):
            name = " ".join((tf.value or "").split())
            if not name:
                tf.error_text = "Escribe un nombre."
                tf.update()
                return
            try:
                db.add_person(name) if pid is None else db.rename_person(pid, name)
            except sqlite3.IntegrityError:
                tf.error_text = "Ya existe una persona con ese nombre."
                tf.update()
                return
            page.close(dlg)
            reload()
            show()
            toast("Persona agregada." if pid is None else "Cambios guardados.")

        tf.on_submit = save
        dlg = ft.AlertDialog(
            modal=True, shape=ft.RoundedRectangleBorder(radius=14),
            title=ft.Text("Nueva persona" if pid is None else "Editar persona"),
            content=ft.Container(tf, width=340),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: page.close(dlg)),
                     ft.FilledButton("Agregar" if pid is None else "Guardar cambios", on_click=save)])
        page.open(dlg)

    def delete_person(pid, name):
        def go():
            db.delete_person(pid)
            reload()
            show()
            toast(f"{name} eliminada.")
        confirm(f"Eliminar a {name}", "También se borrarán todos sus turnos de todas las semanas.", go)

    def build_people():
        sch = db.week(week_key())
        items = []
        for pid, name in data["people"]:
            assigned = [sch[(pid, d)][1] for d in range(7) if (pid, d) in sch]
            rests = assigned.count("Descanso")
            worked = len(assigned) - rests
            sub = f"Esta semana: {worked} turnos, {rests} descansos" if assigned else "Sin turnos esta semana"
            items.append(ft.Container(
                padding=ft.padding.symmetric(horizontal=14, vertical=10), border_radius=10,
                content=ft.Row([
                    avatar(pid, name, 38),
                    ft.Column([ft.Text(name, size=14, weight=ft.FontWeight.W_600),
                               ft.Text(sub, size=12, color=MUTED)], spacing=0, expand=True),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Editar",
                                  on_click=lambda e, p=pid, n=name: person_dialog(p, n)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Eliminar", icon_color=ft.Colors.ERROR,
                                  on_click=lambda e, p=pid, n=name: delete_person(p, n)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)))
            items.append(ft.Divider(height=1, color=LINE))
        if items:
            items.pop()
        else:
            items = [ft.Container(padding=40, alignment=ft.alignment.center,
                                  content=ft.Text("Aún no hay personas. Agrega la primera.", color=MUTED))]
        return ft.Column([
            page_title("Personas", f"{len(data['people'])} en el equipo",
                       ft.FilledButton("Nueva persona", icon=ft.Icons.ADD, on_click=lambda e: person_dialog())),
            surface(ft.Column(items, scroll=ft.ScrollMode.AUTO, spacing=0), expand=True, padding=6),
        ], expand=True, spacing=16)

    # ---------- sección: Sucursales ----------
    def branch_dialog(bid=None, name="", color=None):
        used = {b[2] for b in data["branches"]}
        sel = {"c": color or next((c for c in BRANCH_PALETTE if c not in used), BRANCH_PALETTE[0])}
        tf = ft.TextField(label="Nombre de la sucursal", value=name, autofocus=True, border_radius=10)
        swatches = ft.Row(wrap=True, spacing=10, run_spacing=10)

        def paint():
            swatches.controls = [
                ft.Container(
                    width=32, height=32, border_radius=16, bgcolor=c,
                    border=ft.border.all(3, ft.Colors.ON_SURFACE if c == sel["c"] else ft.Colors.TRANSPARENT),
                    on_click=lambda e, c=c: pick(c))
                for c in BRANCH_PALETTE]

        def pick(c):
            sel["c"] = c
            paint()
            swatches.update()

        paint()

        def save(e):
            n = " ".join((tf.value or "").split())
            if not n:
                tf.error_text = "Escribe un nombre."
                tf.update()
                return
            try:
                db.add_branch(n, sel["c"]) if bid is None else db.update_branch(bid, n, sel["c"])
            except sqlite3.IntegrityError:
                tf.error_text = "Ya existe una sucursal con ese nombre."
                tf.update()
                return
            page.close(dlg)
            reload()
            show()
            toast("Sucursal agregada." if bid is None else "Cambios guardados.")

        tf.on_submit = save
        dlg = ft.AlertDialog(
            modal=True, shape=ft.RoundedRectangleBorder(radius=14),
            title=ft.Text("Nueva sucursal" if bid is None else "Editar sucursal"),
            content=ft.Container(ft.Column([tf, ft.Text("Color en el horario", size=12, color=MUTED), swatches],
                                           tight=True, spacing=14), width=360),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: page.close(dlg)),
                     ft.FilledButton("Agregar" if bid is None else "Guardar cambios", on_click=save)])
        page.open(dlg)

    def delete_branch(bid, name):
        def go():
            db.delete_branch(bid)
            if state["highlight"] == bid:
                state["highlight"] = None
            reload()
            show()
            toast(f"{name} eliminada.")
        confirm(f"Eliminar {name}", "Se borrarán los turnos asignados a esta sucursal en todas las semanas.", go)

    def build_branches():
        sch = db.week(week_key())
        cards = []
        for bid, name, color in data["branches"]:
            mine = [(p, d) for (p, d), (b, _) in sch.items() if b == bid]
            people_n = len({p for p, _ in mine})
            cards.append(surface(
                ft.Column([
                    ft.Row([
                        ft.Container(width=40, height=40, border_radius=10, alignment=ft.alignment.center,
                                     bgcolor=ft.Colors.with_opacity(0.16, color),
                                     content=ft.Icon(ft.Icons.STORE_OUTLINED, color=color, size=22)),
                        ft.Column([ft.Text(name, size=15, weight=ft.FontWeight.W_600, max_lines=1,
                                           overflow=ft.TextOverflow.ELLIPSIS),
                                   ft.Text(f"{len(mine)} turnos · {people_n} personas", size=12, color=MUTED)],
                                  spacing=0, expand=True)], spacing=12),
                    ft.Row([ft.Container(expand=True),
                            ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Editar", icon_size=19,
                                          on_click=lambda e, b=bid, n=name, c=color: branch_dialog(b, n, c)),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Eliminar", icon_size=19,
                                          icon_color=ft.Colors.ERROR,
                                          on_click=lambda e, b=bid, n=name: delete_branch(b, n))],
                           spacing=0),
                ], spacing=4),
                padding=ft.padding.only(left=16, right=8, top=16, bottom=6)))
        for c in cards:
            c.width = 290
        body = ft.Row(cards, wrap=True, spacing=14, run_spacing=14, alignment=ft.MainAxisAlignment.START) if cards \
            else ft.Container(padding=40, content=ft.Text("Aún no hay sucursales. Agrega la primera.", color=MUTED))
        return ft.Column([
            page_title("Sucursales", f"{len(data['branches'])} sucursales · conteo de la semana {week_label()}",
                       ft.FilledButton("Nueva sucursal", icon=ft.Icons.ADD, on_click=lambda e: branch_dialog())),
            ft.Column([body], scroll=ft.ScrollMode.AUTO, expand=True),
        ], expand=True, spacing=16)

    # ---------- navegación y shell ----------
    main_area = ft.Container(expand=True, padding=ft.padding.only(left=28, right=28, top=22, bottom=22),
                             bgcolor=PAGE_BG)

    def show():
        builders = [build_schedule, build_people, build_branches]
        main_area.content = builders[state["section"]]()
        page.update()

    def on_nav(e):
        state["section"] = e.control.selected_index
        show()

    def toggle_theme(e):
        dark = page.theme_mode == ft.ThemeMode.LIGHT
        page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
        e.control.icon = ft.Icons.LIGHT_MODE_OUTLINED if dark else ft.Icons.DARK_MODE_OUTLINED
        page.update()

    rail = ft.NavigationRail(
        selected_index=0, min_width=84, bgcolor=ft.Colors.SURFACE,
        label_type=ft.NavigationRailLabelType.ALL, on_change=on_nav,
        leading=ft.Container(padding=ft.padding.only(top=16, bottom=14), content=ft.Container(
            width=42, height=42, border_radius=12, alignment=ft.alignment.center,
            bgcolor=ft.Colors.PRIMARY, content=ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK, color=ft.Colors.ON_PRIMARY))),
        trailing=ft.Container(padding=ft.padding.only(top=24), content=ft.IconButton(
            ft.Icons.DARK_MODE_OUTLINED, tooltip="Cambiar tema", on_click=toggle_theme)),
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                                         selected_icon=ft.Icons.CALENDAR_MONTH, label="Turnos"),
            ft.NavigationRailDestination(icon=ft.Icons.GROUPS_OUTLINED,
                                         selected_icon=ft.Icons.GROUPS, label="Personas"),
            ft.NavigationRailDestination(icon=ft.Icons.STORE_OUTLINED,
                                         selected_icon=ft.Icons.STORE, label="Sucursales"),
        ],
    )

    page.add(ft.Row([rail, ft.VerticalDivider(width=1, color=LINE), main_area], expand=True, spacing=0))
    show()


if __name__ == "__main__":
    ft.app(target=main)
