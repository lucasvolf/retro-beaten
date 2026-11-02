"""Responsive cover layout with centered rows."""


def enable_responsive_grid(parent, covers):
    """Adapt columns and center each row of covers in the panel."""
    previous = getattr(parent, "_cancel_cover_layout", None)
    if previous:
        previous()
    for column in range(parent.grid_size()[0]):
        parent.grid_columnconfigure(column, minsize=0, weight=0)
    if not covers:
        return

    # Center the grid horizontally and align it to the top.
    parent.grid_anchor("n")

    # Share a temporary cell until the panel width is known.
    # A temporary column with hundreds of rows creates an oversized panel
    # that can displace images within their borders on Windows.
    # Each cover spans two small columns, allowing half-cell offsets.
    for cover_label in covers:
        if not cover_label.winfo_manager():
            cover_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

    current_layout = None
    configured_columns = 0
    pending_layout = None
    last_measurement = None
    cell_width = None

    def update_layout():
        nonlocal current_layout, configured_columns, pending_layout, last_measurement, cell_width
        pending_layout = None

        # Measure frames and margins independently of their grid positions.
        # These measurements already include CustomTkinter scaling.
        available_width = parent.winfo_width()
        # Height changes and moving a window cannot change the column layout.
        # Scaling is included so moving between DPI settings still remeasures.
        measurement = (available_width, parent._get_widget_scaling())
        if measurement == last_measurement:
            return
        last_measurement = measurement
        cell_width = max(
            cover.winfo_reqwidth() + 2 * int(cover.grid_info()["padx"])
            for cover in covers
        )
        if cell_width <= 0 or available_width <= 1:
            return

        half_cell_width = (cell_width + 1) // 2
        columns = max(1, min(len(covers), available_width // (2 * half_cell_width)))
        layout = (columns, half_cell_width)
        if layout == current_layout:
            return

        # Clear old widths when the column count decreases.
        for column in range(configured_columns):
            parent.grid_columnconfigure(column, minsize=0, weight=0)
        for column in range(columns * 2):
            parent.grid_columnconfigure(column, minsize=half_cell_width, weight=0)

        current_layout = layout
        configured_columns = columns * 2

        for index, cover_label in enumerate(covers):
            row = index // columns
            row_count = min(columns, len(covers) - row * columns)
            offset = columns - row_count
            cover_label.grid(
                row=row,
                column=offset + 2 * (index % columns),
                columnspan=2,
                padx=10,
                pady=10
            )

    def cancel_layout(event=None):
        nonlocal pending_layout
        if event is not None and event.widget not in (parent, parent._canvas):
            return
        if pending_layout is not None:
            parent.after_cancel(pending_layout)
            pending_layout = None

    def schedule_layout(event=None):
        nonlocal pending_layout
        # Wait for the width to settle before laying out the covers.
        cancel_layout()
        pending_layout = parent.after(50, update_layout)

    # Bind on the native canvas to retain IDs: CTkFrame.bind always appends
    # callbacks and discards those IDs, which otherwise accumulates stale grids.
    configure_id = parent._canvas.bind("<Configure>", schedule_layout, add="+")
    destroy_id = parent._canvas.bind("<Destroy>", cancel_layout, add="+")
    active = True

    def stop_layout():
        nonlocal active
        if not active:
            return
        active = False
        cancel_layout()
        if parent._canvas.winfo_exists():
            parent._canvas.unbind("<Configure>", configure_id)
            parent._canvas.unbind("<Destroy>", destroy_id)

    parent._cancel_cover_layout = stop_layout
    schedule_layout()
