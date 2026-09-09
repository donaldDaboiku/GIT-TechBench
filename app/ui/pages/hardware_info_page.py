"""Full inventory from the last system scan."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.system_info import (
    DataOrigin,
    FieldValue,
    SystemInfo,
    format_bytes,
)
from app.ui.components.page_header import PageHeader


def _origin_text(origin: DataOrigin, note: str = "") -> str:
    label = origin.value.capitalize()
    return f"{label}" + (f" — {note}" if note else "")


class HardwareInfoPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.layout_body = QVBoxLayout(body)
        self.layout_body.setContentsMargins(28, 24, 28, 24)
        self.layout_body.setSpacing(16)
        self.header = PageHeader(
            "Hardware Info",
            "Measured inventory only. Unavailable fields stay Unavailable.",
        )
        self.layout_body.addWidget(self.header)
        self.sections = QVBoxLayout()
        self.sections.setSpacing(16)
        self.layout_body.addLayout(self.sections)
        self.layout_body.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self._show_message("Run a dashboard scan to populate this page.")

    def apply_info(self, info: SystemInfo) -> None:
        self._clear_sections()
        when = info.collected_at.strftime("%Y-%m-%d %H:%M:%S")
        self.header.set_subtitle(f"Last scan {when}. Values are tagged Measured / Unavailable / Estimated.")

        identity = [
            ("Computer name", info.computer_name),
            ("Manufacturer", info.manufacturer),
            ("Model", info.model),
            ("Serial number", info.serial_number),
            ("Operating system", info.os_caption),
            ("Windows version", info.windows_version),
            ("Architecture", info.os_architecture),
            ("BIOS version", info.bios_version),
            ("BIOS date", info.bios_date),
            ("Uptime", info.uptime),
        ]
        self.sections.addWidget(self._field_card("Identity", identity))

        cpu_ram = [
            ("Processor", info.cpu_name),
            ("Physical cores", info.cpu_physical_cores),
            ("Logical processors", info.cpu_logical_cores),
            (
                "Total RAM",
                FieldValue(
                    info.ram_total_display() if info.ram_total_bytes is not None else None,
                    info.ram_origin,
                    info.ram_note,
                ),
            ),
            (
                "Available RAM",
                FieldValue(
                    format_bytes(info.ram_available_bytes) if info.ram_available_bytes is not None else None,
                    info.ram_origin,
                    info.ram_note,
                ),
            ),
        ]
        self.sections.addWidget(self._field_card("CPU & Memory", cpu_ram))

        vol_fields: list[tuple[str, FieldValue]] = []
        if not info.volumes:
            vol_fields.append(("Volumes", FieldValue.unavailable("No volumes enumerated")))
        for vol in info.volumes:
            size = format_bytes(vol.total_bytes) if vol.total_bytes is not None else "Unavailable"
            used = format_bytes(vol.used_bytes) if vol.used_bytes is not None else "Unavailable"
            free = format_bytes(vol.free_bytes) if vol.free_bytes is not None else "Unavailable"
            fs = vol.filesystem.display()
            vol_fields.append(
                (
                    vol.letter,
                    FieldValue(
                        f"{fs} · {size} total · {used} used · {free} free",
                        vol.origin,
                        vol.note,
                    ),
                )
            )
        self.sections.addWidget(self._field_card("Volumes", vol_fields))

        disk_fields: list[tuple[str, FieldValue]] = []
        if not info.physical_disks:
            disk_fields.append(
                ("Physical disks", FieldValue.unavailable("Win32_DiskDrive returned no rows"))
            )
        for i, disk in enumerate(info.physical_disks, start=1):
            size = format_bytes(disk.size_bytes) if disk.size_bytes is not None else "size unavailable"
            disk_fields.append(
                (
                    f"Disk {i}",
                    FieldValue.measured(
                        f"{disk.model.display()} · {size} · {disk.interface.display()} · "
                        f"serial {disk.serial.display()}"
                    ),
                )
            )
        self.sections.addWidget(self._field_card("Physical disks", disk_fields))

        gpu_fields: list[tuple[str, FieldValue]] = []
        if not info.gpus:
            gpu_fields.append(("GPU", FieldValue.unavailable("No video controller reported")))
        for gpu in info.gpus:
            ram = format_bytes(gpu.adapter_ram_bytes) if gpu.adapter_ram_bytes else "adapter RAM unavailable"
            gpu_fields.append(
                (
                    gpu.name.display(),
                    FieldValue.measured(
                        f"{gpu.manufacturer.display()} · driver {gpu.driver_version.display()} · {ram}"
                    ),
                )
            )
        self.sections.addWidget(self._field_card("Graphics", gpu_fields))

        battery_fields = [
            ("Present", FieldValue.measured("Yes" if info.battery.present else "No")),
            ("Name", info.battery.name),
            ("Charge", info.battery.percent),
            ("Power state", info.battery.charging),
        ]
        self.sections.addWidget(self._field_card("Battery", battery_fields))

        net_fields: list[tuple[str, FieldValue]] = []
        if not info.adapters:
            net_fields.append(("Adapters", FieldValue.unavailable("No adapters enumerated")))
        for adp in info.adapters:
            state = "up" if adp.is_up else "down" if adp.is_up is False else "state unknown"
            net_fields.append(
                (
                    adp.name,
                    FieldValue.measured(f"{adp.ipv4.display()} · MAC {adp.mac.display()} · {state}"),
                )
            )
        self.sections.addWidget(self._field_card("Network adapters", net_fields))

        if info.errors:
            notes = [(f"Note {i}", FieldValue.measured(msg)) for i, msg in enumerate(info.errors, start=1)]
            self.sections.addWidget(self._field_card("Collector notes", notes))

        self.sections.addStretch()

    def _show_message(self, text: str) -> None:
        self._clear_sections()
        label = QLabel(text)
        label.setObjectName("muted")
        self.sections.addWidget(label)

    def _clear_sections(self) -> None:
        while self.sections.count():
            item = self.sections.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _field_card(self, title: str, rows: list[tuple[str, FieldValue]]) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        heading = QLabel(title.upper())
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        for i, (label, field) in enumerate(rows):
            name = QLabel(label.upper())
            name.setObjectName("fieldLabel")
            value = QLabel(field.display())
            value.setObjectName("fieldValue")
            value.setWordWrap(True)
            origin = QLabel(_origin_text(field.origin, field.note))
            origin.setObjectName("muted")
            origin.setWordWrap(True)
            grid.addWidget(name, i, 0)
            grid.addWidget(value, i, 1)
            grid.addWidget(origin, i, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card
